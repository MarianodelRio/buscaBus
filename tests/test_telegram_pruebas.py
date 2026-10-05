# tests/test_telegram_pruebas.py
"""Canal de pruebas por Telegram (solo rama pruebas-telegram). Sin red ni
token real: httpx simulado."""
import importlib
import logging

import httpx
import pytest

from app.handlers.conversation import UNKNOWN_INPUT
from app.services import whatsapp as wa
from app.services.horarios import datos as horarios_datos
from app.utils import matcher
from app.utils.interactive import (
    build_confirmar,
    build_destinos,
    build_dias,
    build_linea,
    build_lineas,
    build_localidad_pendiente,
    build_menu,
    build_origen,
    build_resultado,
)
from tools import telegram_pruebas as tg

TOKEN = "123456:SECRET-TOKEN-XYZ"
NOMBRE_LARGO = "Villanueva de la Serena del Norte"  # > 24 caracteres


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeClient:
    """Responde con lo guionizado: dict -> JSON, Exception -> se lanza.
    Agotado el guion, responde ok con result vacio."""

    def __init__(self, script=None, on_empty=None):
        self.script = list(script or [])
        self.calls = []
        self.on_empty = on_empty

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.script:
            item = self.script.pop(0)
        else:
            if self.on_empty:
                self.on_empty()
            item = {"ok": True, "result": []}
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    def metodos(self):
        return [u.rsplit("/", 1)[1] for u, _ in self.calls]


OK = {"ok": True, "result": {"message_id": 1}}


def _ejemplos_reales():
    """Un mensaje de cada constructor, con ids reales de horarios/."""
    datos = horarios_datos.actual()
    modelo = datos.horarios.modelo
    locs = [(lid, modelo.localidades[lid].nombre)
            for lid in list(modelo.localidades)[:9]]
    lineas = matcher.lineas(datos.horarios)
    linea0, pueblos0 = lineas[0]
    return {
        "menu": build_menu(),
        "origen": build_origen(locs[:8], con_lineas=True),
        "destinos": build_destinos("Origen", locs, con_lineas=False),
        "dias": build_dias("A", "B", [
            ("dia:2026-10-05", "Hoy lunes", "lunes 5 de octubre"),
            ("dia:2026-10-06", "Mañana martes", "martes 6 de octubre"),
        ]),
        "lineas": build_lineas([(ln, len(ps)) for ln, ps in lineas[:8]], 0,
                               len(lineas) > 8, "origen"),
        "linea": build_linea(linea0, [(p.id, p.nombre) for p in pueblos0[:8]],
                             0, len(pueblos0) > 8),
        "resultado": build_resultado("Salidas...", [("menu", "Menu"),
                                                    ("vuelta", "Vuelta")]),
        "confirmar": build_confirmar("Pozoblanco"),
        "pendiente": build_localidad_pendiente(
            "No hay hora", "pozoblanco", "Pozoblanco", "origen"),
    }


# ── traducir ────────────────────────────────────────────────────────────


def test_traducir_cabecera_primero_sin_pie():
    texto, _ = tg.traducir(build_menu())
    assert texto.startswith("🚌 Autocares · Horarios\n\n¿Qué necesitas?")
    assert "Footer" not in texto
    from app.config import INTERACTIVE_FOOTER
    if INTERACTIVE_FOOTER:
        assert INTERACTIVE_FOOTER not in texto


def test_traducir_botones_un_boton_por_fila():
    _, markup = tg.traducir(build_menu())
    assert markup == {"inline_keyboard": [
        [{"text": "🚌 Ver horarios", "callback_data": "menu_horarios"}],
        [{"text": "ℹ️ Contacto", "callback_data": "menu_info"}],
    ]}


def test_traducir_lista_orden_y_una_por_fila(_datos_cargados):
    locs = [("a", "Alfa"), ("b", "Beta"), ("c", "Gamma")]
    payload = build_origen(locs)
    _, markup = tg.traducir(payload)
    ids = [fila[0]["callback_data"] for fila in markup["inline_keyboard"]]
    assert ids == ["loc:a", "loc:b", "loc:c", "escribir", "menu"]
    assert all(len(fila) == 1 for fila in markup["inline_keyboard"])


def test_traducir_titulo_truncado_muestra_nombre_completo():
    payload = build_origen([("x", NOMBRE_LARGO)])
    fila = payload["interactive"]["action"]["sections"][0]["rows"][0]
    assert fila["title"] != NOMBRE_LARGO  # el constructor lo trunca
    texto, markup = tg.traducir(payload)
    assert markup["inline_keyboard"][0][0]["text"] == NOMBRE_LARGO
    assert f"{fila['title']}: " not in texto  # no se duplica en el texto


def test_traducir_descripcion_de_dias_en_el_texto():
    payload = build_dias("A", "B", [
        ("dia:2026-10-05", "Hoy lunes", "lunes 5 de octubre"),
    ])
    texto, markup = tg.traducir(payload)
    assert "Hoy lunes: lunes 5 de octubre" in texto
    assert markup["inline_keyboard"][0][0]["text"] == "Hoy lunes"
    assert texto.index("¿Qué día viajas?") < texto.index("Hoy lunes: ")


