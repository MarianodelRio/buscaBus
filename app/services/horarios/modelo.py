"""app/services/horarios/modelo.py — entidades inmutables del modelo de horarios.

Ver design.md, sección 2.4. Estos objetos son el resultado de cargar y validar
`horarios/` con `app/services/horarios/formato.py`. No se construyen a mano en
ningún otro sitio.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Zona:
    id: str
    nombre: str


@dataclass(frozen=True)
class Localidad:
    id: str
    nombre: str
    zona: str
    alias: tuple[str, ...] = ()


@dataclass(frozen=True)
class Parada:
    codigo: str
    nombre: str
    localidad: str


@dataclass(frozen=True)
class Observacion:
    id: str
    letra: str | None
    tipo: str  # "condicion" | "aviso"
    ambitos: tuple[str, ...]  # subset of ("parada", "viaje", "linea")
    texto: str


@dataclass(frozen=True)
class Temporada:
    nombre: str
    rango: str  # "DD/MM - DD/MM" o "todo el año", tal como está en el fichero


@dataclass(frozen=True)
class Paso:
    parada: str  # código de parada
    hora: str  # "HH:MM"
    observaciones: tuple[str, ...] = ()  # ids de observaciones de ámbito parada


@dataclass(frozen=True)
class Tabla:
    """Una tabla `horarios:` tal como está escrita en el fichero de línea:
    conserva el sentido y el orden de columnas. La vista de revisión pinta
    una tabla por `Tabla`, nunca mezcla tablas (design.md, 2.4)."""

    linea: str  # id de línea
    temporada: str
    dias: str
    paradas: tuple[str, ...]  # cabecera ordenada, tal cual escrita
    posicion: int  # orden de aparición en el fichero, 0-based


@dataclass(frozen=True)
class Viaje:
    linea: str  # id de línea
    temporada: str
    dias: str  # clave de días de esta tabla concreta
    tabla: Tabla
    observaciones: tuple[str, ...] = ()  # ids de observaciones de ámbito viaje
    pendientes: tuple[str, ...] = ()
    pasos: tuple[Paso, ...] = ()


@dataclass(frozen=True)
class Linea:
    id: str
    nombre: str
    telefono_demanda: str | None
    avisos: tuple[str, ...]
    no_circula: tuple[str, ...]
    temporadas: tuple[Temporada, ...]
    dias: dict[str, dict[str, str]] = field(
        default_factory=dict
    )  # temporada -> {clase: estado}
    pendientes: tuple[str, ...] = ()
    viajes: tuple[Viaje, ...] = ()
    tablas: tuple[Tabla, ...] = ()  # en orden de aparición en el fichero
