"""app/services/horarios/diff.py — diferencias entre dos versiones de horarios/
en lenguaje de negocio (design.md, sección 2.3, "Cambios desde la versión
publicada").

Módulo puro: no toca disco, no invoca git, no lanza excepciones por
diferencias de negocio. Compara dos `Modelo` ya validados por
`formato.validar()` (los construye quien llama, típicamente
`tools/revision.py`). `tools/revision.py` es responsable de decidir si hay
una versión anterior o si es la primera versión: este módulo siempre recibe
dos `Modelo`s reales.
"""

from __future__ import annotations

from app.services.horarios.formato import DIAS_INDIVIDUALES, GRUPOS_DIA, Modelo
from app.services.horarios.modelo import Linea, Paso, Viaje

_MESES_EN_PALABRAS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

_ESTADOS_EN_PALABRAS = {
    "horario": "hay servicio",
    "sin_servicio": "sin servicio",
    "sin_datos": "sin datos",
}

# Orden estable de las clases de día para recorrer los cambios de "dias".
_ORDEN_CLASES = DIAS_INDIVIDUALES

# Fraseo "en palabras" de cada clave de tabla (design.md sección 2.3). Se
# construye a partir de GRUPOS_DIA para no duplicar el catálogo de claves de
# formato.py, con los textos exactos que pide el diseño.
_CLASES_EN_PALABRAS = {
    "lunes": "lunes",
    "martes": "martes",
    "miercoles": "miércoles",
    "jueves": "jueves",
    "viernes": "viernes",
    "sabado": "sábado",
    "domingo": "domingo",
    "festivos": "festivos",
    "lunes-viernes": "lunes a viernes",
    "lunes-jueves": "lunes a jueves",
    "martes-viernes": "martes a viernes",
    "sabados-domingos": "sábados y domingos",
    "domingos-festivos": "domingos y festivos",
    "sabados-domingos-festivos": "sábados, domingos y festivos",
}

assert set(_CLASES_EN_PALABRAS) == set(GRUPOS_DIA), (
    "_CLASES_EN_PALABRAS debe cubrir exactamente las claves de GRUPOS_DIA "
    "(formato.py)"
)


def fecha_en_palabras(fecha: str) -> str:
    """'15/09' -> '15 de septiembre'. Si no tiene ese formato, se devuelve
    tal cual (nunca se adivina)."""
    fecha = fecha.strip()
    partes = fecha.split("/")
    if len(partes) != 2:
        return fecha
    try:
        dia = int(partes[0])
        mes = int(partes[1])
    except ValueError:
        return fecha
    nombre_mes = _MESES_EN_PALABRAS.get(mes)
    if nombre_mes is None:
        return fecha
    return f"{dia} de {nombre_mes}"


def rango_en_palabras(rango: str) -> str:
    """'15/09 - 22/06' -> 'del 15 de septiembre al 22 de junio'. 'todo el
    año' se deja igual."""
    rango = rango.strip()
    if rango.lower() in ("todo el año", "todo el ano"):
        return rango
    partes = [p.strip() for p in rango.split("-")]
    if len(partes) != 2:
        return rango
    return f"del {fecha_en_palabras(partes[0])} al {fecha_en_palabras(partes[1])}"


def clase_en_palabras(clase: str) -> str:
    return _CLASES_EN_PALABRAS.get(clase, clase)


def estado_en_palabras(estado: str) -> str:
    return _ESTADOS_EN_PALABRAS.get(estado, estado)


def _nombre_parada(modelo: Modelo, codigo: str) -> str:
    parada = modelo.paradas.get(codigo)
    return parada.nombre if parada is not None else codigo


def _hora_primer_paso(viaje: Viaje) -> str:
    return viaje.pasos[0].hora if viaje.pasos else ""


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# Diferencia máxima (minutos) entre las horas del primer punto en común de
# dos viajes para considerarlos "el mismo viaje que cambió de hora" en vez de
# una alta y una baja independientes (design.md 8, "Correcciones de la fase
# 1", punto 3).
_UMBRAL_MINUTOS_EMPAREJADO = 30


def _firma_tabla(viaje: Viaje) -> tuple[str, str, str | None, str | None]:
    """(temporada, dias, primera parada de la cabecera, última parada de la
    cabecera) de la `Tabla` a la que pertenece `viaje`. Dos tablas con la
    misma firma en versiones distintas se consideran "la misma tabla" a
    efectos del diff (formato.py impide que haya dos tablas con la misma
    firma dentro de una misma línea)."""
    paradas = viaje.tabla.paradas
    primera = paradas[0] if paradas else None
    ultima = paradas[-1] if paradas else None
    return (viaje.temporada, viaje.dias, primera, ultima)


