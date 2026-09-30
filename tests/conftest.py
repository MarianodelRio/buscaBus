# tests/conftest.py
"""Fixtures compartidas. Todas las APIs externas (WhatsApp) están simuladas;
no hacen falta credenciales reales."""
import hashlib
import hmac as _hmac
import itertools
import json
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.config import HORARIOS_DIR, PUEBLOS_MENU_INICIO
from app.services.horarios import datos as horarios_datos

TZ = ZoneInfo("Europe/Madrid")
TEST_APP_SECRET = "test-secret-buscabus"

# ── Webhook payload builder ─────────────────────────────────────────────

_msg_id_counter = itertools.count(1)

_BUTTON_PREFIXES = ("menu", "otra_", "si", "no", "cambiar_origen", "escribir",
                    "lineas:", "linea:", "vuelta", "otro_dia")


def make_payload(phone: str, *, text: str | None = None,
                  interactive_id: str | None = None,
                  user_id: str = "") -> dict:
    """Build a Meta webhook payload for a single message.

    Uses list_reply for ids that clearly come from a list row (loc:, dia:)
    and button_reply for everything else — the distinction does not matter
    to the webhook parser, which reads the same "id" field either way.
    """
    msg_id = f"test_msg_{next(_msg_id_counter)}"
    msg: dict = {"from": phone, "id": msg_id, "user_id": user_id}
    if text is not None:
        msg["type"] = "text"
        msg["text"] = {"body": text}
    elif interactive_id is not None:
        if interactive_id.startswith("loc:") or interactive_id.startswith("dia:") \
                or interactive_id.startswith("zona:"):
            itype = "list_reply"
        else:
            itype = "button_reply"
        msg["type"] = "interactive"
        msg["interactive"] = {"type": itype, itype: {"id": interactive_id}}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def sign_body(body: dict) -> tuple[bytes, str]:
    """Return (raw_body_bytes, X-Hub-Signature-256 header value) signed with
    TEST_APP_SECRET, for posting to /webhook."""
    raw = json.dumps(body).encode("utf-8")
    sig = _hmac.new(TEST_APP_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={sig}"


# ── Datetime helpers ────────────────────────────────────────────────────

def aware_dt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _app_secret(monkeypatch):
    """A diferencia de Peluquería, WHATSAPP_APP_SECRET es obligatorio: los
    tests firman sus payloads con TEST_APP_SECRET en vez de desactivar la
    verificación."""
    monkeypatch.setattr("app.handlers.webhook.WHATSAPP_APP_SECRET", TEST_APP_SECRET)


@pytest.fixture(autouse=True)
def _datos_cargados():
    """Instala los datos de horarios reales (con los 8 pueblos de
    `pueblos_menu_inicio`, verificados en fase 4) antes de cada test, y los
    limpia después."""
    d = horarios_datos.cargar(HORARIOS_DIR, PUEBLOS_MENU_INICIO)
    horarios_datos.instalar(d)
    yield d
    horarios_datos._actual = None


@pytest.fixture
def datos_motor():
    """Instala los datos sintéticos de `tests/fixtures/horarios_motor/`
    (fase 2, ya usados por `test_query.py`), para probar en la conversación
    los casos borde de 4.8 que `horarios/` real no cubre con comodidad
    (sin_datos, sin_servicio largo, a demanda, viernes lectivo, fusión).
    Restaura los datos anteriores (los de `_datos_cargados`) al terminar."""
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "fixtures" / "horarios_motor"
    pueblos = ["Pueblo A", "Pueblo E", "Pueblo K", "Pueblo N"]
    d = horarios_datos.cargar(fixtures_dir, pueblos)
    anterior = horarios_datos._actual
    horarios_datos.instalar(d)
    yield d
    if anterior is not None:
        horarios_datos.instalar(anterior)
    else:
        horarios_datos._actual = None


@pytest.fixture
def datos_pendientes():
    """Instala los datos sintéticos de `tests/fixtures/horarios_pendientes/`
    (ciclo C2: localidades pendientes, P15/P32). Restaura los datos
    anteriores al terminar."""
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "fixtures" / "horarios_pendientes"
    d = horarios_datos.cargar(fixtures_dir, ["Pueblo A", "Pueblo B"])
    anterior = horarios_datos._actual
    horarios_datos.instalar(d)
    yield d
    if anterior is not None:
        horarios_datos.instalar(anterior)
    else:
        horarios_datos._actual = None


def crear_horarios_muchas_lineas(directorio) -> None:
    """Genera un `horarios/` sintético para probar la paginación de la lista de
    líneas (P18): 12 líneas desde un mismo origen ("Origen"); "Linea Larga"
    pasa por 18 pueblos y "Ruta muy larga del norte al sur de la sierra" (más
    de 24 caracteres) lleva `nombre_corto: Ruta del norte`."""
    from pathlib import Path

    directorio = Path(directorio)
    (directorio / "lineas").mkdir(parents=True, exist_ok=True)

    def codigo(i: int) -> str:
        return f"{chr(65 + i // 26)}{chr(65 + i % 26)}Z"

    lineas: list[tuple[str, str, str | None, int]] = []
    for n in range(1, 11):
        lineas.append((f"linea-{n:02d}", f"Linea {n:02d}", None, 1))
    lineas.append(("linea-larga", "Linea Larga", None, 18))
    lineas.append(
        (
            "ruta-norte",
            "Ruta muy larga del norte al sur de la sierra",
            "Ruta del norte",
            2,
        )
    )
    localidades = ["  origen: { nombre: Origen }"]
    paradas = ["  ORI: { nombre: Origen, localidad: origen }"]
    contador = 0
    for lid, nombre, corto, n_pueblos in lineas:
        cabecera = ["ORI"]
        horas = ["08:00"]
        for k in range(n_pueblos):
            contador += 1
            pid = f"aldea-{contador:02d}"
            localidades.append(f"  {pid}: {{ nombre: Aldea {contador:02d} }}")
            paradas.append(
                f"  {codigo(contador)}: {{ nombre: Aldea {contador:02d}, "
                f"localidad: {pid} }}"
            )
            cabecera.append(codigo(contador))
            horas.append(f"{8 + (k + 1) * 5 // 60:02d}:{(k + 1) * 5 % 60:02d}")
        texto = f"nombre: {nombre}\n"
        if corto:
            texto += f"nombre_corto: {corto}\n"
        texto += (
            "avisos: []\nno_circula: []\n\n"
            "temporadas:\n  anual: todo el año\n\n"
            "dias:\n  anual: { lunes-viernes: horario, sabado: sin_servicio, "
            "domingos-festivos: sin_servicio }\n\n"
            "horarios:\n  - temporada: anual\n    dias: lunes-viernes\n"
            "    tabla: |\n"
            f"      {'  '.join(cabecera)}\n"
            f"      {'  '.join(horas)}\n\n"
            "pendientes: []\n"
        )
        (directorio / "lineas" / f"{lid}.yaml").write_text(texto, encoding="utf-8")
    (directorio / "paradas.yaml").write_text(
        "localidades:\n" + "\n".join(localidades) + "\n\nparadas:\n"
        + "\n".join(paradas) + "\n",
        encoding="utf-8",
    )
    (directorio / "observaciones.yaml").write_text("{}\n", encoding="utf-8")
    (directorio / "calendario.yaml").write_text(
        "vigencia: 01/01/2026 - 31/08/2027\n\nfestivos:\n"
        "  01/01/2026: Año Nuevo\n\ncurso:\n  inicio_clases: 01/09/2026\n"
        "  fin_clases: 30/06/2027\n  vacaciones:\n"
        "    - 23/12/2026 - 07/01/2027\n  no_lectivos: []\n\npendientes: []\n",
        encoding="utf-8",
    )


@pytest.fixture
def datos_muchas_lineas(tmp_path):
    """Instala el `horarios/` sintético de `crear_horarios_muchas_lineas`.
    Restaura los datos anteriores al terminar."""
    crear_horarios_muchas_lineas(tmp_path)
    d = horarios_datos.cargar(tmp_path, ["Origen"])
    anterior = horarios_datos._actual
    horarios_datos.instalar(d)
    yield d
    if anterior is not None:
        horarios_datos.instalar(anterior)
    else:
        horarios_datos._actual = None


@pytest.fixture
def mock_wa():
    """Patch all WhatsApp send functions to no-ops returning True."""
    with patch("app.services.whatsapp.send_text_message", return_value=True) as txt, \
         patch("app.services.whatsapp.send_interactive", return_value=True) as inter, \
         patch("app.services.whatsapp.send_template", return_value=True) as tmpl:
        yield {"text": txt, "interactive": inter, "template": tmpl}


@pytest.fixture
def freeze_calendario(monkeypatch):
    """Fija `calendario.hoy()`/`calendario.ahora()` tal como se llaman desde
    `app.handlers.flujo`, para que los tests de conversación sean
    deterministas."""

    def _apply(fecha: date, hora=None):
        hora = hora or (0, 0)
        fake_ahora = datetime(fecha.year, fecha.month, fecha.day, *hora, tzinfo=TZ)

        def _hoy(tz="Europe/Madrid"):
            return fecha

        def _ahora(tz="Europe/Madrid"):
            return fake_ahora

        monkeypatch.setattr("app.handlers.flujo.calendario.hoy", _hoy)
        monkeypatch.setattr("app.handlers.flujo.calendario.ahora", _ahora)
        return fake_ahora

    return _apply