def test_traducir_limites_con_constructores_reales():
    for nombre, payload in _ejemplos_reales().items():
        texto, markup = tg.traducir(payload)
        assert len(texto) <= 4096, nombre
        if markup:
            for fila in markup["inline_keyboard"]:
                for b in fila:
                    assert len(b["text"]) <= 64, nombre
                    assert len(b["callback_data"].encode("utf-8")) <= 64, nombre


def test_traducir_todos_los_ids_reales_caben_en_64_bytes():
    modelo = horarios_datos.actual().horarios.modelo
    ids = [f"loc:{lid}" for lid in modelo.localidades]
    ids += [f"usar:{lid}" for lid in modelo.localidades]
    ids += [f"linea:{lid}:99" for lid in modelo.lineas]
    for id_ in ids:
        assert len(id_.encode("utf-8")) <= 64, id_


def test_traducir_texto_largo_se_recorta_a_4096():
    texto, _ = tg.traducir(build_resultado("x" * 6000, [("menu", "Menu")]))
    assert len(texto) == 4096


def test_traducir_callback_demasiado_largo_se_omite_y_se_registra(caplog):
    payload = build_resultado("hola", [("a" * 65, "Largo"), ("menu", "Menu")])
    with caplog.at_level(logging.ERROR):
        _, markup = tg.traducir(payload)
    assert [f[0]["callback_data"] for f in markup["inline_keyboard"]] == ["menu"]
    assert any("callback_data" in r.getMessage() for r in caplog.records)


# ── procesar_update ─────────────────────────────────────────────────────


@pytest.fixture
def llamadas(monkeypatch):
    registro = []
    monkeypatch.setattr(
        tg, "handle_message",
        lambda ident, phone, text, iid: registro.append((ident, phone, text, iid)),
    )
    return registro


def _msg(text=None, chat_type="private", **extra):
    m = {"chat": {"id": 42, "type": chat_type}, **extra}
    if text is not None:
        m["text"] = text
    return {"update_id": 1, "message": m}


def test_update_texto(llamadas):
    tg.procesar_update(_msg("  Pozoblanco  "), FakeClient(), TOKEN)
    assert llamadas == [("42", None, "Pozoblanco", None)]


def test_update_start(llamadas):
    tg.procesar_update(_msg("/start"), FakeClient(), TOKEN)
    tg.procesar_update(_msg("/start xyz"), FakeClient(), TOKEN)
    assert llamadas == [("42", None, "menu", None)] * 2


def test_update_texto_se_recorta_a_4096(llamadas):
    tg.procesar_update(_msg("a" * 5000), FakeClient(), TOKEN)
    assert len(llamadas[0][2]) == 4096


def test_update_sin_texto_es_desconocido(llamadas):
    tg.procesar_update(_msg(photo=[{"file_id": "x"}]), FakeClient(), TOKEN)
    assert llamadas == [("42", None, UNKNOWN_INPUT, None)]


def test_update_grupo_ignorado(llamadas):
    tg.procesar_update(_msg("hola", chat_type="group"), FakeClient(), TOKEN)
    assert llamadas == []


def test_update_otros_tipos_ignorados(llamadas):
    tg.procesar_update({"update_id": 1, "edited_message": {}}, FakeClient(), TOKEN)
    assert llamadas == []


def test_callback_responde_primero_y_luego_procesa(llamadas):
    client = FakeClient([OK])
    orden = []
    original = tg.handle_message
    tg.handle_message = lambda *a: orden.append(client.metodos())
    try:
        update = {"update_id": 2, "callback_query": {
            "id": "cb1", "data": "loc:pozoblanco",
            "message": {"chat": {"id": 42, "type": "private"}},
        }}
        tg.procesar_update(update, client, TOKEN)
    finally:
        tg.handle_message = original
    assert orden == [["answerCallbackQuery"]]
    assert client.calls[0][1] == {"callback_query_id": "cb1"}


def test_callback_sin_datos_o_en_grupo_solo_responde(llamadas):
    client = FakeClient()
    base = {"id": "cb", "message": {"chat": {"id": 1, "type": "group"}},
            "data": "menu"}
    tg.procesar_update({"callback_query": base}, client, TOKEN)
    sin_data = {"id": "cb", "message": {"chat": {"id": 1, "type": "private"}}}
    tg.procesar_update({"callback_query": sin_data}, client, TOKEN)
    sin_msg = {"id": "cb", "data": "menu"}
    tg.procesar_update({"callback_query": sin_msg}, client, TOKEN)
    assert client.metodos() == ["answerCallbackQuery"] * 3
    assert llamadas == []


def test_callback_procesa_con_data(llamadas):
    update = {"callback_query": {
        "id": "cb1", "data": "menu",
        "message": {"chat": {"id": 7, "type": "private"}},
    }}
    tg.procesar_update(update, FakeClient(), TOKEN)
    assert llamadas == [("7", None, None, "menu")]


# ── envios y seguimiento de entrega ──────────────────────────────────────


