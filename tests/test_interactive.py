"""tests/test_interactive.py — ninguna lista supera 10 filas ni ningún botón
3 (design.md, 4 y 9). La prueba más importante: la lista de destinos depende
del origen elegido y nunca puede pasarse del límite."""
from app.handlers import flujo
from app.services.horarios import datos as horarios_datos, query
from app.utils.interactive import (
    build_candidatas,
    build_confirmar,
    build_destinos,
    build_dias,
    build_escribir,
    build_info,
    build_menu,
    build_origen,
    build_resultado,
    build_linea,
    build_lineas,
    descripcion_linea,
)

MAX_ROWS = 10
MAX_BUTTONS = 3
MAX_ROW_TITLE = 24
MAX_ROW_DESC = 72
MAX_BUTTON_TITLE = 20


def _rows(payload: dict) -> list[dict]:
    sections = payload["interactive"]["action"]["sections"]
    return [row for section in sections for row in section["rows"]]


def _buttons(payload: dict) -> list[dict]:
    return payload["interactive"]["action"]["buttons"]


def _assert_list_limits(payload: dict) -> None:
    assert payload["interactive"]["type"] == "list"
    rows = _rows(payload)
    assert len(rows) <= MAX_ROWS, f"{len(rows)} rows > {MAX_ROWS}"
    for row in rows:
        assert len(row["title"]) <= MAX_ROW_TITLE
        if "description" in row:
            assert len(row["description"]) <= MAX_ROW_DESC


def _assert_button_limits(payload: dict) -> None:
    assert payload["interactive"]["type"] == "button"
    buttons = _buttons(payload)
    assert len(buttons) <= MAX_BUTTONS
    for b in buttons:
        assert len(b["reply"]["title"]) <= MAX_BUTTON_TITLE


def test_menu_within_limits():
    _assert_button_limits(build_menu())


def test_info_within_limits():
    _assert_button_limits(build_info())


def test_build_origen_within_limits():
    datos = horarios_datos.actual()
    localidades = [
        (lid, datos.horarios.modelo.localidades[lid].nombre)
        for lid in datos.menu_origen
    ]
    _assert_list_limits(build_origen(localidades))
    _assert_list_limits(build_origen(localidades, con_lineas=True))


def test_build_destinos_every_real_origin_within_limits():
    """Propiedad obligatoria (plan fase 4): recorre TODOS los orígenes
    reales de horarios/ y comprueba que la lista de destinos nunca supera
    el límite de WhatsApp, sea cual sea su longitud."""
    datos = horarios_datos.actual()
    horarios = datos.horarios
    for origen_id in horarios.localidad_viajes:
        alcanzables = list(query.destinos_desde(horarios, origen_id))
        if not alcanzables:
            continue
        nombres = {
            lid: horarios.modelo.localidades[lid].nombre for lid in alcanzables
        }
        prioridad = list(datos.menu_origen)
        ordenados = flujo.ordenar_destinos(alcanzables, prioridad, nombres)
        origen_nombre = horarios.modelo.localidades[origen_id].nombre
        payload = build_destinos(origen_nombre, ordenados)
        _assert_list_limits(payload)


def test_build_candidatas_within_limits():
    datos = horarios_datos.actual()
    localidades = [
        (lid, datos.horarios.modelo.localidades[lid].nombre)
        for lid in list(datos.horarios.modelo.localidades)[:9]
    ]
    payload = build_candidatas(localidades, "origen")
    if payload["interactive"]["type"] == "list":
        _assert_list_limits(payload)
    else:
        _assert_button_limits(payload)


def test_build_confirmar_within_limits():
    _assert_button_limits(build_confirmar("Pozoblanco"))


def test_build_escribir_within_limits():
    _assert_button_limits(build_escribir("origen", "texto"))


def _lineas_reales():
    from app.utils.matcher import lineas

    datos = horarios_datos.actual()
    return lineas(datos.horarios)


def _titulo_utf16(texto: str) -> int:
    return len(texto.encode("utf-16-le")) // 2


def _assert_titulos_whatsapp(payload: dict) -> None:
    """El título de fila se cuenta en code points y en unidades UTF-16."""
    for row in _rows(payload):
        assert len(row["title"]) <= MAX_ROW_TITLE
        assert _titulo_utf16(row["title"]) <= MAX_ROW_TITLE, row["title"]


def _linea_falsa(n: int, nombre_corto: str | None = None, nombre: str | None = None):
    from app.services.horarios.modelo import Linea

    return Linea(
        id=f"linea-{n:02d}",
        nombre=nombre or f"Linea {n:02d}",
        telefono_demanda=None,
        avisos=(),
        no_circula=(),
        temporadas=(),
        nombre_corto=nombre_corto,
    )


