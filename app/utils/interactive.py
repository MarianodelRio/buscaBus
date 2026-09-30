# utils/interactive.py
"""Constructores de mensajes interactivos de WhatsApp (listas/botones).

Límites de WhatsApp (design.md, 4): lista máximo 10 filas en total, título de
fila 24 caracteres, descripción 72; botones máximo 3, texto 20 caracteres.
Los constructores de aquí son PUROS: no leen estado ni el reloj — reciben ya
calculados los datos que van a pintar (plan fase 4, paso 10).
"""

from __future__ import annotations

import re

from app.config import (
    INTERACTIVE_FOOTER,
    MAX_DESCRIPCION_FILA,
    MAX_FILAS_LISTA,
    MAX_TITULO_BOTON,
    MAX_TITULO_FILA,
)

# ── Helpers genéricos (copiados del patrón de Peluquería) ─────────────────


def _trunc(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def _button(id_: str, title: str) -> dict:
    return {
        "type": "reply",
        "reply": {"id": id_, "title": _trunc(title, MAX_TITULO_BOTON)},
    }


def _row(id_: str, title: str, description: str = "") -> dict:
    row = {"id": id_, "title": _trunc(title, MAX_TITULO_FILA)}
    if description:
        row["description"] = _trunc(description, MAX_DESCRIPCION_FILA)
    return row


def _section(title: str, rows: list) -> dict:
    return {"title": title, "rows": rows}


def _interactive_buttons(body: str, buttons: list, header: str | None = None) -> dict:
    msg: dict = {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "footer": {"text": INTERACTIVE_FOOTER},
            "action": {"buttons": buttons},
        },
    }
    if header:
        msg["interactive"]["header"] = {"type": "text", "text": header}
    return msg


def _interactive_list(body: str, button_label: str, sections: list,
                       header: str | None = None) -> dict:
    msg: dict = {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "footer": {"text": INTERACTIVE_FOOTER},
            "action": {
                "button": _trunc(button_label, MAX_TITULO_BOTON),
                "sections": sections,
            },
        },
    }
    if header:
        msg["interactive"]["header"] = {"type": "text", "text": header}
    return msg


def _fila_localidad(id_: str, nombre: str) -> dict:
    """Fila para una localidad: la descripción lleva el nombre completo si el
    título se truncó (plan fase 4, paso 10)."""
    row = {"id": id_, "title": _trunc(nombre, MAX_TITULO_FILA)}
    if len(nombre) > MAX_TITULO_FILA:
        row["description"] = _trunc(nombre, MAX_DESCRIPCION_FILA)
    return row


# ── Menú / información ──────────────────────────────────────────────────


def build_menu() -> dict:
    from app.utils.messages import msg_menu_footer

    return _interactive_buttons(
        header="🚌 Autocares · Horarios",
        body=f"¿Qué necesitas?\n\n{msg_menu_footer()}",
        buttons=[
            _button("menu_horarios", "🚌 Ver horarios"),
            _button("menu_info", "ℹ️ Teléfono y contacto"),
        ],
    )


def build_info() -> dict:
    from app.utils.messages import msg_info

    return _interactive_buttons(
        body=msg_info(),
        buttons=[
            _button("menu_horarios", "🚌 Ver horarios"),
            _button("menu", "↩️ Menú"),
        ],
    )


# ── Origen / destino ──────────────────────────────────────────────────────


def build_origen(localidades: list[tuple[str, str]], aviso: str | None = None,
                  con_lineas: bool = False) -> dict:
    """localidades: lista de (id, nombre) ya recortada a como mucho 8."""
    rows = [_fila_localidad(f"loc:{lid}", nombre) for lid, nombre in localidades[:8]]
    if con_lineas:
        rows.append(_row("lineas:0", "🚌 Ver pueblos por línea"))
    else:
        rows.append(_row("escribir", "✍️ Otro pueblo"))
    rows.append(_row("menu", "↩️ Volver al menú"))
    body = "¿Desde qué pueblo sales?"
    if aviso:
        body = f"{aviso}\n\n{body}"
    return _interactive_list(
        header="🚌 Horarios de autobús",
        body=body,
        button_label="Ver pueblos",
        sections=[_section("Pueblos", rows)],
    )