@pytest.fixture
def entrega():
    wa.begin_delivery_tracking()
    yield
    wa.begin_delivery_tracking()


def test_entrega_falla_con_error_de_telegram(entrega):
    client = FakeClient([{"ok": False, "error_code": 400,
                          "description": "Bad Request"}])
    assert tg.tg_send_text_message(client, TOKEN, "42", "hola") is False
    assert wa.reply_was_delivered() is False


def test_entrega_ok(entrega):
    client = FakeClient([OK])
    assert tg.tg_send_text_message(client, TOKEN, "42", "hola") is True
    assert wa.reply_was_delivered() is True
    assert client.calls[0][1] == {"chat_id": "42", "text": "hola",
                                  "link_preview_options": {"is_disabled": True}}


def test_interactive_envia_texto_y_teclado(entrega):
    client = FakeClient([OK])
    assert tg.tg_send_interactive(client, TOKEN, "42", build_menu()) is True
    cuerpo = client.calls[0][1]
    assert cuerpo["chat_id"] == "42"
    assert "parse_mode" not in cuerpo
    assert cuerpo["link_preview_options"] == {"is_disabled": True}
    assert len(cuerpo["reply_markup"]["inline_keyboard"]) == 2
    assert wa.reply_was_delivered() is True


def test_template_no_soportada(entrega, caplog):
    with caplog.at_level(logging.WARNING):
        assert tg.tg_send_template("42", "t", "es", []) is False
    assert wa.reply_was_delivered() is False
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_importar_no_cambia_los_envios_de_whatsapp():
    antes = (wa.send_text_message, wa.send_interactive, wa.send_template)
    importlib.reload(tg)
    assert (wa.send_text_message, wa.send_interactive,
            wa.send_template) == antes


def test_token_no_aparece_en_logs_con_error_de_red(caplog):
    url = tg._API.format(token=TOKEN, method="sendMessage")
    error = httpx.ConnectError(f"fallo conectando a {url}")
    client = FakeClient([error, error])
    with caplog.at_level(logging.DEBUG):
        assert tg.tg_send_text_message(client, TOKEN, "42", "hola") is False
        assert tg._api(client, TOKEN, "getUpdates") is None
    assert caplog.records
    for r in caplog.records:
        assert TOKEN not in r.getMessage()
        assert TOKEN not in str(r.args)
        assert TOKEN not in (r.exc_text or "")
        assert r.exc_info is None
    assert "ConnectError" in caplog.text


def test_logging_deja_httpx_en_warning(monkeypatch):
    root = logging.getLogger()
    nombres = ["httpx", "httpcore"]
    niveles = {n: logging.getLogger(n).level for n in nombres}
    handlers = list(root.handlers)
    nivel_root = root.level
    try:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        tg._configurar_logging()
        for n in nombres:
            assert logging.getLogger(n).level == logging.WARNING
        assert root.level == logging.DEBUG
    finally:
        for h in list(root.handlers):
            if h not in handlers:
                root.removeHandler(h)
        root.setLevel(nivel_root)
        for n, nivel in niveles.items():
            logging.getLogger(n).setLevel(nivel)


def test_logging_nivel_invalido_usa_info(monkeypatch, capsys):
    root = logging.getLogger()
    handlers = list(root.handlers)
    nivel_root = root.level
    try:
        monkeypatch.setenv("LOG_LEVEL", "NOPE")
        tg._configurar_logging()
        assert root.level == logging.INFO
    finally:
        for h in list(root.handlers):
            if h not in handlers:
                root.removeHandler(h)
        root.setLevel(nivel_root)
        logging.getLogger("httpx").setLevel(logging.NOTSET)
        logging.getLogger("httpcore").setLevel(logging.NOTSET)


# ── arranque y polling ───────────────────────────────────────────────────


def test_main_sin_token_sale_con_error(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        tg.main()
    assert exc.value.code != 0
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def _parada_tras(n, client):
    """stop() que corta cuando el cliente ha recibido n llamadas."""
    return lambda: len(client.calls) >= n


def test_polling_el_offset_avanza_aunque_falle_el_proceso(monkeypatch):
    update = {"update_id": 10, "message": {"chat": {"id": 1, "type": "private"},
                                           "text": "hola"}}
    client = FakeClient([{"ok": True, "result": [update]}])
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)

    def falla(*a, **k):
        raise RuntimeError("fallo del manejador")

    monkeypatch.setattr(tg, "procesar_update", falla)
    tg.bucle(client, TOKEN, stop=_parada_tras(2, client))
    assert "offset" not in client.calls[0][1]
    assert client.calls[1][1]["offset"] == 11
    assert client.calls[1][1]["allowed_updates"] == ["message", "callback_query"]


def test_polling_error_de_red_reintenta(monkeypatch):
    esperas = []
    monkeypatch.setattr(tg.time, "sleep", lambda s: esperas.append(s))
    client = FakeClient([httpx.ReadTimeout("x"), {"ok": False,
                                                  "error_code": 502}])
    tg.bucle(client, TOKEN, stop=_parada_tras(3, client))
    assert esperas == [3, 3]
    assert len(client.calls) == 3