def test_build_lineas_real_within_limits():
    from app.utils.matcher import paginar

    todas = [(linea, len(locs)) for linea, locs in _lineas_reales()]
    assert len(todas) == 15
    paginas = paginar(todas)
    assert [len(p) for p in paginas] == [8, 7]
    lineas = list(paginas[1])
    for campo in ("origen", "destino"):
        payload = build_lineas(lineas, 0, False, campo)
        _assert_list_limits(payload)
        _assert_titulos_whatsapp(payload)
    ids = [r["id"] for r in _rows(build_lineas(lineas, 0, False, "origen"))]
    assert ids[-1] == "menu"
    ids = [r["id"] for r in _rows(build_lineas(lineas, 0, False, "destino"))]
    assert ids[-1] == "cambiar_origen"


def test_build_lineas_pagina_0_con_mas_lineas_son_10_filas():
    lineas = [(_linea_falsa(n), 3) for n in range(1, 9)]
    rows = _rows(build_lineas(lineas, 0, True, "origen"))
    assert len(rows) == 10
    assert rows[8] == {"id": "lineas:1", "title": "➡️ Más líneas"}
    assert rows[9]["id"] == "menu"
    assert rows[0]["id"] == "linea:linea-01:0"


def test_build_lineas_15_lineas_dos_paginas(datos_muchas_lineas):
    from app.utils.matcher import lineas, paginar

    todas = [(linea, len(locs)) for linea, locs in lineas(datos_muchas_lineas.horarios)]
    paginas = paginar(todas)
    assert len(todas) == 12
    assert [len(p) for p in paginas] == [8, 4]
    p0 = build_lineas(list(paginas[0]), 0, True, "origen")
    p1 = build_lineas(list(paginas[1]), 1, False, "origen")
    assert len(_rows(p0)) == 10
    assert len(_rows(p1)) == 4 + 1  # 4 líneas + volver
    _assert_list_limits(p0)
    _assert_list_limits(p1)
    _assert_titulos_whatsapp(p0)
    _assert_titulos_whatsapp(p1)
    assert _rows(p0)[8]["id"] == "lineas:1"
    assert _rows(p1)[-1]["id"] == "menu"
    assert all(r["id"] != "lineas:2" for r in _rows(p1))


def test_build_lineas_nombre_corto_en_titulo_y_descripcion():
    linea = _linea_falsa(
        1, nombre_corto="Ruta del norte",
        nombre="Ruta muy larga del norte al sur de la sierra",
    )
    fila = _rows(build_lineas([(linea, 2)], 0, False, "origen"))[0]
    assert fila["title"] == "Ruta del norte"
    assert fila["description"] == (
        "Ruta muy larga del norte al sur de la sierra · 2 pueblos"
    )


def test_descripcion_linea_singular_y_sin_nombre_corto():
    assert descripcion_linea(_linea_falsa(1), 1) == "1 pueblo"
    assert descripcion_linea(_linea_falsa(1), 5) == "5 pueblos"
    fila = _rows(build_lineas([(_linea_falsa(1), 1)], 0, False, "origen"))[0]
    assert fila["description"] == "1 pueblo"


def test_descripcion_linea_nombre_largo_no_come_el_recuento():
    linea = _linea_falsa(1, nombre_corto="Corta", nombre="X" * 200)
    desc = descripcion_linea(linea, 12)
    assert len(desc) <= MAX_ROW_DESC
    assert desc.endswith(" · 12 pueblos")
    fila = _rows(build_lineas([(linea, 12)], 0, False, "destino"))[0]
    assert fila["description"] == desc


def test_build_linea_20_pueblos_3_paginas(datos_muchas_lineas):
    from app.utils.matcher import lineas, paginar

    larga, locs = next(
        (li, lo) for li, lo in lineas(datos_muchas_lineas.horarios)
        if li.id == "linea-larga"
    )
    assert len(locs) == 19  # origen + 18
    paginas = paginar(locs)
    assert [len(p) for p in paginas] == [8, 8, 3]
    for n, pagina in enumerate(paginas):
        hay_mas = n + 1 < len(paginas)
        filas = [(loc.id, loc.nombre) for loc in pagina]
        payload = build_linea(larga, filas, n, hay_mas)
        _assert_list_limits(payload)
        _assert_titulos_whatsapp(payload)
        rows = _rows(payload)
        assert rows[-1]["id"] == "lineas:0"
        if hay_mas:
            assert rows[-2]["id"] == f"linea:linea-larga:{n + 1}"
        assert len(rows) <= 10
        assert payload["interactive"]["header"]["text"] == "🚌 Linea Larga"


def test_build_linea_titulo_corto_en_cabecera_y_seccion():
    linea = _linea_falsa(
        1, nombre_corto="Ruta del norte",
        nombre="Ruta muy larga del norte al sur de la sierra",
    )
    payload = build_linea(linea, [("a", "Aldea")], 0, False)
    assert payload["interactive"]["header"]["text"] == "🚌 Ruta del norte"
    assert payload["interactive"]["action"]["sections"][0]["title"] == "Ruta del norte"