def build_destinos(origen_nombre: str, destinos_ordenados: list[tuple[str, str]],
                    aviso: str | None = None, con_lineas: bool = False) -> dict:
    """destinos_ordenados: lista completa de (id, nombre) ya ordenada
    (`flujo.ordenar_destinos`). Si hay 9 o menos, se muestran todos + volver
    (cero ambigüedad, design.md 4.4). Si hay más, se muestran los 8
    primeros + fila de escribir/líneas + volver = 10 filas."""
    n = len(destinos_ordenados)
    if n <= MAX_FILAS_LISTA - 1:
        rows = [
            _fila_localidad(f"loc:{lid}", nombre) for lid, nombre in destinos_ordenados
        ]
        rows.append(_row("cambiar_origen", "↩️ Cambiar origen"))
    else:
        rows = [
            _fila_localidad(f"loc:{lid}", nombre)
            for lid, nombre in destinos_ordenados[:8]
        ]
        if con_lineas:
            rows.append(_row("lineas:0", "🚌 Ver pueblos por línea"))
        else:
            rows.append(_row("escribir", "✍️ Otro destino"))
        rows.append(_row("cambiar_origen", "↩️ Cambiar origen"))
    body = "¿A dónde vas?"
    if aviso:
        body = f"{aviso}\n\n{body}"
    return _interactive_list(
        header=f"🚌 Desde {origen_nombre}",
        body=body,
        button_label="Ver destinos",
        sections=[_section("Destinos", rows)],
    )


def build_candidatas(localidades: list[tuple[str, str]], campo: str) -> dict:
    """2-9 candidatas. 2-3 con nombres cortos -> botones; si no, lista."""
    if 2 <= len(localidades) <= 3 and all(len(n) <= 20 for _, n in localidades):
        buttons = [_button(f"loc:{lid}", nombre) for lid, nombre in localidades]
        return _interactive_buttons(
            body="¿Cuál de estos es?", buttons=buttons,
        )
    rows = [_fila_localidad(f"loc:{lid}", nombre) for lid, nombre in localidades[:9]]
    rows.append(_row("menu", "↩️ Volver al menú"))
    return _interactive_list(
        body="¿Cuál de estos es?",
        button_label="Elegir",
        sections=[_section("Coincidencias", rows)],
    )


def build_confirmar(localidad_nombre: str) -> dict:
    return _interactive_buttons(
        body=f"¿Querías decir {localidad_nombre}?",
        buttons=[_button("si", "Sí"), _button("no", "No")],
    )


def build_escribir(campo: str, texto: str) -> dict:
    boton_volver = "cambiar_origen" if campo == "destino" else "menu"
    titulo_volver = "↩️ Menú" if boton_volver == "menu" else "↩️ Cambiar origen"
    return _interactive_buttons(
        body=texto,
        buttons=[
            _button("lineas:0", "🚌 Ver por línea"),
            _button(boton_volver, titulo_volver),
        ],
    )


# ── Localidad pendiente (P15/P32) ─────────────────────────────────────────


def _titulo_usar(nombre: str) -> str:
    """"Usar {nombre}" en 20 caracteres como mucho: nombre completo; si no
    cabe, sin el complemento " de/del ..."; si no, la primera palabra; último
    recurso, truncar."""
    prefijo = "Usar "
    candidatos = [nombre]
    corte = re.split(r"\s+(?:de|del)\s+", nombre, maxsplit=1)[0]
    candidatos.append(corte)
    candidatos.append(nombre.split()[0] if nombre.split() else nombre)
    for c in candidatos:
        if len(prefijo + c) <= MAX_TITULO_BOTON:
            return prefijo + c
    return _trunc(prefijo + candidatos[-1], MAX_TITULO_BOTON)