def _agrupar_por_firma(linea: Linea) -> dict[tuple, list[Viaje]]:
    grupos: dict[tuple, list[Viaje]] = {}
    for v in linea.viajes:
        grupos.setdefault(_firma_tabla(v), []).append(v)
    return grupos


def _clave_viaje(viaje: Viaje) -> tuple:
    """Identidad de un viaje independiente del orden de sus pasos (para
    detectar viajes idénticos aunque la cabecera de su tabla se haya
    reordenado sin cambiar ningún dato)."""
    pasos = frozenset(
        (p.parada, p.hora, frozenset(p.observaciones)) for p in viaje.pasos
    )
    return (pasos, frozenset(viaje.observaciones), frozenset(viaje.pendientes))


def _diferencia_primer_paso_comun(viaje_a: Viaje, viaje_b: Viaje) -> int | None:
    horas_b = {p.parada: p.hora for p in viaje_b.pasos}
    for paso in viaje_a.pasos:
        hora_b = horas_b.get(paso.parada)
        if hora_b is not None:
            return abs(_minutos(paso.hora) - _minutos(hora_b))
    return None


def _emparejar_por_cercania(
    viajes_ant: list[Viaje], viajes_act: list[Viaje]
) -> tuple[list[tuple[Viaje, Viaje]], list[Viaje], list[Viaje]]:
    """Empareja viajes por cercanía de horas en su primer punto en común
    (≤ _UMBRAL_MINUTOS_EMPAREJADO), voraz por menor diferencia y, en caso de
    empate, por la hora más temprana. Devuelve (pares, sobrantes_ant,
    sobrantes_act)."""
    restante_ant = list(viajes_ant)
    restante_act = list(viajes_act)
    pares: list[tuple[Viaje, Viaje]] = []
    while restante_ant and restante_act:
        mejor: tuple | None = None
        mejor_ij: tuple[int, int] | None = None
        for i, v_ant in enumerate(restante_ant):
            for j, v_act in enumerate(restante_act):
                dif = _diferencia_primer_paso_comun(v_ant, v_act)
                if dif is None or dif > _UMBRAL_MINUTOS_EMPAREJADO:
                    continue
                clave = (dif, _hora_primer_paso(v_ant), _hora_primer_paso(v_act))
                if mejor is None or clave < mejor:
                    mejor = clave
                    mejor_ij = (i, j)
        if mejor_ij is None:
            break
        i, j = mejor_ij
        pares.append((restante_ant.pop(i), restante_act.pop(j)))
    return pares, restante_ant, restante_act


def _comparar_temporadas(
    nombre_linea: str, anterior: Linea, actual: Linea
) -> list[str]:
    mensajes: list[str] = []
    rangos_anterior = {t.nombre: t.rango for t in anterior.temporadas}
    rangos_actual = {t.nombre: t.rango for t in actual.temporadas}
    for nombre_temp in sorted(set(rangos_anterior) | set(rangos_actual)):
        r_ant = rangos_anterior.get(nombre_temp)
        r_act = rangos_actual.get(nombre_temp)
        if r_ant is None:
            mensajes.append(
                f"{nombre_linea}: se añade la temporada '{nombre_temp}' "
                f"({rango_en_palabras(r_act)})."
            )
        elif r_act is None:
            mensajes.append(
                f"{nombre_linea}: se quita la temporada '{nombre_temp}' "
                f"({rango_en_palabras(r_ant)})."
            )
        elif r_ant != r_act:
            mensajes.append(
                f"{nombre_linea}: la temporada '{nombre_temp}' pasa de "
                f"{rango_en_palabras(r_ant)} a {rango_en_palabras(r_act)}."
            )
    return mensajes


def _comparar_dias(nombre_linea: str, anterior: Linea, actual: Linea) -> list[str]:
    mensajes: list[str] = []
    temporadas = sorted(set(anterior.dias) | set(actual.dias))
    for nombre_temp in temporadas:
        estados_ant = anterior.dias.get(nombre_temp, {})
        estados_act = actual.dias.get(nombre_temp, {})
        for clase in _ORDEN_CLASES:
            e_ant = estados_ant.get(clase)
            e_act = estados_act.get(clase)
            if e_ant is None or e_act is None:
                continue
            if e_ant != e_act:
                mensajes.append(
                    f"{nombre_linea}, temporada '{nombre_temp}', "
                    f"{clase_en_palabras(clase)}: pasa de "
                    f"{estado_en_palabras(e_ant)} a {estado_en_palabras(e_act)}."
                )
    return mensajes


