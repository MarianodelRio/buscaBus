# tools/telegram_pruebas.py
"""Canal de pruebas por Telegram: herramienta interna de desarrollo.

Sirve para probar la conversacion (y recoger el feedback de negocio) mientras
no hay WhatsApp. No forma parte del despliegue: `app.main` no lo importa y
solo se ejecuta a mano. El producto sigue siendo solo WhatsApp. Sin tests
propios: si cambia `app/services/whatsapp.py` puede dejar de funcionar.

Hace long polling contra la API de Telegram y alimenta la misma conversacion
que el webhook de WhatsApp (`handle_message`). Los envios de
`app.services.whatsapp` se sustituyen (dentro de `main()`) por envios a
Telegram: los mensajes interactivos de WhatsApp se traducen a teclados en
linea. No toca `app/`.

Uso: TELEGRAM_BOT_TOKEN=... python -m tools.telegram_pruebas   (make telegram)

Sin efectos al importar: ni logging, ni parches, ni lectura de entorno.
Nunca se registra el token (la URL de la API lo contiene): ante errores de red
solo se registra el nombre de la excepcion.
"""
import logging
import os
import sys
import time
from functools import partial

import httpx

from app.config import HORARIOS_DIR, PUEBLOS_MENU_INICIO
from app.handlers.conversation import UNKNOWN_INPUT, handle_message
from app.services import whatsapp as wa
from app.services.horarios import datos as horarios_datos
from app.services.scheduler import create_scheduler
from app.utils.security import mask_phone

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_TEXTO = 4096          # limite de Telegram para un mensaje
_MAX_BOTON = 64            # limite de texto de un boton
_MAX_CALLBACK_BYTES = 64   # limite de callback_data (bytes UTF-8)
_POLL_TIMEOUT = 25         # segundos de long polling
_CLIENT_TIMEOUT = 35       # timeout de httpx, mayor que el del polling
_ESPERA_ERROR = 3          # segundos antes de reintentar tras un fallo


# ── Traduccion de mensajes interactivos ───────────────────────────────────


def _boton(titulo: str, callback_data: str) -> dict | None:
    if len(callback_data.encode("utf-8")) > _MAX_CALLBACK_BYTES:
        logger.error(
            "[TG] callback_data de mas de %d bytes, boton omitido: %r",
            _MAX_CALLBACK_BYTES, callback_data,
        )
        return None
    return {"text": titulo[:_MAX_BOTON], "callback_data": callback_data}


def traducir(payload: dict) -> tuple[str, dict | None]:
    """Convierte un payload interactivo de WhatsApp en (texto, reply_markup).
    Se descarta el pie; sin parse_mode."""
    inter = payload.get("interactive", {})
    partes = []
    header = inter.get("header", {}).get("text")
    if header:
        partes.append(header)
    partes.append(inter.get("body", {}).get("text", ""))
    texto = "\n\n".join(partes)

    botones: list[dict | None] = []
    extras: list[str] = []
    if inter.get("type") == "button":
        for b in inter.get("action", {}).get("buttons", []):
            r = b["reply"]
            botones.append(_boton(r["title"], r["id"]))
    elif inter.get("type") == "list":
        for seccion in inter.get("action", {}).get("sections", []):
            for row in seccion.get("rows", []):
                titulo = row["title"]
                desc = row.get("description", "")
                if not desc:
                    texto_boton = titulo
                elif desc.startswith(titulo):
                    texto_boton = desc
                else:
                    texto_boton = titulo
                    extras.append(f"{titulo}: {desc}")
                botones.append(_boton(texto_boton, row["id"]))
    if extras:
        texto += "\n\n" + "\n".join(extras)
    texto = texto[:_MAX_TEXTO]
    teclado = [[b] for b in botones if b is not None]
    markup = {"inline_keyboard": teclado} if teclado else None
    return texto, markup


# ── API de Telegram ───────────────────────────────────────────────────────


def _api(client, token: str, method: str, payload: dict | None = None,
         timeout: float | None = None):
    """POST a la API de Telegram. Devuelve `result` si ok, None si falla.
    Nunca registra la excepcion completa: la URL contiene el token."""
    url = _API.format(token=token, method=method)
    try:
        kwargs = {"json": payload or {}}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = client.post(url, **kwargs)
        data = response.json()
    except Exception as e:
        logger.error("[TG] %s: error de red/respuesta (%s)", method,
                     type(e).__name__)
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        info = data if isinstance(data, dict) else {}
        logger.error(
            "[TG] %s: error_code=%s description=%s", method,
            info.get("error_code"), info.get("description"),
        )
        return None
    result = data.get("result")
    return True if result is None else result


# ── Envios que sustituyen a los de WhatsApp ───────────────────────────────


