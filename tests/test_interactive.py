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
    build_zona,
    build_zonas,
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
    _assert_list_limits(build_origen(localidades, con_zonas=True))


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


def test_build_zonas_within_limits():
    datos = horarios_datos.actual()
    zonas = [(z.id, z.nombre) for z, _ in __import__(
        "app.utils.matcher", fromlist=["zonas"]
    ).zonas(datos.horarios)]
    _assert_list_limits(build_zonas(zonas, "origen"))


def test_build_zona_within_limits():
    datos = horarios_datos.actual()
    todas = list(datos.horarios.modelo.localidades.items())[:8]
    localidades_pagina = [(lid, loc.nombre) for lid, loc in todas]
    _assert_list_limits(
        build_zona("Los Pedroches", "los-pedroches", 0, localidades_pagina, True)
    )
    _assert_list_limits(
        build_zona("Los Pedroches", "los-pedroches", 0, localidades_pagina, False)
    )


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