def _extremos_viaje(modelo: Modelo, viaje: Viaje) -> str:
    if not viaje.pasos:
        return ""
    origen = _nombre_parada(modelo, viaje.pasos[0].parada)
    destino = _nombre_parada(modelo, viaje.pasos[-1].parada)
    hora = viaje.pasos[0].hora
    return f"{hora} de {origen} a {destino}"


def _comparar_viajes(
    nombre_linea: str,
    anterior: Linea,
    actual: Linea,
    modelo_anterior: Modelo,
    modelo_actual: Modelo,
) -> list[str]:
    mensajes: list[str] = []

    grupos_ant = _agrupar_por_firma(anterior)
    grupos_act = _agrupar_por_firma(actual)

    for firma in sorted(
        set(grupos_ant) | set(grupos_act),
        key=lambda f: (f[0], f[1], f[2] or "", f[3] or ""),
    ):
        temporada, dias, _primera, _ultima = firma
        viajes_ant = grupos_ant.get(firma)
        viajes_act = grupos_act.get(firma)

        if viajes_ant is None:
            resumen = "; ".join(
                _extremos_viaje(modelo_actual, v) for v in viajes_act
            )
            mensajes.append(
                f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: "
                f"tabla añadida ({resumen})."
            )
            continue
        if viajes_act is None:
            resumen = "; ".join(
                _extremos_viaje(modelo_anterior, v) for v in viajes_ant
            )
            mensajes.append(
                f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: "
                f"tabla quitada ({resumen})."
            )
            continue

        mensajes.extend(
            _comparar_tabla(
                nombre_linea,
                temporada,
                dias,
                viajes_ant,
                viajes_act,
                modelo_anterior,
                modelo_actual,
            )
        )

    return mensajes


def _comparar_tabla(
    nombre_linea: str,
    temporada: str,
    dias: str,
    viajes_ant: list[Viaje],
    viajes_act: list[Viaje],
    modelo_anterior: Modelo,
    modelo_actual: Modelo,
) -> list[str]:
    mensajes: list[str] = []

    restante_ant = list(viajes_ant)
    restante_act = list(viajes_act)

    # 1. Viajes idénticos en ambos lados: no generan ningún mensaje. Se
    # comparan por contenido (parada+hora+observaciones), no por posición, así
    # que reordenar la cabecera de la tabla sin cambiar datos no genera ruido.
    for v_act in list(restante_act):
        clave = _clave_viaje(v_act)
        for v_ant in restante_ant:
            if _clave_viaje(v_ant) == clave:
                restante_ant.remove(v_ant)
                restante_act.remove(v_act)
                break

    # 2. El resto se empareja por cercanía de horas: quitar un viaje de en
    # medio de un grupo no debe leerse como que otro viaje "cambió de hora".
    pares, restante_ant, restante_act = _emparejar_por_cercania(
        restante_ant, restante_act
    )

    for viaje_ant, viaje_act in pares:
        mensajes.extend(
            _comparar_viaje_pareado(
                nombre_linea,
                temporada,
                dias,
                viaje_ant,
                viaje_act,
                modelo_anterior,
                modelo_actual,
            )
        )

    for viaje_act in sorted(restante_act, key=_hora_primer_paso):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: "
            f"viaje añadido ({_extremos_viaje(modelo_actual, viaje_act)})."
        )
    for viaje_ant in sorted(restante_ant, key=_hora_primer_paso):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: "
            f"viaje quitado ({_extremos_viaje(modelo_anterior, viaje_ant)})."
        )

    return mensajes


# Fraseo del verbo según la posición del paso en el viaje *actual* (design.md
# 8, "Correcciones de la fase 1", punto 7: no siempre es "la salida").
_VERBO_POR_POSICION = {
    "primera": "Sale de",
    "intermedia": "Pasa por",
    "ultima": "Llega a",
}


def _posicion(indice: int, total: int) -> str:
    if indice == 0:
        return "primera"
    if indice == total - 1:
        return "ultima"
    return "intermedia"