def test_build_escribir_boton_ver_por_linea():
    for campo in ("origen", "destino"):
        botones = _buttons(build_escribir(campo, "texto"))
        assert botones[0]["reply"]["id"] == "lineas:0"
        assert botones[0]["reply"]["title"] == "🚌 Ver por línea"
        assert len(botones) <= MAX_BUTTONS


def test_filas_ver_pueblos_por_linea_en_origen_y_destino():
    datos = horarios_datos.actual()
    localidades = [
        (lid, datos.horarios.modelo.localidades[lid].nombre)
        for lid in datos.menu_origen
    ]
    rows = _rows(build_origen(localidades, con_lineas=True))
    assert {"id": "lineas:0", "title": "🚌 Ver pueblos por línea"} in rows
    _assert_titulos_whatsapp(build_origen(localidades, con_lineas=True))
    nombres = [(f"x{i}", f"Pueblo {i}") for i in range(12)]
    payload = build_destinos("Origen", nombres, con_lineas=True)
    assert {"id": "lineas:0", "title": "🚌 Ver pueblos por línea"} in _rows(payload)
    _assert_list_limits(payload)
    _assert_titulos_whatsapp(payload)


def test_build_dias_within_limits():
    filas = [(f"dia:2026-09-{20+i}", f"Fila {i}", "5 salidas") for i in range(7)]
    _assert_list_limits(build_dias("Pozoblanco", "Córdoba", filas))


def test_build_resultado_within_limits():
    botones = [("otro_dia", "📅 Otro día"), ("vuelta", "🔄 Ver la vuelta"),
               ("otra_consulta", "🔍 Otra consulta")]
    _assert_button_limits(build_resultado("texto", botones))


def test_truncated_locality_names_keep_full_name_in_description():
    nombre_largo = "Villafranca de los Barros muy largo de verdad"
    payload = build_origen([("villafranca-de-los-barros", nombre_largo)])
    fila = _rows(payload)[0]
    assert len(fila["title"]) <= MAX_ROW_TITLE
    assert fila["description"] == nombre_largo[:MAX_ROW_DESC]


def test_msg_resultado_truncates_at_4096_chars():
    from datetime import time
    from app.services.horarios.calendario import InfoDia
    from app.services.horarios.query import Consulta, Salida
    from app.utils.messages import msg_resultado

    salidas = tuple(
        Salida(
            hora_salida=time(6, 0),
            hora_llegada=time(8, 0),
            duracion_min=120,
            parada_origen="POZ",
            parada_destino="COR",
            lineas=("pozoblanco-cordoba",),
            notas=(f"Nota número {i} bastante larga para forzar el truncado.",),
        )
        for i in range(200)
    )
    consulta = Consulta(
        estado="con_salidas",
        salidas=salidas,
        info_dia=InfoDia(
            fecha=__import__("datetime").date(2026, 9, 23),
            dia_semana="miercoles",
            clase_dia="miercoles",
            es_festivo=False,
            nombre_festivo=None,
            es_lectivo=True,
            mes=9,
        ),
        temporadas=(),
        lineas_sin_datos=(),
        fuera_de_calendario=False,
        siguiente_con_servicio=None,
    )
    datos = horarios_datos.actual()
    texto = msg_resultado(consulta, datos.horarios, "Pozoblanco", "Córdoba",
                           __import__("datetime").date(2026, 9, 23))
    assert len(texto) <= 4096
    assert "más, llama al" in texto


def test_msg_resultado_sin_servicio_general_sin_siguiente_da_hecho_y_telefono():
    from datetime import date

    from app.services.horarios import calendario as cal
    from app.services.horarios.query import Consulta
    from app.utils.messages import msg_resultado

    datos = horarios_datos.actual()
    fecha = date(2027, 12, 25)
    consulta = Consulta(
        estado="sin_servicio",
        salidas=(),
        info_dia=cal.info_dia(
            datos.horarios.modelo.calendario, fecha, permitir_fuera_de_vigencia=True
        ),
        temporadas=(),
        lineas_sin_datos=(),
        fuera_de_calendario=False,
        siguiente_con_servicio=None,
        sin_servicio_general=True,
    )
    texto = msg_resultado(consulta, datos.horarios, "Pozoblanco", "Córdoba", fecha)
    assert "El 25/12 no hay servicio en ninguna línea" in texto
    assert "957 42 90 30" in texto
    assert "próximos días" not in texto
    assert "festivo" not in texto  # sin nombre cargado, la cabecera es solo el día


