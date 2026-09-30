# config.py
"""Constantes + carga y validación de config.yaml (design.md, 5.2).

A diferencia de Peluquería, el arranque falla si falta WHATSAPP_APP_SECRET
(design.md, 6.4): aquí no hay un modo "verificación HMAC desactivada".
"""
import logging
import os
import re

import yaml
from dotenv import load_dotenv

from app.services.horarios.formato import normalizar

load_dotenv()

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# Días válidos de `negocio.horario_oficina` (sin tildes, como en horarios/).
DIAS_OFICINA_VALIDOS = (
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
)


def _ranges_overlap(ranges: list) -> bool:
    """Return True if any two ranges in the list overlap."""

    def to_min(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    parsed = [(to_min(r[0]), to_min(r[1])) for r in ranges]
    parsed.sort()
    for i in range(len(parsed) - 1):
        if parsed[i][1] > parsed[i + 1][0]:
            return True
    return False


def _load_and_validate_yaml(path: str) -> dict:
    """
    Load and validate config.yaml. Raises RuntimeError with a descriptive
    message on any failure. Returns the validated dict on success.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        raise RuntimeError(
            f"[CONFIG] Cannot load config.yaml: file not found at '{path}'"
        )
    except yaml.YAMLError as exc:
        raise RuntimeError(f"[CONFIG] Cannot load config.yaml: invalid YAML — {exc}")
    except Exception as exc:
        raise RuntimeError(f"[CONFIG] Cannot load config.yaml: {exc}")

    if not isinstance(cfg, dict):
        raise RuntimeError(
            "[CONFIG] config.yaml must be a YAML mapping at the top level"
        )

    # Rule: negocio.nombre / negocio.telefono_contacto non-empty strings
    negocio = cfg.get("negocio")
    if not isinstance(negocio, dict):
        raise RuntimeError("[CONFIG] Rule: 'negocio' must be a mapping")
    if not isinstance(negocio.get("nombre"), str) or not negocio["nombre"].strip():
        raise RuntimeError(
            "[CONFIG] Rule: 'negocio.nombre' must be a non-empty string"
        )
    if (
        not isinstance(negocio.get("telefono_contacto"), str)
        or not negocio["telefono_contacto"].strip()
    ):
        raise RuntimeError(
            "[CONFIG] Rule: 'negocio.telefono_contacto' must be a non-empty string"
        )

    # Rule: negocio.horario_oficina — non-empty list of blocks
    # {dias: [...], franjas: [[HH:MM, HH:MM], ...]}. Days valid and in at
    # most one block; per franja start < end; no overlaps within a block.
    horario = negocio.get("horario_oficina")
    if not isinstance(horario, list) or len(horario) == 0:
        raise RuntimeError(
            "[CONFIG] Rule: 'negocio.horario_oficina' must be a non-empty list"
            " of blocks {dias, franjas}"
        )
    dias_vistos: set[str] = set()
    for bloque in horario:
        if not (
            isinstance(bloque, dict) and set(bloque.keys()) == {"dias", "franjas"}
        ):
            raise RuntimeError(
                "[CONFIG] Rule: each block in 'negocio.horario_oficina' must"
                " be a mapping with exactly 'dias' and 'franjas'"
            )
        dias = bloque["dias"]
        if not isinstance(dias, list) or len(dias) == 0:
            raise RuntimeError(
                "[CONFIG] Rule: 'dias' of a block in 'negocio.horario_oficina'"
                " must be a non-empty list"
            )
        for dia in dias:
            if dia not in DIAS_OFICINA_VALIDOS:
                raise RuntimeError(
                    f"[CONFIG] Rule: invalid day '{dia}' in"
                    f" 'negocio.horario_oficina' (valid: "
                    f"{', '.join(DIAS_OFICINA_VALIDOS)})"
                )
            if dia in dias_vistos:
                raise RuntimeError(
                    f"[CONFIG] Rule: day '{dia}' appears more than once in"
                    " 'negocio.horario_oficina'"
                )
            dias_vistos.add(dia)
        franjas = bloque["franjas"]
        if not isinstance(franjas, list) or len(franjas) == 0:
            raise RuntimeError(
                "[CONFIG] Rule: 'franjas' of a block in"
                " 'negocio.horario_oficina' must be a non-empty list of"
                " ranges"
            )
        for rng in franjas:
            if not (isinstance(rng, list) and len(rng) == 2):
                raise RuntimeError(
                    "[CONFIG] Rule: each range in 'negocio.horario_oficina'"
                    " must be a 2-element list [inicio, fin]"
                )
            inicio, fin = rng
            if not (_TIME_RE.match(str(inicio)) and _TIME_RE.match(str(fin))):
                raise RuntimeError(
                    "[CONFIG] Rule: range values in 'negocio.horario_oficina'"
                    " must be 'HH:MM' strings"
                )
            if fin <= inicio:
                raise RuntimeError(
                    f"[CONFIG] Rule: 'negocio.horario_oficina' has range where"
                    f" fin ('{fin}') <= inicio ('{inicio}')"
                )
        if len(franjas) > 1 and _ranges_overlap(franjas):
            raise RuntimeError(
                "[CONFIG] Rule: 'negocio.horario_oficina' has overlapping time"
                " ranges within a block"
            )

    # Rule: negocio.enlaces — map of strings (empty values allowed)
    enlaces = negocio.get("enlaces")
    if enlaces is None:
        enlaces = {}
    if not isinstance(enlaces, dict):
        raise RuntimeError("[CONFIG] Rule: 'negocio.enlaces' must be a mapping")
    for key, val in enlaces.items():
        if not isinstance(val, str):
            raise RuntimeError(
                f"[CONFIG] Rule: 'negocio.enlaces.{key}' must be a string"
                " (empty string allowed)"
            )

    # Rule: pueblos_menu_inicio — list of 1-8 non-empty strings, no
    # duplicates after formato.normalizar
    pueblos = cfg.get("pueblos_menu_inicio")
    if not isinstance(pueblos, list) or not (1 <= len(pueblos) <= 8):
        raise RuntimeError(
            "[CONFIG] Rule: 'pueblos_menu_inicio' must be a list of 1 to 8 entries"
        )
    vistos: set[str] = set()
    for pueblo in pueblos:
        if not isinstance(pueblo, str) or not pueblo.strip():
            raise RuntimeError(
                "[CONFIG] Rule: every entry in 'pueblos_menu_inicio' must be a"
                " non-empty string"
            )
        clave = normalizar(pueblo)
        if clave in vistos:
            raise RuntimeError(
                f"[CONFIG] Rule: 'pueblos_menu_inicio' has a duplicate entry"
                f" (normalized): '{pueblo}'"
            )
        vistos.add(clave)

    # Rule: negocio.admin_phone, if present, must be a string of 7-15 digits
    admin_phone_raw = negocio.get("admin_phone")
    if admin_phone_raw:
        if not isinstance(admin_phone_raw, str) or not re.fullmatch(
            r"\d{7,15}", admin_phone_raw
        ):
            raise RuntimeError(
                "[CONFIG] Rule: 'negocio.admin_phone' must be a string of"
                " 7-15 digits (no '+', no spaces, no dashes)"
            )

    return cfg


# ── Load YAML config ───────────────────────────────────────────────────────
_CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yaml")
_cfg = _load_and_validate_yaml(_CONFIG_PATH)

# ── Business constants from YAML ───────────────────────────────────────────
NEGOCIO_NOMBRE: str = _cfg["negocio"]["nombre"]
NEGOCIO_TELEFONO: str = _cfg["negocio"]["telefono_contacto"]
# Lista de bloques (dias, franjas): dias es una tupla de días, franjas una
# tupla de (inicio, fin) "HH:MM". Solo para mostrar; nunca se calcula
# abierto/cerrado.
NEGOCIO_HORARIO_OFICINA: list = [
    (tuple(b["dias"]), tuple(tuple(f) for f in b["franjas"]))
    for b in _cfg["negocio"]["horario_oficina"]
]
NEGOCIO_ENLACES: dict = dict(_cfg["negocio"].get("enlaces") or {})

PUEBLOS_MENU_INICIO: list = list(_cfg["pueblos_menu_inicio"])

# ── Admin commands ────────────────────────────────────────────────────────
ADMIN_PHONE: str = (
    os.getenv("ADMIN_PHONE") or _cfg["negocio"].get("admin_phone") or ""
)
ADMIN_COMANDOS: frozenset = frozenset({"/status", "/help", "/logs", "/restart"})
LOG_FILE: str = os.getenv("LOG_FILE", "")

# ── WhatsApp credentials ───────────────────────────────────────────────────
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

# ── Timezone ───────────────────────────────────────────────────────────────
TIMEZONE = "Europe/Madrid"

# ── Conversation state ─────────────────────────────────────────────────────
ESTADO_EXPIRACION_MIN = 30
LIMPIAR_ESTADOS_INTERVAL_MIN = 10

# ── Concurrency ────────────────────────────────────────────────────────────
MAX_CONCURRENT_HANDLERS = 40

# ── HTTP / API timeouts ────────────────────────────────────────────────────
HTTP_TIMEOUT_SEC = 10

# ── Horarios data ───────────────────────────────────────────────────────────
HORARIOS_DIR = os.getenv("HORARIOS_DIR", "horarios")

# ── Conversation / interactive constants ───────────────────────────────────
DIAS_LISTA = 7
MAX_FILAS_LISTA = 10
MAX_BOTONES = 3
MAX_TITULO_FILA = 24
MAX_TITULO_BOTON = 20
MAX_DESCRIPCION_FILA = 72
MAX_TEXTO = 4096
# A diferencia de Peluquería, el texto libre no siempre vuelve al menú (hay
# pasos de texto libre válidos), así que el footer no puede decir eso.
INTERACTIVE_FOOTER = "Autocares · Horarios de autobús"


def validate_config() -> None:
    """
    Validate required environment variables at startup.
    Raises RuntimeError if any critical variable is missing.
    A diferencia de Peluquería, WHATSAPP_APP_SECRET es obligatorio: el
    arranque falla si falta, no solo un aviso (design.md, 6.4).
    """
    _log = logging.getLogger(__name__)
    critical = {
        "WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID,
        "WHATSAPP_ACCESS_TOKEN": WHATSAPP_ACCESS_TOKEN,
        "WHATSAPP_VERIFY_TOKEN": WHATSAPP_VERIFY_TOKEN,
        "WHATSAPP_APP_SECRET": WHATSAPP_APP_SECRET,
        "ADMIN_PHONE": ADMIN_PHONE,
    }
    missing = [name for name, val in critical.items() if not val]
    if missing:
        raise RuntimeError(f"[CONFIG] Missing required env vars: {', '.join(missing)}")
    _log.info("[CONFIG] Validation OK")