def build_localidad_pendiente(
    texto: str, ver_id: str, ver_nombre: str, campo: str
) -> dict:
    """Aldea sin hora de paso: ofrece consultar en su lugar la localidad `ver`
    o escribir otro pueblo. 2 botones."""
    return _interactive_buttons(
        body=texto,
        buttons=[
            _button(f"usar:{ver_id}", _titulo_usar(ver_nombre)),
            _button("escribir", "✍️ Otro pueblo"),
        ],
    )


# ── Pueblos por línea (P18) ───────────────────────────────────────────


def descripcion_linea(linea, n_pueblos: int) -> str:
    """Descripción de la fila de una línea en la lista de líneas: "<nombre> ·
    N pueblos" si la línea tiene título corto (el nombre completo no cabe en el
    título de fila), o solo "N pueblos". Se recorta el nombre, nunca el
    recuento. Función pura, también la usa la vista de revisión."""
    cuenta = "1 pueblo" if n_pueblos == 1 else f"{n_pueblos} pueblos"
    if not linea.nombre_corto:
        return cuenta
    sufijo = f" · {cuenta}"
    nombre = linea.nombre
    if len(nombre) + len(sufijo) > MAX_DESCRIPCION_FILA:
        nombre = _trunc(nombre, MAX_DESCRIPCION_FILA - len(sufijo) - 1) + "…"
    return nombre + sufijo


def build_lineas(lineas: list, pagina: int, hay_mas: bool, campo: str) -> dict:
    """lineas: lista de (Linea, n_pueblos) ya recortada a como mucho 8 (la
    página actual). 8 + "Más líneas" + volver = 10 filas."""
    rows = [
        _row(f"linea:{linea.id}:0", linea.titulo, descripcion_linea(linea, n))
        for linea, n in lineas[:8]
    ]
    if hay_mas:
        rows.append(_row(f"lineas:{pagina + 1}", "➡️ Más líneas"))
    if campo == "origen":
        rows.append(_row("menu", "↩️ Volver al menú"))
    else:
        rows.append(_row("cambiar_origen", "↩️ Cambiar origen"))
    return _interactive_list(
        body="¿Qué línea pasa por tu pueblo?",
        button_label="Ver líneas",
        sections=[_section("Líneas", rows)],
    )


def build_linea(linea, pueblos_pagina: list[tuple[str, str]], pagina: int,
                hay_mas: bool) -> dict:
    """pueblos_pagina: lista de (id, nombre), como mucho 8."""
    rows = [_fila_localidad(f"loc:{lid}", nombre) for lid, nombre in pueblos_pagina[:8]]
    if hay_mas:
        rows.append(_row(f"linea:{linea.id}:{pagina + 1}", "➡️ Ver más"))
    rows.append(_row("lineas:0", "↩️ Volver a líneas"))
    return _interactive_list(
        header=f"🚌 {linea.titulo}",
        body="Elige tu pueblo:",
        button_label="Ver pueblos",
        sections=[_section(linea.titulo, rows)],
    )


# ── Día ────────────────────────────────────────────────────────────────


def build_dias(
    origen_nombre: str,
    destino_nombre: str,
    filas: list[tuple[str, str, str]],
    aviso: str | None = None,
) -> dict:
    """filas: lista de (id "dia:<ISO>", titulo, descripcion), máximo 7."""
    rows = [_row(id_, titulo, desc) for id_, titulo, desc in filas]
    rows.append(_row("otra_fecha", "📅 Otra fecha"))
    body = "¿Qué día viajas?"
    if aviso:
        body = f"{aviso}\n\n{body}"
    return _interactive_list(
        header=f"🚌 {origen_nombre} → {destino_nombre}",
        body=body,
        button_label="Ver días",
        sections=[_section("Días", rows)],
    )


# ── Resultado ─────────────────────────────────────────────────────────


def build_resultado(texto: str, botones: list[tuple[str, str]]) -> dict:
    """botones: lista de (id, titulo), máximo 3."""
    return _interactive_buttons(
        body=texto,
        buttons=[_button(id_, titulo) for id_, titulo in botones[:3]],
    )