def test_lista_de_destinos_con_no_vendibles_filtrados_respeta_limites():
    datos = horarios_datos.actual()
    horarios = datos.horarios
    for origen_id in ("cordoba", "campus-de-rabanales", "alcolea"):
        alcanzables = list(query.destinos_desde(horarios, origen_id))
        assert alcanzables
        for otro in ("cordoba", "campus-de-rabanales", "alcolea"):
            if otro != origen_id:
                assert otro not in alcanzables
        nombres = {
            lid: horarios.modelo.localidades[lid].nombre for lid in alcanzables
        }
        ordenados = flujo.ordenar_destinos(
            alcanzables, list(datos.menu_origen), nombres
        )
        payload = build_destinos(
            horarios.modelo.localidades[origen_id].nombre, ordenados
        )
        _assert_list_limits(payload)
        assert len(_rows(payload)) <= MAX_ROWS


# ── Fase 1b-1: Pozoblanco con 19 destinos y nombre largo de la Estación AVE ──

NOMBRE_LARGO = "Estación AVE Villanueva de Córdoba"


def test_destinos_de_pozoblanco_son_10_filas_con_los_8_esperados():
    datos = horarios_datos.actual()
    horarios = datos.horarios
    alcanzables = list(query.destinos_desde(horarios, "pozoblanco"))
    assert len(alcanzables) > 9
    nombres = {lid: horarios.modelo.localidades[lid].nombre for lid in alcanzables}
    ordenados = flujo.ordenar_destinos(alcanzables, list(datos.menu_origen), nombres)
    payload = build_destinos("Pozoblanco", ordenados)
    _assert_list_limits(payload)
    filas = _rows(payload)
    assert len(filas) == 10
    assert [f["title"] for f in filas[:8]] == [
        "Córdoba",
        "Villanueva de Córdoba",
        "Hinojosa del Duque",
        "Belalcázar",
        "Alcaracejos",
        "Añora",
        "Cardeña",
        "Conquista",
    ]
    assert [f["id"] for f in filas[8:]] == ["escribir", "cambiar_origen"]


def test_nombre_largo_estacion_ave_respeta_limites_en_todos_los_constructores():
    assert len(NOMBRE_LARGO) > MAX_ROW_TITLE
    fila = _rows(build_origen([("estacion-ave-villanueva", NOMBRE_LARGO)]))[0]
    assert len(fila["title"]) <= MAX_ROW_TITLE
    assert fila["description"] == NOMBRE_LARGO

    _assert_button_limits(build_confirmar(NOMBRE_LARGO))

    # nombre largo: build_candidatas pasa de botones a lista
    cands = build_candidatas(
        [
            ("estacion-ave-villanueva", NOMBRE_LARGO),
            ("villanueva-de-cordoba", "Villanueva"),
        ],
        "destino",
    )
    _assert_list_limits(cands)
    assert NOMBRE_LARGO in [r.get("description") for r in _rows(cands)]

    _assert_list_limits(
        build_dias(
            "Pozoblanco", NOMBRE_LARGO, [("dia:2026-10-01", "Jueves 1", "2 salidas")]
        )
    )


# ── Localidad pendiente (ciclo C2, P15/P32) ──────────────────────────────


def test_build_localidad_pendiente_within_limits():
    from app.utils.interactive import build_localidad_pendiente

    for nombre in ("Pozoblanco", "Almodóvar del Río", "Villanueva de Córdoba",
                   "Villafranca de los Barros", "Santa Eufemia del Norte"):
        payload = build_localidad_pendiente("Texto", "ver-id", nombre, "origen")
        _assert_button_limits(payload)
        ids = [b["reply"]["id"] for b in _buttons(payload)]
        assert ids == ["usar:ver-id", "escribir"]


def test_build_localidad_pendiente_acorta_nombre_largo():
    from app.utils.interactive import build_localidad_pendiente

    def titulo(nombre):
        p = build_localidad_pendiente("t", "x", nombre, "destino")
        return _buttons(p)[0]["reply"]["title"]

    assert titulo("Pozoblanco") == "Usar Pozoblanco"
    assert titulo("Almodóvar del Río") == "Usar Almodóvar"
    assert titulo("Villanueva de Córdoba") == "Usar Villanueva"
    assert titulo("Superextraordinariamente") == "Usar Superextraordin"


def test_build_localidad_pendiente_los_mochos_real():
    from app.utils.interactive import build_localidad_pendiente

    modelo = horarios_datos.actual().horarios.modelo
    mochos = modelo.localidades["los-mochos"]
    ver = modelo.localidades[mochos.ver]
    payload = build_localidad_pendiente("Texto", mochos.ver, ver.nombre, "origen")
    _assert_button_limits(payload)
    titulos = [b["reply"]["title"] for b in _buttons(payload)]
    assert titulos[0] == "Usar Almodóvar"
    assert len(titulos[0]) <= 20
