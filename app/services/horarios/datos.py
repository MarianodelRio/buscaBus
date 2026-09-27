"""app/services/horarios/datos.py — contenedor de los datos de horarios ya
cargados en memoria (design.md, fase 4).

Aísla el estado global compartido entre los hilos de las peticiones y el
hilo del scheduler: `instalar()`/`actual()` están protegidos por un
`threading.Lock`. Nunca se lee ni se escribe `_actual` directamente fuera de
este módulo.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services.horarios import loader
from app.services.horarios.formato import normalizar
from app.services.horarios.loader import Horarios
from app.utils.matcher import Matcher


@dataclass(frozen=True)
class Datos:
    horarios: Horarios
    matcher: Matcher
    menu_origen: tuple[str, ...]
    cargado: datetime


_lock = threading.Lock()
_actual: Datos | None = None


def cargar(directorio: Path | str, pueblos_menu: list[str]) -> Datos:
    """Carga `horarios/` y resuelve `pueblos_menu` contra las localidades
    reales. Lanza `RuntimeError` con el nombre del pueblo si no se encuentra
    (exacto, sin prefijo ni errata), está duplicado, o no tiene ningún viaje
    en `horarios.localidad_viajes`."""
    horarios = loader.cargar(directorio)
    modelo = horarios.modelo

    # id de localidad por nombre normalizado, para una búsqueda exacta.
    por_nombre: dict[str, str] = {
        normalizar(loc.nombre): lid for lid, loc in modelo.localidades.items()
    }

    menu_ids: list[str] = []
    vistos: set[str] = set()
    for pueblo in pueblos_menu:
        clave = normalizar(pueblo)
        lid = por_nombre.get(clave)
        if lid is None:
            raise RuntimeError(
                f"[DATOS] pueblos_menu_inicio: '{pueblo}' no es una localidad"
                " conocida de horarios/"
            )
        if lid in vistos:
            raise RuntimeError(
                f"[DATOS] pueblos_menu_inicio: '{pueblo}' está duplicado"
            )
        if not horarios.localidad_viajes.get(lid):
            raise RuntimeError(
                f"[DATOS] pueblos_menu_inicio: '{pueblo}' no tiene ningún"
                " viaje en horarios/"
            )
        vistos.add(lid)
        menu_ids.append(lid)

    matcher = Matcher(horarios)
    return Datos(
        horarios=horarios,
        matcher=matcher,
        menu_origen=tuple(menu_ids),
        cargado=datetime.now(),
    )


def instalar(datos: Datos) -> None:
    global _actual
    with _lock:
        _actual = datos


def actual() -> Datos:
    with _lock:
        if _actual is None:
            raise RuntimeError("[DATOS] No hay datos de horarios cargados")
        return _actual


def hay_datos() -> bool:
    with _lock:
        return _actual is not None
