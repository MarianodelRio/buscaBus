# handlers/conversation.py
"""Infraestructura de la conversación: bloqueo por teléfono, estado con
caducidad, comandos de administrador, despacho por estado. La máquina de
estados en sí (las reglas de la tabla de design.md 4.1-4.8) vive en
`flujo.py`."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import ADMIN_COMANDOS, ADMIN_PHONE, ESTADO_EXPIRACION_MIN, TIMEZONE
from app.handlers import flujo
from app.services import whatsapp as wa
from app.utils import metrics
from app.utils.admin import (
    build_help_message,
    build_status_report,
    read_log_tail,
    schedule_restart,
)
from app.utils.messages import msg_input_no_soportado, msg_reintentar
from app.utils.security import mask_phone

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

UNKNOWN_INPUT = "__unknown__"  # tipos de mensaje no soportados (audio, imagen…)

# Palabras que, escritas en cualquier estado, vuelven al menú (design.md 4).
_ESCAPE_MENU = {"menu", "menú", "inicio", "hola", "salir"}


@dataclass
class ConversationState:
    step: str = flujo.MENU
    phone: Optional[str] = None
    campo: Optional[str] = None  # "origen" | "destino" mientras se busca/confirma
    origen: Optional[str] = None
    destino: Optional[str] = None
    fecha: Optional[date] = None
    pendiente: Optional[str] = None  # id de localidad pendiente de confirmar
    last_interaction: datetime = field(default_factory=lambda: datetime.now(TZ))

    def touch(self) -> None:
        self.last_interaction = datetime.now(TZ)


# ── Estado en memoria ──────────────────────────────────────────────────────
_states: dict[str, ConversationState] = {}
_phone_locks: dict[str, threading.Lock] = {}
_phone_locks_guard = threading.Lock()
_ctx = threading.local()


def _get_phone_lock(phone: str) -> threading.Lock:
    with _phone_locks_guard:
        if phone not in _phone_locks:
            _phone_locks[phone] = threading.Lock()
        return _phone_locks[phone]


def _safe_fallback(identifier: str) -> None:
    _clear(identifier)
    wa.send_text_message(identifier, msg_reintentar())


def _get(phone: str) -> ConversationState:
    if phone not in _states:
        _states[phone] = ConversationState()
    return _states[phone]


def _clear(phone: str) -> None:
    _states.pop(phone, None)


def clean_expired_states() -> None:
    """Elimina estados inactivos más de ESTADO_EXPIRACION_MIN minutos y
    purga los limitadores de tasa inactivos. Sin bloqueos de slot ni caché
    de Calendar: este bot no tiene nada de eso (design.md, 5.3)."""
    now = datetime.now(TZ)
    snapshot = list(_states.items())
    expired = [
        p for p, s in snapshot
        if (now - s.last_interaction).total_seconds() > ESTADO_EXPIRACION_MIN * 60
    ]
    for p in expired:
        logger.info("[CONV] Expired state for %s", mask_phone(p))
        _states.pop(p, None)
        with _phone_locks_guard:
            _phone_locks.pop(p, None)

    from app.handlers.webhook import ip_rate_limiter, phone_rate_limiter
    ip_rate_limiter.purge_inactive()
    phone_rate_limiter.purge_inactive()


# ── Punto de entrada ───────────────────────────────────────────────────────


def handle_message(identifier: str, phone: Optional[str], text: Optional[str],
                    interactive_id: Optional[str]) -> None:
    lock = _get_phone_lock(identifier)
    if not lock.acquire(timeout=45):
        logger.warning("[CONV] Phone lock timeout para %s", mask_phone(identifier))
        metrics.inc("phone_lock_timeout")
        wa.send_text_message(identifier, msg_reintentar())
        return
    try:
        wa.begin_delivery_tracking()
        try:
            _process_message(identifier, phone, text, interactive_id)
        except Exception:
            logger.exception(
                "[CONV] Error procesando mensaje de %s", mask_phone(identifier)
            )
            metrics.inc("handler_errors")
            _safe_fallback(identifier)
            return
        if not wa.reply_was_delivered():
            logger.warning(
                "[CONV] Respuesta no entregada a %s; fallback", mask_phone(identifier)
            )
            metrics.inc("reply_delivery_failed")
            _safe_fallback(identifier)
    finally:
        lock.release()


def _process_message(identifier: str, phone: Optional[str], text: Optional[str],
                      interactive_id: Optional[str]) -> None:
    state = _get(identifier)
    state.touch()
    if phone is not None:
        state.phone = phone

    effective_phone = phone or state.phone
    if (text is not None and ADMIN_PHONE and effective_phone == ADMIN_PHONE
            and text.strip().lower() in ADMIN_COMANDOS):
        _handle_admin_command(identifier, text.strip().lower())
        return

    if text == UNKNOWN_INPUT:
        wa.send_text_message(identifier, msg_input_no_soportado())
        return

    value = interactive_id if interactive_id is not None else (text or "")

    # Escape global: palabras que vuelven al menú desde cualquier estado.
    if text is not None and text.strip().lower() in _ESCAPE_MENU:
        flujo.to_menu(identifier, state)
        return

    # Globales: disponibles desde cualquier estado.
    if interactive_id == "menu":
        flujo.to_menu(identifier, state)
        return
    if interactive_id in ("otra_consulta", "menu_horarios"):
        flujo._ir_a_origen(identifier, state)
        return

    handler = flujo.DESPACHO.get(state.step)
    if handler is None:
        flujo.to_menu(identifier, state)
        return
    handler(identifier, state, value)


def _handle_admin_command(identifier: str, cmd: str) -> None:
    if cmd == "/status":
        wa.send_text_message(identifier, build_status_report())
    elif cmd == "/help":
        wa.send_text_message(identifier, build_help_message())
    elif cmd == "/logs":
        wa.send_text_message(identifier, read_log_tail())
    elif cmd == "/restart":
        wa.send_text_message(identifier, "Reiniciando...")
        schedule_restart()