def _comparar_viaje_pareado(
    nombre_linea: str,
    temporada: str,
    dias: str,
    viaje_ant: Viaje,
    viaje_act: Viaje,
    modelo_anterior: Modelo,
    modelo_actual: Modelo,
) -> list[str]:
    mensajes: list[str] = []
    pasos_ant_por_codigo = {p.parada: p for p in viaje_ant.pasos}
    pasos_act_por_codigo = {p.parada: p for p in viaje_act.pasos}
    total = len(viaje_act.pasos)

    for indice, paso_act in enumerate(viaje_act.pasos):
        nombre_parada = _nombre_parada(modelo_actual, paso_act.parada)
        paso_ant = pasos_ant_por_codigo.get(paso_act.parada)
        if paso_ant is None:
            mensajes.append(
                f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: ahora "
                f"para en {nombre_parada} a las {paso_act.hora}."
            )
            continue
        if paso_ant.hora != paso_act.hora:
            verbo = _VERBO_POR_POSICION[_posicion(indice, total)]
            mensajes.append(
                f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: {verbo} "
                f"{nombre_parada}: de las {paso_ant.hora} a las {paso_act.hora}."
            )
        mensajes.extend(
            _comparar_observaciones_paso(
                nombre_linea, temporada, dias, nombre_parada, paso_ant, paso_act
            )
        )

    for paso_ant in viaje_ant.pasos:
        if paso_ant.parada not in pasos_act_por_codigo:
            nombre_parada = _nombre_parada(modelo_anterior, paso_ant.parada)
            mensajes.append(
                f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: ya no "
                f"para en {nombre_parada}."
            )

    mensajes.extend(
        _comparar_observaciones_viaje(
            nombre_linea, temporada, dias, viaje_ant, viaje_act
        )
    )
    return mensajes


def _comparar_observaciones_paso(
    nombre_linea: str,
    temporada: str,
    dias: str,
    nombre_parada: str,
    paso_ant: Paso,
    paso_act: Paso,
) -> list[str]:
    mensajes: list[str] = []
    obs_ant = set(paso_ant.observaciones)
    obs_act = set(paso_act.observaciones)
    for oid in sorted(obs_act - obs_ant):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}, en "
            f"{nombre_parada}: se añade la observación '{oid}'."
        )
    for oid in sorted(obs_ant - obs_act):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}, en "
            f"{nombre_parada}: se quita la observación '{oid}'."
        )
    return mensajes


def _comparar_observaciones_viaje(
    nombre_linea: str,
    temporada: str,
    dias: str,
    viaje_ant: Viaje,
    viaje_act: Viaje,
) -> list[str]:
    mensajes: list[str] = []
    obs_ant = set(viaje_ant.observaciones)
    obs_act = set(viaje_act.observaciones)
    for oid in sorted(obs_act - obs_ant):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: se añade "
            f"la observación de viaje '{oid}'."
        )
    for oid in sorted(obs_ant - obs_act):
        mensajes.append(
            f"{nombre_linea}, {temporada}, {clase_en_palabras(dias)}: se quita "
            f"la observación de viaje '{oid}'."
        )
    return mensajes


def _comparar_linea(
    anterior: Linea,
    actual: Linea,
    modelo_anterior: Modelo,
    modelo_actual: Modelo,
) -> list[str]:
    nombre_linea = actual.nombre
    mensajes: list[str] = []
    mensajes.extend(_comparar_temporadas(nombre_linea, anterior, actual))
    mensajes.extend(_comparar_dias(nombre_linea, anterior, actual))
    mensajes.extend(
        _comparar_viajes(nombre_linea, anterior, actual, modelo_anterior, modelo_actual)
    )
    return mensajes


def comparar(anterior: Modelo, actual: Modelo) -> list[str]:
    """Devuelve una lista de frases en lenguaje de negocio con las
    diferencias entre `anterior` y `actual`. Ambos deben ser `Modelo`s reales
    ya validados; nunca se llama con `None` (eso lo decide quien invoca este
    módulo, típicamente `tools/revision.py`, que resuelve "primera versión"
    antes de llamar aquí)."""
    mensajes: list[str] = []
    ids_lineas = sorted(set(anterior.lineas) | set(actual.lineas))
    for lid in ids_lineas:
        linea_ant = anterior.lineas.get(lid)
        linea_act = actual.lineas.get(lid)
        if linea_ant is None:
            mensajes.append(f"Línea nueva: {linea_act.nombre}.")
        elif linea_act is None:
            mensajes.append(f"Línea eliminada: {linea_ant.nombre}.")
        else:
            mensajes.extend(_comparar_linea(linea_ant, linea_act, anterior, actual))
    return mensajes
