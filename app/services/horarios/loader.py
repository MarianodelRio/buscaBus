"""app/services/horarios/loader.py — carga `horarios/` a memoria al arrancar
el bot (design.md, 2.4), usando el único parser/validador (`formato.py`).

Nunca devuelve datos parciales o ambiguos: si `horarios/` no valida, lanza
`HorariosInvalidos` con la lista completa de errores en vez de devolver un
`Horarios` a medio construir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.horarios import formato
from app.services.horarios.formato import Modelo
from app.services.horarios.modelo import Viaje


class HorariosInvalidos(Exception):
    """`horarios/` no valida. Lleva la lista completa de errores de
    `formato.validar()`."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        mensaje = "\n".join(f"  - {e}" for e in errores)
        super().__init__(f"horarios/ no valida ({len(errores)} error(es)):\n{mensaje}")


@dataclass(frozen=True)
class Horarios:
    """`Modelo` ya validado, más índices de solo lectura precalculados para
    que el motor de consulta (`query.py`) no tenga que recorrer todas las
    líneas en cada consulta."""

    modelo: Modelo
    # localidad -> códigos de parada de esa localidad, en cualquier línea
    localidad_paradas: dict[str, tuple[str, ...]]
    # localidad -> viajes que paran en alguna parada de esa localidad
    localidad_viajes: dict[str, tuple[Viaje, ...]]


def cargar(directorio: Path | str) -> Horarios:
    """Valida `horarios/` y construye `Horarios`. Lanza `HorariosInvalidos`
    si hay algún error; nunca devuelve un resultado parcial."""
    resultado = formato.validar(directorio)
    if resultado.errores:
        raise HorariosInvalidos(resultado.errores)

    modelo = resultado.modelo
    assert modelo is not None

    localidad_paradas: dict[str, set[str]] = {}
    localidad_viajes: dict[str, list[Viaje]] = {}

    for codigo, parada in modelo.paradas.items():
        localidad_paradas.setdefault(parada.localidad, set()).add(codigo)

    for linea in modelo.lineas.values():
        for viaje in linea.viajes:
            localidades_del_viaje: set[str] = set()
            for paso in viaje.pasos:
                parada = modelo.paradas.get(paso.parada)
                if parada is not None:
                    localidades_del_viaje.add(parada.localidad)
            for localidad_id in localidades_del_viaje:
                localidad_viajes.setdefault(localidad_id, []).append(viaje)

    return Horarios(
        modelo=modelo,
        localidad_paradas={
            lid: tuple(sorted(codigos)) for lid, codigos in localidad_paradas.items()
        },
        localidad_viajes={
            lid: tuple(viajes) for lid, viajes in localidad_viajes.items()
        },
    )
