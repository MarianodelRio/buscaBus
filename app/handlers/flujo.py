# handlers/flujo.py
"""Máquina de estados de la conversación (design.md, 4.1-4.8).

Toda lectura del reloj o del calendario pasa por `calendario.hoy()` /
`calendario.ahora()`, llamadas únicamente desde aquí (nunca desde los
constructores de `interactive.py` ni desde `messages.py`) para que los tests
puedan fijar la fecha con monkeypatch.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from app.services.horarios import calendario, datos as horarios_datos
from app.services.horarios import formato
from app.services.horarios import query
from app.services import whatsapp as wa
from app.utils import fechas
from app.utils.interactive import (
    build_candidatas,
    build_confirmar,
    build_destinos,
    build_dias,
    build_escribir,
    build_info,
    build_linea,
    build_lineas,
    build_localidad_pendiente,
    build_menu,
    build_origen,
    build_resultado,
)
from app.utils.matcher import lineas as matcher_lineas, paginar
from app.utils import messages as msg

logger = logging.getLogger(__name__)

# Textos no reconocidos se registran normalizados, nunca con el teléfono del
# cliente (design.md, 4.7): si el texto contiene 6 dígitos o más (p. ej. un
# teléfono escrito donde iba una fecha, con o sin espacios/guiones), se
# registra `<numero>` en su lugar. El recuento se hace sobre los dígitos del
# texto sin separadores, porque `formato.normalizar()` sustituye separadores
# por espacios y los dígitos dejarían de estar consecutivos.
_RE_NO_DIGITO = re.compile(r"\D")


def _texto_para_log(texto: str) -> str:
    normalizado = formato.normalizar(texto)[:40]
    solo_digitos = _RE_NO_DIGITO.sub("", normalizado)
    if len(solo_digitos) >= 6:
        return "<numero>"
    return normalizado

# ── Estados ────────────────────────────────────────────────────────────────
MENU = "MENU"
SEL_ORIGEN = "SEL_ORIGEN"
ESCRIBIR_ORIGEN = "ESCRIBIR_ORIGEN"
SEL_DESTINO = "SEL_DESTINO"
ESCRIBIR_DESTINO = "ESCRIBIR_DESTINO"
CONFIRMAR_PUEBLO = "CONFIRMAR_PUEBLO"
SEL_DIA = "SEL_DIA"
ESCRIBIR_FECHA = "ESCRIBIR_FECHA"
RESULTADO = "RESULTADO"


# ── Helpers puros ───────────────────────────────────────────────────────


def ordenar_destinos(
    alcanzables: list[str], prioridad: list[str], nombres: dict[str, str]
) -> list[tuple[str, str]]:
    """Orden de negocio primero (según `pueblos_menu_inicio`), después el
    resto en orden alfabético (design.md, 4.4)."""
    prioridad_presentes = [lid for lid in prioridad if lid in alcanzables]
    resto = [lid for lid in alcanzables if lid not in prioridad_presentes]
    resto.sort(key=lambda lid: formato.normalizar(nombres[lid]))
    orden = prioridad_presentes + resto
    return [(lid, nombres[lid]) for lid in orden]


def _nombres(datos, ids) -> list[tuple[str, str]]:
    return [(lid, datos.horarios.modelo.localidades[lid].nombre) for lid in ids]


def _nombre_localidad(datos, lid: str) -> str:
    return datos.horarios.modelo.localidades[lid].nombre


# ── Navegación ──────────────────────────────────────────────────────────


def to_menu(identifier: str, state) -> None:
    state.step = MENU
    state.campo = None
    state.origen = None
    state.destino = None
    state.fecha = None
    state.pendiente = None
    wa.send_interactive(identifier, build_menu())


def _ir_a_origen(identifier: str, state, aviso: str | None = None) -> None:
    datos = horarios_datos.actual()
    state.step = SEL_ORIGEN
    state.campo = "origen"
    state.origen = None
    state.destino = None
    state.pendiente = None
    localidades = _nombres(datos, datos.menu_origen)
    wa.send_interactive(identifier, build_origen(localidades, aviso=aviso))


def _mostrar_paso(identifier: str, state, campo: str, aviso: str | None = None,
                   con_lineas: bool = False) -> None:
    datos = horarios_datos.actual()
    if campo == "origen":
        localidades = _nombres(datos, datos.menu_origen)
        wa.send_interactive(
            identifier,
            build_origen(localidades, aviso=aviso, con_lineas=con_lineas),
        )
    else:
        origen_nombre = _nombre_localidad(datos, state.origen)
        alcanzables = list(query.destinos_desde(datos.horarios, state.origen))
        nombres_map = {lid: _nombre_localidad(datos, lid) for lid in alcanzables}
        ordenados = ordenar_destinos(alcanzables, list(datos.menu_origen), nombres_map)
        wa.send_interactive(
            identifier,
            build_destinos(
                origen_nombre, ordenados, aviso=aviso, con_lineas=con_lineas
            ),
        )


# ── Búsqueda de texto libre (design.md, 4.7) ──────────────────────────────


def _buscar(identifier: str, state, campo: str, texto: str) -> None:
    datos = horarios_datos.actual()
    coincidencia = datos.matcher.buscar(texto)

    if coincidencia.tipo == "unico":
        _elegir(identifier, state, campo, coincidencia.localidades[0])
        return

    if coincidencia.tipo == "confirmar":
        state.pendiente = coincidencia.localidades[0]
        state.campo = campo
        state.step = CONFIRMAR_PUEBLO
        nombre = _nombre_localidad(datos, state.pendiente)
        wa.send_interactive(identifier, build_confirmar(nombre))
        return

    if coincidencia.tipo == "elegir":
        candidatas = _nombres(datos, coincidencia.localidades)
        state.campo = campo
        wa.send_interactive(identifier, build_candidatas(candidatas, campo))
        return

    if coincidencia.tipo == "demasiadas":
        state.campo = campo
        wa.send_interactive(
            identifier, build_escribir(campo, msg.msg_demasiadas_coincidencias())
        )
        return

    # sin_coincidencia
    logger.info(
        "[NO_RECONOCIDO] paso=%s texto=%s", campo, _texto_para_log(texto)
    )
    state.campo = campo
    _mostrar_paso(identifier, state, campo, aviso=msg.msg_no_conozco_ese_pueblo(),
                  con_lineas=True)


def _elegir(identifier: str, state, campo: str, localidad_id: str) -> None:
    datos = horarios_datos.actual()
    loc = datos.horarios.modelo.localidades.get(localidad_id)
    if loc is not None and loc.pendiente is not None:
        # Aldea sin hora de paso (P15/P32): se ofrece consultar `ver` en su
        # lugar; no se toca state.origen ni se emite "sin trayecto".
        state.step = SEL_ORIGEN if campo == "origen" else SEL_DESTINO
        state.campo = campo
        state.pendiente = None
        ver_nombre = _nombre_localidad(datos, loc.ver)
        wa.send_interactive(
            identifier,
            build_localidad_pendiente(
                msg.msg_localidad_pendiente(loc.nombre, ver_nombre, loc.minutos),
                loc.ver,
                ver_nombre,
                campo,
            ),
        )
        return
    if campo == "origen":
        destinos = query.destinos_desde(datos.horarios, localidad_id)
        if not destinos:
            nombre = _nombre_localidad(datos, localidad_id)
            _mostrar_paso(
                identifier, state, "origen",
                aviso=msg.msg_sin_destinos_desde_origen(nombre),
            )
            return
        state.origen = localidad_id
        state.destino = None
        state.campo = "destino"
        state.step = SEL_DESTINO
        _mostrar_paso(identifier, state, "destino")
        return

    # campo == "destino"
    if localidad_id == state.origen:
        _mostrar_paso(identifier, state, "destino", aviso=msg.msg_destino_distinto())
        return
    alcanzables = query.destinos_desde(datos.horarios, state.origen)
    if localidad_id not in alcanzables:
        origen_nombre = _nombre_localidad(datos, state.origen)
        destino_nombre = _nombre_localidad(datos, localidad_id)
        if query.es_no_vendible(datos.horarios, state.origen, localidad_id):
            aviso = msg.msg_no_vendible(origen_nombre, destino_nombre)
        else:
            aviso = msg.msg_sin_trayecto(origen_nombre, destino_nombre)
        _mostrar_paso(identifier, state, "destino", aviso=aviso)
        return
    state.destino = localidad_id
    state.campo = None
    _mostrar_dias(identifier, state)


def _usar(identifier: str, state, campo: str, value: str) -> None:
    """Botón `usar:<id>` del mensaje de localidad pendiente. El id puede venir
    manipulado: si no existe o es pendiente, se repite el paso sin cambios."""
    lid = value.removeprefix("usar:")
    loc = horarios_datos.actual().horarios.modelo.localidades.get(lid)
    if loc is None or loc.pendiente is not None:
        _mostrar_paso(identifier, state, campo)
        return
    _elegir(identifier, state, campo, lid)


# ── Pueblos por línea (P18) ───────────────────────────────────────────


def _lineas_visibles(datos, campo: str, origen: str | None):
    """[(Linea, pueblos)] que ve el cliente. Origen: todas las líneas. Destino:
    de cada línea solo los pueblos alcanzables desde `origen` en esa línea,
    descartando las líneas que se quedan sin ninguno."""
    todas = matcher_lineas(datos.horarios)
    if campo != "destino" or origen is None:
        return [(linea, locs) for linea, locs in todas]
    resultado = []
    for linea, locs in todas:
        alcanzables = query.destinos_desde(datos.horarios, origen, linea.id)
        visibles = tuple(loc for loc in locs if loc.id in alcanzables)
        if visibles:
            resultado.append((linea, visibles))
    return resultado


def _mostrar_lineas(identifier: str, state, campo: str, pagina: int = 0) -> None:
    datos = horarios_datos.actual()
    visibles = _lineas_visibles(datos, campo, state.origen)
    if not visibles:
        state.campo = campo
        _mostrar_paso(identifier, state, campo, aviso=msg.msg_sin_lineas())
        return
    paginas = paginar(visibles)
    if pagina < 0 or pagina >= len(paginas):
        pagina = 0
    hay_mas = pagina + 1 < len(paginas)
    filas = [(linea, len(locs)) for linea, locs in paginas[pagina]]
    state.campo = campo
    wa.send_interactive(identifier, build_lineas(filas, pagina, hay_mas, campo))


def _pagina_de_lineas(value: str) -> int:
    try:
        return int(value.split(":", 1)[1])
    except (ValueError, IndexError):
        return 0


def _mostrar_linea_pagina(identifier: str, state, campo: str, value: str) -> None:
    partes = value.split(":")
    if len(partes) != 3:
        _mostrar_lineas(identifier, state, campo, 0)
        return
    lid, pag_txt = partes[1], partes[2]
    try:
        pagina = int(pag_txt)
    except ValueError:
        _mostrar_lineas(identifier, state, campo, 0)
        return
    datos = horarios_datos.actual()
    elegida = next(
        (
            (linea, locs)
            for linea, locs in _lineas_visibles(datos, campo, state.origen)
            if linea.id == lid
        ),
        None,
    )
    if elegida is None:
        _mostrar_lineas(identifier, state, campo, 0)
        return
    linea, locs = elegida
    paginas = paginar(locs)
    if pagina < 0 or pagina >= len(paginas):
        _mostrar_lineas(identifier, state, campo, 0)
        return
    hay_mas = pagina + 1 < len(paginas)
    filas = [(loc.id, loc.nombre) for loc in paginas[pagina]]
    state.campo = campo
    wa.send_interactive(identifier, build_linea(linea, filas, pagina, hay_mas))


# ── Día ────────────────────────────────────────────────────────────────


def _titulo_dia(fecha: date, indice: int) -> str:
    abrev = msg.nombre_dia_abrev_es(fecha)
    dd_mm = f"{fecha.day:02d}/{fecha.month:02d}"
    if indice == 0:
        return f"Hoy · {abrev} {dd_mm}"
    if indice == 1:
        return f"Mañana · {abrev} {dd_mm}"
    return f"{abrev.capitalize()} {dd_mm}"


def _descripcion_dia(consulta, es_hoy: bool) -> str:
    """Descripción de una fila de la lista de días (design.md, 4.5)."""
    es_festivo = (
        consulta.info_dia is not None and consulta.info_dia.es_festivo
    ) or consulta.festivo_local is not None
    prefijo = "festivo · " if es_festivo else ""
    sufijo = " · puede haber más" if consulta.lineas_sin_datos else ""

    if consulta.estado == "con_salidas":
        n = len(consulta.salidas)
        if es_hoy:
            pendientes = [s for s in consulta.salidas if not s.ya_salio]
            if not pendientes:
                return prefijo + "ya no quedan salidas hoy" + sufijo
            proxima = pendientes[0].hora_salida.strftime("%H:%M")
            return prefijo + f"{n} salidas · próxima {proxima}" + sufijo
        if n == 1:
            hora = consulta.salidas[0].hora_salida.strftime("%H:%M")
            return prefijo + f"1 salida · {hora}" + sufijo
        primera = consulta.salidas[0].hora_salida.strftime("%H:%M")
        ultima = consulta.salidas[-1].hora_salida.strftime("%H:%M")
        return prefijo + f"{n} salidas · de {primera} a {ultima}" + sufijo
    if consulta.estado == "sin_servicio":
        return prefijo + "sin servicio"  # también sin_servicio_general (P03g)
    if consulta.estado == "sin_datos":
        return prefijo + "horario no disponible"
    if consulta.estado == "no_vendible":
        return "no vendemos este trayecto"  # defensivo: no debería llegar aquí
    return prefijo + "—"


def _mostrar_dias(identifier: str, state, aviso: str | None = None) -> None:
    datos = horarios_datos.actual()
    hoy = calendario.hoy()
    ahora = calendario.ahora()
    filas = []
    for i in range(7):
        f = hoy + timedelta(days=i)
        consulta = query.consultar(
            datos.horarios, state.origen, state.destino, f, ahora=ahora
        )
        filas.append(
            (f"dia:{f.isoformat()}", _titulo_dia(f, i),
             _descripcion_dia(consulta, es_hoy=(i == 0)))
        )
    origen_nombre = _nombre_localidad(datos, state.origen)
    destino_nombre = _nombre_localidad(datos, state.destino)
    state.step = SEL_DIA
    state.campo = None
    wa.send_interactive(
        identifier, build_dias(origen_nombre, destino_nombre, filas, aviso=aviso)
    )


# ── Fecha libre ────────────────────────────────────────────────────────


def _leer_fecha_libre(identifier: str, state, texto: str, en_lista: bool) -> None:
    hoy = calendario.hoy()
    lectura = fechas.leer_fecha(texto, hoy)
    if lectura.estado == "ok":
        _resultado(identifier, state, lectura.fecha)
        return
    if lectura.estado == "pasada":
        if en_lista:
            _mostrar_dias(identifier, state, aviso=msg.msg_fecha_pasada())
        else:
            wa.send_text_message(identifier, msg.msg_fecha_pasada_con_formato())
        return
    # formato | inexistente
    logger.info("[NO_RECONOCIDO] paso=fecha texto=%s", _texto_para_log(texto))
    if en_lista:
        _mostrar_dias(identifier, state, aviso=msg.msg_elige_de_la_lista())
    else:
        wa.send_text_message(identifier, msg.msg_fecha_no_entendida())


# ── Resultado ──────────────────────────────────────────────────────────


def _botones_resultado(datos, consulta, fecha: date) -> list[tuple[str, str]]:
    hoy = calendario.hoy()
    vigencia_fin = datos.horarios.modelo.calendario.vigencia_fin
    botones: list[tuple[str, str]] = []

    if consulta.estado == "no_vendible":
        # defensivo: sin "otro día" ni "vuelta" (tampoco se vende la vuelta)
        return [("otra_consulta", "🔍 Otra consulta")]

    if consulta.estado == "con_salidas":
        pendientes = [s for s in consulta.salidas if not s.ya_salio]
        if not pendientes and fecha == hoy:
            manana = fecha + timedelta(days=1)
            if manana <= vigencia_fin:
                botones.append((f"dia:{manana.isoformat()}", "📅 Mañana"))
            else:
                botones.append(("otro_dia", "📅 Otro día"))
        else:
            botones.append(("otro_dia", "📅 Otro día"))
    elif consulta.estado == "sin_servicio" and consulta.siguiente_con_servicio:
        sig = consulta.siguiente_con_servicio
        botones.append((f"dia:{sig.isoformat()}", f"📅 Día {sig.day}/{sig.month}"))
    else:
        botones.append(("otro_dia", "📅 Otro día"))

    botones.append(("vuelta", "🔄 Ver la vuelta"))
    botones.append(("otra_consulta", "🔍 Otra consulta"))
    return botones[:3]


def _resultado(identifier: str, state, fecha: date) -> None:
    datos = horarios_datos.actual()
    ahora = calendario.ahora()
    consulta = query.consultar(
        datos.horarios, state.origen, state.destino, fecha, ahora=ahora
    )
    origen_nombre = _nombre_localidad(datos, state.origen)
    destino_nombre = _nombre_localidad(datos, state.destino)
    texto = msg.msg_resultado(
        consulta, datos.horarios, origen_nombre, destino_nombre, fecha
    )
    botones = _botones_resultado(datos, consulta, fecha)
    state.fecha = fecha
    state.step = RESULTADO
    wa.send_interactive(identifier, build_resultado(texto, botones))


# ── Handlers por estado ───────────────────────────────────────────────


def _handle_menu(identifier: str, state, value: str) -> None:
    if value == "menu_horarios":
        _ir_a_origen(identifier, state)
    elif value == "menu_info":
        wa.send_interactive(identifier, build_info())
    else:
        wa.send_interactive(identifier, build_menu())


def _handle_sel_origen(identifier: str, state, value: str) -> None:
    if value.startswith("loc:"):
        _elegir(identifier, state, "origen", value.removeprefix("loc:"))
    elif value.startswith("usar:"):
        _usar(identifier, state, "origen", value)
    elif value == "escribir":
        state.step = ESCRIBIR_ORIGEN
        state.campo = "origen"
        wa.send_interactive(
            identifier, build_escribir("origen", msg.msg_pedir_pueblo("origen"))
        )
    elif value.startswith("lineas:"):
        _mostrar_lineas(identifier, state, "origen", _pagina_de_lineas(value))
    elif value.startswith("linea:"):
        _mostrar_linea_pagina(identifier, state, "origen", value)
    elif value == "zonas" or value.startswith("zona:"):
        # Botones y filas antiguos (antes de P18): lista de líneas.
        _mostrar_lineas(identifier, state, "origen", 0)
    elif value == "menu":
        to_menu(identifier, state)
    else:
        _buscar(identifier, state, "origen", value)


def _handle_sel_destino(identifier: str, state, value: str) -> None:
    if value.startswith("loc:"):
        _elegir(identifier, state, "destino", value.removeprefix("loc:"))
    elif value.startswith("usar:"):
        _usar(identifier, state, "destino", value)
    elif value == "escribir":
        state.step = ESCRIBIR_DESTINO
        state.campo = "destino"
        wa.send_interactive(
            identifier, build_escribir("destino", msg.msg_pedir_pueblo("destino"))
        )
    elif value.startswith("lineas:"):
        _mostrar_lineas(identifier, state, "destino", _pagina_de_lineas(value))
    elif value.startswith("linea:"):
        _mostrar_linea_pagina(identifier, state, "destino", value)
    elif value == "zonas" or value.startswith("zona:"):
        # Botones y filas antiguos (antes de P18): lista de líneas.
        _mostrar_lineas(identifier, state, "destino", 0)
    elif value == "cambiar_origen":
        _ir_a_origen(identifier, state)
    else:
        _buscar(identifier, state, "destino", value)


def _handle_confirmar_pueblo(identifier: str, state, value: str) -> None:
    if value == "si":
        if state.pendiente is None or state.campo is None:
            to_menu(identifier, state)
            return
        campo = state.campo
        lid = state.pendiente
        state.pendiente = None
        _elegir(identifier, state, campo, lid)
    elif value == "no":
        state.pendiente = None
        campo = state.campo or "origen"
        state.step = ESCRIBIR_ORIGEN if campo == "origen" else ESCRIBIR_DESTINO
        wa.send_interactive(
            identifier, build_escribir(campo, msg.msg_escribelo_de_otra_forma())
        )
    else:
        campo = state.campo or "origen"
        _buscar(identifier, state, campo, value)


def _handle_sel_dia(identifier: str, state, value: str) -> None:
    if value.startswith("dia:"):
        try:
            f = date.fromisoformat(value.removeprefix("dia:"))
        except ValueError:
            _mostrar_dias(identifier, state)
            return
        _resultado(identifier, state, f)
    elif value == "otra_fecha":
        state.step = ESCRIBIR_FECHA
        wa.send_text_message(identifier, msg.msg_formato_fecha())
    else:
        _leer_fecha_libre(identifier, state, value, en_lista=True)


def _handle_escribir_fecha(identifier: str, state, value: str) -> None:
    _leer_fecha_libre(identifier, state, value, en_lista=False)


def _handle_resultado(identifier: str, state, value: str) -> None:
    datos = horarios_datos.actual()
    if value == "otro_dia":
        _mostrar_dias(identifier, state)
    elif value == "vuelta":
        nuevo_origen, nuevo_destino = state.destino, state.origen
        alcanzables = query.destinos_desde(datos.horarios, nuevo_origen)
        if nuevo_destino not in alcanzables:
            origen_nombre = _nombre_localidad(datos, nuevo_origen)
            destino_nombre = _nombre_localidad(datos, nuevo_destino)
            if query.es_no_vendible(datos.horarios, nuevo_origen, nuevo_destino):
                texto = msg.msg_no_vendible(origen_nombre, destino_nombre)
            else:
                texto = msg.msg_sin_trayecto(origen_nombre, destino_nombre)
            wa.send_text_message(identifier, texto)
            to_menu(identifier, state)
            return
        state.origen, state.destino = nuevo_origen, nuevo_destino
        _mostrar_dias(identifier, state)
    elif value == "otra_consulta":
        _ir_a_origen(identifier, state)
    elif value.startswith("dia:"):
        try:
            f = date.fromisoformat(value.removeprefix("dia:"))
        except ValueError:
            to_menu(identifier, state)
            return
        _resultado(identifier, state, f)
    else:
        to_menu(identifier, state)


DESPACHO = {
    MENU: _handle_menu,
    SEL_ORIGEN: _handle_sel_origen,
    ESCRIBIR_ORIGEN: _handle_sel_origen,
    SEL_DESTINO: _handle_sel_destino,
    ESCRIBIR_DESTINO: _handle_sel_destino,
    CONFIRMAR_PUEBLO: _handle_confirmar_pueblo,
    SEL_DIA: _handle_sel_dia,
    ESCRIBIR_FECHA: _handle_escribir_fecha,
    RESULTADO: _handle_resultado,
}