# WhatsApp no muestra tarjeta de vista previa; Telegram sí por defecto.
_SIN_VISTA_PREVIA = {"is_disabled": True}


def tg_send_text_message(client, token: str, to: str, text: str) -> bool:
    ok = _api(client, token, "sendMessage",
              {"chat_id": to, "text": text[:_MAX_TEXTO],
               "link_preview_options": _SIN_VISTA_PREVIA}) is not None
    wa._delivery.attempted = True
    if ok:
        wa._delivery.delivered = True
    return ok


def tg_send_interactive(client, token: str, to: str, payload: dict) -> bool:
    texto, markup = traducir(payload)
    cuerpo: dict = {"chat_id": to, "text": texto,
                    "link_preview_options": _SIN_VISTA_PREVIA}
    if markup:
        cuerpo["reply_markup"] = markup
    ok = _api(client, token, "sendMessage", cuerpo) is not None
    wa._delivery.attempted = True
    if ok:
        wa._delivery.delivered = True
    return ok


def tg_send_template(to: str, template_name: str, lang: str,
                     components: list) -> bool:
    logger.warning("[TG] plantillas no soportadas en Telegram (%s)",
                   template_name)
    wa._delivery.attempted = True
    return False


# ── Proceso de un update ──────────────────────────────────────────────────


def _es_privado(chat: dict | None) -> bool:
    return bool(chat) and chat.get("type") == "private" and "id" in chat


def procesar_update(update: dict, client, token: str) -> None:
    """Procesa un update de Telegram. Solo chats privados."""
    callback = update.get("callback_query")
    if callback:
        # Siempre se responde primero, para quitar el "cargando" del boton.
        _api(client, token, "answerCallbackQuery",
             {"callback_query_id": callback.get("id")})
        message = callback.get("message") or {}
        chat = message.get("chat")
        data = callback.get("data")
        if _es_privado(chat) and data:
            chat_id = str(chat["id"])
            logger.info("[TG] callback de %s", mask_phone(chat_id))
            handle_message(chat_id, None, None, data)
        return

    message = update.get("message")
    if not message:
        return
    chat = message.get("chat")
    if not _es_privado(chat):
        return
    chat_id = str(chat["id"])
    text = message.get("text")
    if text is None:
        texto = UNKNOWN_INPUT
    else:
        stripped = text.strip()
        if stripped == "/start" or stripped.startswith("/start "):
            texto = "menu"
        else:
            texto = stripped[:_MAX_TEXTO]
    logger.info("[TG] mensaje de %s", mask_phone(chat_id))
    handle_message(chat_id, None, texto, None)


# ── Bucle y arranque ──────────────────────────────────────────────────────


def _configurar_logging() -> None:
    raw = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, raw, None)
    if not isinstance(level, int):
        print(f"[TG] LOG_LEVEL={raw!r} invalido, se usa INFO", flush=True)
        level = logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def bucle(client, token: str, stop=lambda: False) -> None:
    """Long polling. El offset avanza siempre, aunque falle el proceso."""
    offset = None
    while not stop():
        payload: dict = {
            "timeout": _POLL_TIMEOUT,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        updates = _api(client, token, "getUpdates", payload,
                       timeout=_CLIENT_TIMEOUT)
        if not isinstance(updates, list):
            time.sleep(_ESPERA_ERROR)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                procesar_update(update, client, token)
            except Exception:
                logger.exception("[TG] error procesando un update")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("Falta TELEGRAM_BOT_TOKEN (token de @BotFather, en .env).",
              file=sys.stderr)
        sys.exit(1)
    _configurar_logging()

    logger.info("[TG] Cargando horarios...")
    horarios_datos.instalar(horarios_datos.cargar(HORARIOS_DIR, PUEBLOS_MENU_INICIO))
    scheduler = create_scheduler()
    scheduler.start()

    originales = (wa.send_text_message, wa.send_interactive, wa.send_template)
    try:
        with httpx.Client(timeout=_CLIENT_TIMEOUT) as client:
            me = _api(client, token, "getMe")
            if not isinstance(me, dict):
                logger.error("[TG] getMe fallo: revisa el token")
                sys.exit(1)
            logger.info("[TG] Conectado como @%s", me.get("username"))
            _api(client, token, "deleteWebhook", {"drop_pending_updates": True})

            wa.send_text_message = partial(tg_send_text_message, client, token)
            wa.send_interactive = partial(tg_send_interactive, client, token)
            wa.send_template = tg_send_template
            try:
                bucle(client, token)
            except KeyboardInterrupt:
                logger.info("[TG] Detenido por el usuario")
    finally:
        wa.send_text_message, wa.send_interactive, wa.send_template = originales
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
