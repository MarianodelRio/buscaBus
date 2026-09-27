"""app/services/horarios/query.py — motor de consulta (design.md, sección 3).

Puro: no hace E/S ni lee el reloj. `ahora` siempre se recibe como parámetro
(nunca `datetime.now()` dentro de este módulo), para que las pruebas sean
deterministas y para no acoplar el motor a una zona horaria concreta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from app.services.horarios import calendario as calendario_servicio
from app.services.horarios import formato
from app.services.horarios.calendario import InfoDia
from app.services.horarios.loader import Horarios
from app.services.horarios.modelo import Linea, Temporada, Viaje

# Número de días hacia delante en los que se busca la siguiente fecha con
# servicio cuando la fecha pedida no tiene salidas (design.md, sección 3).
SIGUIENTE_CON_SERVICIO_DIAS = 7

EstadoConsulta = Literal["con_salidas", "sin_servicio", "sin_datos", "sin_trayecto"]


@dataclass(frozen=True)
class Salida:
    hora_salida: time
    hora_llegada: time
    duracion_min: int
    parada_origen: str
    parada_destino: str
    lineas: tuple[str, ...]
    notas: tuple[str, ...] = ()
    ya_salio: bool = False


@dataclass(frozen=True)
class Consulta:
    estado: EstadoConsulta
    salidas: tuple[Salida, ...]
    info_dia: InfoDia | None
    temporadas: tuple[tuple[str, Temporada], ...]
    lineas_sin_datos: tuple[str, ...]
    fuera_de_calendario: bool
    siguiente_con_servicio: date | None


def _parse_hora(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def _localidades_del_viaje(horarios: Horarios, viaje: Viaje) -> list[str]:
    modelo = horarios.modelo
    localidades = []
    for paso in viaje.pasos:
        parada = modelo.paradas.get(paso.parada)
        localidades.append(parada.localidad if parada is not None else None)
    return localidades


def _emparejar(
    horarios: Horarios, viaje: Viaje, origen: str, destino: str
) -> tuple[int, int] | None:
    """Índice del paso de origen y de destino en `viaje.pasos` para el par
    (origen, destino), o None si el viaje no los conecta en ese sentido.

    La parada de destino es la PRIMERA de la localidad de destino en el
    orden del viaje; la de origen es la ÚLTIMA de la localidad de origen
    antes de esa parada de destino (el tramo más corto posible)."""
    modelo = horarios.modelo
    idx_destino = None
    for i, paso in enumerate(viaje.pasos):
        parada = modelo.paradas.get(paso.parada)
        if parada is not None and parada.localidad == destino:
            idx_destino = i
            break
    if idx_destino is None:
        return None

    idx_origen = None
    for i in range(idx_destino - 1, -1, -1):
        parada = modelo.paradas.get(viaje.pasos[i].parada)
        if parada is not None and parada.localidad == origen:
            idx_origen = i
            break
    if idx_origen is None:
        return None

    return idx_origen, idx_destino


def _viajes_candidatos_por_localidad(
    horarios: Horarios, origen: str, destino: str
) -> list[Viaje]:
    """Viajes que paran en alguna parada de `origen` y en alguna parada de
    `destino` (en cualquier orden), usando `horarios.localidad_viajes` en vez
    de recorrer todas las líneas y viajes. No confirma el sentido del
    trayecto: eso lo hace `_emparejar` sobre cada candidato.

    El orden devuelto es el de `horarios.localidad_viajes[origen]`, que a su
    vez respeta el orden de `modelo.lineas` y, dentro de cada línea, el orden
    de `linea.viajes` (ver `loader.py`); así la agrupación por línea y por
    salida en `_resolver_fecha` no cambia respecto al escaneo completo."""
    viajes_origen = horarios.localidad_viajes.get(origen, ())
    viajes_destino = horarios.localidad_viajes.get(destino, ())
    if not viajes_origen or not viajes_destino:
        return []
    ids_destino = {id(v) for v in viajes_destino}
    return [v for v in viajes_origen if id(v) in ids_destino]


def _candidatos_por_linea(
    horarios: Horarios, origen: str, destino: str
) -> dict[str, list[Viaje]]:
    """Agrupa `_viajes_candidatos_por_localidad` por línea, preservando el
    orden de aparición de cada línea y de sus viajes."""
    agrupados: dict[str, list[Viaje]] = {}
    for viaje in _viajes_candidatos_por_localidad(horarios, origen, destino):
        agrupados.setdefault(viaje.linea, []).append(viaje)
    return agrupados


def _conecta_alguna_vez(
    horarios: Horarios, candidatos: list[Viaje], origen: str, destino: str
) -> bool:
    return any(
        _emparejar(horarios, viaje, origen, destino) is not None
        for viaje in candidatos
    )


def _mes_en_no_circula(linea: Linea, mes: int) -> bool:
    for nombre_mes in linea.no_circula:
        if formato._MESES.get(str(nombre_mes).strip().lower()) == mes:
            return True
    return False


def _observaciones_relevantes(
    linea: Linea, viaje: Viaje, i_origen: int, i_destino: int
):
    paso_origen = viaje.pasos[i_origen]
    paso_destino = viaje.pasos[i_destino]
    ids: list[str] = []
    ids.extend(linea.avisos)
    ids.extend(viaje.observaciones)
    ids.extend(paso_origen.observaciones)
    ids.extend(paso_destino.observaciones)
    return ids


def _evaluar_pareja(
    horarios: Horarios,
    linea: Linea,
    viaje: Viaje,
    i_origen: int,
    i_destino: int,
    info: InfoDia,
) -> tuple[bool, tuple[str, ...]]:
    """Comprueba las condiciones de negocio (design.md, 2.4 y 3) que aplican
    a esta pareja concreta de paradas de un viaje, y devuelve si es válida y
    las notas (texto ya resuelto) que debe llevar. Ningún pendiente (`Pnn`)
    aparece nunca aquí: son solo para negocio/validador."""
    modelo = horarios.modelo
    ids = _observaciones_relevantes(linea, viaje, i_origen, i_destino)
    notas: list[str] = []
    for oid in ids:
        obs = modelo.observaciones.get(oid)
        if obs is None:
            continue
        if obs.id == "solo_viernes_lectivo":
            if not (info.dia_semana == "viernes" and info.es_lectivo):
                return False, ()
        texto = formato.texto_observacion(obs, linea)
        if texto not in notas:
            notas.append(texto)
    return True, tuple(notas)


def _resolver_fecha(
    horarios: Horarios, origen: str, destino: str, fecha: date
) -> tuple[
    EstadoConsulta,
    list[Salida],
    InfoDia | None,
    tuple[tuple[str, Temporada], ...],
    tuple[str, ...],
    bool,
]:
    modelo = horarios.modelo
    calendario = modelo.calendario
    assert calendario is not None

    if fecha < calendario.vigencia_inicio or fecha > calendario.vigencia_fin:
        return "sin_datos", [], None, (), (), True

    info = calendario_servicio.info_dia(calendario, fecha)

    lineas_conectan: set[str] = set()
    lineas_sin_datos: set[str] = set()
    temporadas_usadas: dict[str, Temporada] = {}
    # (hora_salida, hora_llegada, parada_origen, parada_destino) -> Salida provisional
    agrupadas: dict[tuple[time, time, str, str], dict] = {}

    candidatos_por_linea = _candidatos_por_linea(horarios, origen, destino)

    for lid, candidatos in candidatos_por_linea.items():
        linea = modelo.lineas[lid]
        conecta_esta_linea = _conecta_alguna_vez(horarios, candidatos, origen, destino)
        if conecta_esta_linea:
            lineas_conectan.add(lid)

        temporada = calendario_servicio.temporada_de(linea, fecha)
        if temporada is None:
            continue
        if conecta_esta_linea:
            temporadas_usadas[lid] = temporada

        if _mes_en_no_circula(linea, fecha.month):
            continue

        estado = linea.dias.get(temporada.nombre, {}).get(info.clase_dia)
        if estado is None or estado == "sin_servicio":
            continue
        if estado == "sin_datos":
            if conecta_esta_linea:
                lineas_sin_datos.add(lid)
            continue

        # estado == "horario"
        for viaje in candidatos:
            if viaje.temporada != temporada.nombre:
                continue
            if info.clase_dia not in formato.GRUPOS_DIA.get(viaje.dias, frozenset()):
                continue
            par = _emparejar(horarios, viaje, origen, destino)
            if par is None:
                continue
            i_origen, i_destino = par
            valido, notas = _evaluar_pareja(
                horarios, linea, viaje, i_origen, i_destino, info
            )
            if not valido:
                continue

            paso_origen = viaje.pasos[i_origen]
            paso_destino = viaje.pasos[i_destino]
            hora_salida = _parse_hora(paso_origen.hora)
            hora_llegada = _parse_hora(paso_destino.hora)
            clave = (hora_salida, hora_llegada, paso_origen.parada, paso_destino.parada)
            entrada = agrupadas.setdefault(
                clave,
                {
                    "hora_salida": hora_salida,
                    "hora_llegada": hora_llegada,
                    "parada_origen": paso_origen.parada,
                    "parada_destino": paso_destino.parada,
                    "lineas": [],
                    "notas": [],
                },
            )
            if lid not in entrada["lineas"]:
                entrada["lineas"].append(lid)
            for nota in notas:
                if nota not in entrada["notas"]:
                    entrada["notas"].append(nota)

    salidas = [
        Salida(
            hora_salida=e["hora_salida"],
            hora_llegada=e["hora_llegada"],
            duracion_min=_minutos(e["hora_llegada"]) - _minutos(e["hora_salida"]),
            parada_origen=e["parada_origen"],
            parada_destino=e["parada_destino"],
            lineas=tuple(e["lineas"]),
            notas=tuple(e["notas"]),
        )
        for e in agrupadas.values()
    ]
    salidas.sort(key=lambda s: s.hora_salida)

    if not lineas_conectan:
        estado_final: EstadoConsulta = "sin_trayecto"
    elif salidas:
        estado_final = "con_salidas"
    elif lineas_sin_datos:
        estado_final = "sin_datos"
    else:
        estado_final = "sin_servicio"

    temporadas = tuple(
        sorted(temporadas_usadas.items(), key=lambda item: item[0])
    )
    return (
        estado_final,
        salidas,
        info,
        temporadas,
        tuple(sorted(lineas_sin_datos)),
        False,
    )


def consultar(
    horarios: Horarios,
    origen: str,
    destino: str,
    fecha: date,
    ahora: datetime | None = None,
) -> Consulta:
    modelo = horarios.modelo
    if origen == destino:
        raise ValueError("origen y destino no pueden ser la misma localidad")
    if origen not in modelo.localidades:
        raise ValueError(f"localidad de origen sin definir: '{origen}'")
    if destino not in modelo.localidades:
        raise ValueError(f"localidad de destino sin definir: '{destino}'")

    (
        estado,
        salidas,
        info,
        temporadas,
        lineas_sin_datos,
        fuera_de_calendario,
    ) = _resolver_fecha(horarios, origen, destino, fecha)

    if ahora is not None and ahora.date() == fecha:
        hora_actual = ahora.time()
        salidas = [
            Salida(
                hora_salida=s.hora_salida,
                hora_llegada=s.hora_llegada,
                duracion_min=s.duracion_min,
                parada_origen=s.parada_origen,
                parada_destino=s.parada_destino,
                lineas=s.lineas,
                notas=s.notas,
                ya_salio=s.hora_salida < hora_actual,
            )
            for s in salidas
        ]

    siguiente_con_servicio: date | None = None
    if not salidas and estado != "sin_trayecto" and not fuera_de_calendario:
        calendario = modelo.calendario
        assert calendario is not None
        for delta in range(1, SIGUIENTE_CON_SERVICIO_DIAS + 1):
            candidata = fecha + timedelta(days=delta)
            if candidata > calendario.vigencia_fin:
                break
            _, salidas_candidata, *_ = _resolver_fecha(
                horarios, origen, destino, candidata
            )
            if salidas_candidata:
                siguiente_con_servicio = candidata
                break

    return Consulta(
        estado=estado,
        salidas=tuple(salidas),
        info_dia=info,
        temporadas=temporadas,
        lineas_sin_datos=lineas_sin_datos,
        fuera_de_calendario=fuera_de_calendario,
        siguiente_con_servicio=siguiente_con_servicio,
    )


def destinos_desde(horarios: Horarios, origen: str) -> frozenset[str]:
    """Localidades a las que se llega en servicio directo desde `origen`, en
    cualquier temporada/día (no filtrado por fecha). Nunca incluye `origen`."""
    resultado: set[str] = set()
    for viaje in horarios.localidad_viajes.get(origen, ()):
        localidades_viaje = _localidades_del_viaje(horarios, viaje)
        if origen not in localidades_viaje:
            continue
        idx_primero = localidades_viaje.index(origen)
        for loc in localidades_viaje[idx_primero + 1 :]:
            if loc is not None and loc != origen:
                resultado.add(loc)
    return frozenset(resultado)
