"""tests/test_conversation.py — flujo completo y casos borde (design.md 4.8,
plan fase 4 paso 13)."""
from datetime import date, timedelta

import pytest

import app.handlers.conversation as conv

HOY = date(2026, 9, 23)  # miércoles, dentro de vigencia (design.md ejemplo)


def _last_interactive(mock_wa):
    return mock_wa["interactive"].call_args[0][1]


def _last_text(mock_wa):
    return mock_wa["text"].call_args[0][1]


def _button_ids(payload):
    return [b["reply"]["id"] for b in payload["interactive"]["action"]["buttons"]]


def _row_ids(payload):
    return [
        row["id"]
        for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    ]


@pytest.fixture(autouse=True)
def _clear_states():
    conv._states.clear()
    yield
    conv._states.clear()


def test_happy_path(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000001"
    conv.handle_message(phone, phone, None, "menu_horarios")
    assert "pueblo" in _last_interactive(mock_wa)["interactive"]["body"]["text"].lower()

    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    payload = _last_interactive(mock_wa)
    assert "Desde Pozoblanco" in payload["interactive"]["header"]["text"]

    conv.handle_message(phone, phone, None, "loc:cordoba")
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "list"
    assert any(r.startswith("dia:") for r in _row_ids(payload))

    manana = (HOY + timedelta(days=1)).isoformat()
    conv.handle_message(phone, phone, None, f"dia:{manana}")
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "button"
    assert set(_button_ids(payload)) == {"otro_dia", "vuelta", "otra_consulta"}
    assert "Pozoblanco" in payload["interactive"]["body"]["text"]


def test_villafranca_ambiguity_always_asks(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000002"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "villafranca", None)
    payload = _last_interactive(mock_wa)
    ids = set(_row_ids(payload)) if payload["interactive"]["type"] == "list" else set(
        _button_ids(payload)
    )
    assert "loc:villafranca-de-cordoba" in ids
    assert "loc:villafranca-de-los-barros" in ids
    # no debe ser una confirmación sí/no
    assert not (payload["interactive"]["type"] == "button" and set(
        _button_ids(payload)) == {"si", "no"})


def test_villafranca_with_typo_still_asks(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000003"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "villafranka", None)
    payload = _last_interactive(mock_wa)
    ids = set(_row_ids(payload)) if payload["interactive"]["type"] == "list" else set(
        _button_ids(payload)
    )
    assert "loc:villafranca-de-cordoba" in ids
    assert "loc:villafranca-de-los-barros" in ids


def test_errata_confirms(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000004"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pozoblnco", None)
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "button"
    assert set(_button_ids(payload)) == {"si", "no"}
    assert "Pozoblanco" in payload["interactive"]["body"]["text"]

    conv.handle_message(phone, phone, None, "si")
    payload = _last_interactive(mock_wa)
    assert "Desde Pozoblanco" in payload["interactive"]["header"]["text"]


def test_sin_coincidencia_logs_no_phone(mock_wa, freeze_calendario, caplog):
    freeze_calendario(HOY)
    phone = "34600000005"
    conv.handle_message(phone, phone, None, "menu_horarios")
    import logging
    caplog.set_level(logging.INFO, logger="app.handlers.flujo")
    conv.handle_message(phone, phone, "xyzxyzxyz", None)
    assert any("[NO_RECONOCIDO]" in r.message for r in caplog.records)
    for r in caplog.records:
        if "[NO_RECONOCIDO]" in r.message:
            assert phone not in r.message


def test_origen_igual_destino(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000006"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    payload = _last_interactive(mock_wa)
    assert "distinto" in payload["interactive"]["body"]["text"].lower()


def test_sin_trayecto_directo(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000007"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, "badajoz", None)
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"].lower()
    assert "trayecto" in body or "no hay" in body


def test_fecha_pasada(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000008"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "otra_fecha")
    conv.handle_message(phone, phone, "20/09", None)
    all_texts = " ".join(c.args[1] for c in mock_wa["text"].call_args_list)
    assert "pasado" in all_texts.lower()


def test_hoy_sin_salidas_ofrece_mañana(mock_wa, freeze_calendario):
    freeze_calendario(HOY, hora=(23, 0))
    phone = "34600000009"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "button"
    ids = _button_ids(payload)
    assert any(i.startswith("dia:") for i in ids)
    assert "ya no quedan" in payload["interactive"]["body"]["text"].lower()


def test_estado_caducado_vuelve_al_menu(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000010"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    state = conv._get(phone)
    from datetime import datetime
    state.last_interaction = datetime(2000, 1, 1, tzinfo=state.last_interaction.tzinfo)
    conv.clean_expired_states()
    assert phone not in conv._states


def test_unknown_id_goes_to_menu(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000011"
    # Estado fresco (MENU): un id desconocido nunca debe tratarse como si
    # fuera válido en otro paso — vuelve al menú.
    conv.handle_message(phone, phone, None, "dia:2020-01-01")
    payload = _last_interactive(mock_wa)
    assert "necesitas" in payload["interactive"]["body"]["text"].lower()


def test_escape_words_return_to_menu(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000012"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "menu", None)
    payload = _last_interactive(mock_wa)
    assert "necesitas" in payload["interactive"]["body"]["text"].lower()


def test_one_outgoing_message_per_input(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000013"
    conv.handle_message(phone, phone, None, "menu_horarios")
    total_before = mock_wa["text"].call_count + mock_wa["interactive"].call_count
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    total_after = mock_wa["text"].call_count + mock_wa["interactive"].call_count
    assert total_after - total_before == 1


def test_unsupported_media_type_gives_fallback(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000014"
    conv.handle_message(phone, phone, conv.UNKNOWN_INPUT, None)
    assert mock_wa["text"].called


# ── Casos borde de 4.8 (correcciones fase 4, docs/rds_fase4_correcciones.md) ─

def _n_calls(mock_wa):
    return mock_wa["text"].call_count + mock_wa["interactive"].call_count


def test_dia_sin_servicio_ofrece_siguiente(mock_wa, freeze_calendario, datos_motor):
    sabado = date(2026, 9, 26)
    freeze_calendario(sabado)
    phone = "34600000101"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo a", None)
    conv.handle_message(phone, phone, "pueblo b", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{sabado.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"].lower()
    assert "no hay servicio" in body
    ids = _button_ids(payload)
    siguiente = date(2026, 9, 28)  # lunes: próximo día con servicio
    assert f"dia:{siguiente.isoformat()}" in ids

    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{siguiente.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert "no hay servicio" not in payload["interactive"]["body"]["text"].lower()


def test_sin_servicio_largo_sin_boton_dia(mock_wa, freeze_calendario, datos_motor):
    freeze_calendario(HOY)  # 23/09/2026, dentro del no_circula [septiembre]
    phone = "34600000102"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo p", None)
    conv.handle_message(phone, phone, "pueblo q", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "no hay salidas" in body.lower()
    assert "957" in body or "tel" in body.lower() or "📞" in body
    ids = _button_ids(payload)
    assert not any(i.startswith("dia:") for i in ids)


def test_dia_sin_datos_no_es_sin_servicio(mock_wa, freeze_calendario, datos_motor):
    freeze_calendario(HOY)
    phone = "34600000103"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo g", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "pueblo h", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    filas = [
        (row["id"], row.get("description", ""))
        for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    ]
    hoy_desc = next(desc for id_, desc in filas if id_ == f"dia:{HOY.isoformat()}")
    assert hoy_desc == "horario no disponible"

    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"].lower()
    assert "no hay servicio" not in body
    assert "no tengo el horario" in body


def test_fecha_fuera_de_vigencia_da_sin_datos(mock_wa, freeze_calendario, datos_motor):
    freeze_calendario(HOY)
    phone = "34600000104"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo a", None)
    conv.handle_message(phone, phone, "pueblo b", None)
    conv.handle_message(phone, phone, None, "otra_fecha")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "01/10/2027", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"].lower()
    assert "no tengo el horario" in body
    assert "no hay servicio" not in body


def test_salidas_con_linea_sin_datos_avisa(mock_wa, freeze_calendario, datos_motor):
    freeze_calendario(HOY)
    phone = "34600000105"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo e", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "pueblo f", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    filas = [
        (row["id"], row.get("description", ""))
        for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    ]
    hoy_desc = next(desc for id_, desc in filas if id_ == f"dia:{HOY.isoformat()}")
    assert "puede haber más" in hoy_desc

    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert "puede haber más" in payload["interactive"]["body"]["text"].lower()


def test_a_demanda_incluye_telefono_de_la_linea(
    mock_wa, freeze_calendario, datos_motor
):
    freeze_calendario(HOY)
    phone = "34600000106"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo k", None)
    conv.handle_message(phone, phone, "pueblo l", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "957 00 00 00" in body


def test_viernes_lectivo_solo_corre_en_viernes_de_curso(
    mock_wa, freeze_calendario, datos_motor
):
    viernes_lectivo = date(2026, 9, 25)
    freeze_calendario(viernes_lectivo)
    phone = "34600000107"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo a", None)
    conv.handle_message(phone, phone, "pueblo b", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{viernes_lectivo.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "09:00" in body
    assert "Solo viernes en periodo escolar." in body

    jueves = date(2026, 9, 24)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{jueves.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "09:00" not in body


def test_horas_aproximadas_sin_marca_numerica(mock_wa, freeze_calendario, datos_motor):
    freeze_calendario(HOY)
    phone = "34600000108"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo r", None)
    conv.handle_message(phone, phone, "pueblo s", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "⚠️ Horarios de paso aproximados." in body
    for marca in "¹²³⁴⁵⁶⁷⁸⁹":
        assert marca not in body


def test_otro_dia_vuelve_a_sel_dia_mismo_trayecto(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000109"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "otro_dia")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "list"
    assert "Pozoblanco → Córdoba" in payload["interactive"]["header"]["text"]


def test_ver_la_vuelta_con_trayecto_valido(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000110"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "vuelta")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "list"
    assert "Córdoba → Pozoblanco" in payload["interactive"]["header"]["text"]


def test_ver_la_vuelta_sin_trayecto(mock_wa, freeze_calendario, datos_motor):
    """Único camino que no se pudo colapsar a un solo mensaje (documentado en
    el resumen del coder): sin trayecto de vuelta manda un texto y después
    vuelve al menú con un interactivo, porque `build_menu()` no acepta un
    aviso en el cuerpo y no se puede tocar `interactive.py` en esta fase."""
    freeze_calendario(HOY)
    phone = "34600000111"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pueblo a", None)
    conv.handle_message(phone, phone, "pueblo c", None)
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "vuelta")
    assert _n_calls(mock_wa) - total_before == 2
    assert "trayecto" in _last_text(mock_wa).lower()


def test_otra_consulta_muestra_lista_origen(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000112"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "otra_consulta")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert "pueblo" in payload["interactive"]["body"]["text"].lower()


def test_zonas_en_origen_pagina(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000113"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "escribir")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "zonas")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert any(r.startswith("zona:extremadura:0") for r in _row_ids(payload))

    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "zona:extremadura:0")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    rows = _row_ids(payload)
    assert "zona:extremadura:1" in rows

    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "zona:extremadura:1")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert "zona:extremadura:2" not in _row_ids(payload)


def test_zonas_en_destino_solo_alcanzables(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000114"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, "escribir", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "zonas", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    zonas_ids = {r.split(":")[1] for r in _row_ids(payload) if r.startswith("zona:")}
    assert "adamuz" not in zonas_ids
    assert "extremadura" not in zonas_ids
    assert "los-pedroches" in zonas_ids


def test_demasiadas_coincidencias_pide_mas_concreto(mock_wa, freeze_calendario):
    from app.services.horarios import datos as horarios_datos
    from app.utils.matcher import Coincidencia

    freeze_calendario(HOY)
    phone = "34600000115"
    conv.handle_message(phone, phone, None, "menu_horarios")
    datos = horarios_datos.actual()
    original = datos.matcher.buscar
    datos.matcher.buscar = lambda texto: Coincidencia(
        tipo="demasiadas", localidades=(), texto_normalizado="a"
    )
    total_before = _n_calls(mock_wa)
    try:
        conv.handle_message(phone, phone, "a", None)
    finally:
        datos.matcher.buscar = original
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"].lower()
    assert "concreto" in body


def test_no_tras_confirmar_pide_escribirlo_de_otra_forma(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000116"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, "pozoblnco", None)
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "no")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "button"
    body = payload["interactive"]["body"]["text"].lower()
    assert "otra forma" in body
    botones = payload["interactive"]["action"]["buttons"]
    assert any(b["reply"]["id"] == "zonas" for b in botones)
    assert conv._get(phone).step == conv.flujo.ESCRIBIR_ORIGEN


def test_fecha_escrita_directamente_en_lista_de_dias(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000117"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "25/12", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "button"


def test_texto_no_valido_en_lista_de_dias_un_solo_mensaje(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000118"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "mañana", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert payload["interactive"]["type"] == "list"
    assert "lista" in payload["interactive"]["body"]["text"].lower()


def test_fecha_pasada_en_lista_de_dias_un_solo_mensaje(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000119"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "20/09", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    assert "pasado" in payload["interactive"]["body"]["text"].lower()


def test_fecha_pasada_en_escribir_fecha_un_solo_mensaje(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000120"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "otra_fecha")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, "20/09", None)
    assert _n_calls(mock_wa) - total_before == 1
    text = _last_text(mock_wa)
    assert "pasado" in text.lower()
    assert "25/12" in text  # formato de ejemplo, en el mismo mensaje


def test_origen_con_mas_de_9_destinos_muestra_10_filas(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000121"
    conv.handle_message(phone, phone, None, "menu_horarios")
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, None, "loc:cordoba")
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    filas = [
        row for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    ]
    assert len(filas) == 10
    assert any("Otro destino" in row["title"] for row in filas)


def test_log_redaction_numero_telefono(mock_wa, freeze_calendario, caplog):
    import logging

    freeze_calendario(HOY)
    phone = "34600000122"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "otra_fecha")
    caplog.set_level(logging.INFO, logger="app.handlers.flujo")
    numero = "612345678"
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, numero, None)
    assert _n_calls(mock_wa) - total_before == 1
    encontrado = False
    for r in caplog.records:
        if "[NO_RECONOCIDO]" in r.message:
            encontrado = True
            assert numero not in r.message
            assert "<numero>" in r.message
    assert encontrado


def test_log_redaction_numero_telefono_con_separadores(
    mock_wa, freeze_calendario, caplog
):
    """`formato.normalizar()` sustituye separadores por espacios, así que un
    número escrito con espacios o guiones no debe colar como si tuviera menos
    de 6 dígitos consecutivos (design.md, 4.7)."""
    import logging

    freeze_calendario(HOY)
    phone = "34600000124"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "otra_fecha")
    caplog.set_level(logging.INFO, logger="app.handlers.flujo")
    numero = "612 34 56 78"
    total_before = _n_calls(mock_wa)
    conv.handle_message(phone, phone, numero, None)
    assert _n_calls(mock_wa) - total_before == 1
    encontrado = False
    for r in caplog.records:
        assert numero not in r.message
        if "[NO_RECONOCIDO]" in r.message:
            encontrado = True
            assert "<numero>" in r.message
    assert encontrado


def test_admin_status_solo_desde_admin_phone(mock_wa, freeze_calendario, monkeypatch):
    freeze_calendario(HOY)
    monkeypatch.setattr(conv, "ADMIN_PHONE", "34699999999")
    admin_phone = "34699999999"
    total_before = _n_calls(mock_wa)
    conv.handle_message(admin_phone, admin_phone, "/status", None)
    assert _n_calls(mock_wa) - total_before == 1
    text = _last_text(mock_wa)
    assert "Estado del sistema" in text

    otro_phone = "34600000123"
    total_before = _n_calls(mock_wa)
    conv.handle_message(otro_phone, otro_phone, "/status", None)
    assert _n_calls(mock_wa) - total_before == 1
    payload = _last_interactive(mock_wa)
    # no es un comando de administrador: se trata como texto normal, vuelve
    # al menú (id/texto desconocido)
    assert "necesitas" in payload["interactive"]["body"]["text"].lower()


# ── Sin servicio en ninguna línea (P03g) ────────────────────────────────────


def test_lista_de_dias_muestra_sin_servicio_el_25_12(mock_wa, freeze_calendario):
    freeze_calendario(date(2026, 12, 22))
    phone = "34600000201"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    payload = _last_interactive(mock_wa)
    filas = {
        row["id"]: row
        for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    }
    fila = filas["dia:2026-12-25"]
    assert fila["description"] == "festivo · sin servicio"
    assert len(fila["description"]) <= 72


def test_resultado_25_12_sin_servicio_en_ninguna_linea(mock_wa, freeze_calendario):
    freeze_calendario(date(2026, 12, 22))
    phone = "34600000202"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "dia:2026-12-25")
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "festivo (Navidad)" in body
    assert "El 25/12 no hay servicio en ninguna línea" in body
    assert "957 42 90 30" in body
    assert "sábado 26/12" in body
    assert "dia:2026-12-26" in _button_ids(payload)
    assert "No hay salidas en los próximos días" not in body


# ── Festivos locales (P03e) ────────────────────────────────────────────────


def test_festivo_local_de_cordoba_en_lista_y_resultado(mock_wa, freeze_calendario):
    freeze_calendario(date(2026, 10, 20))
    phone = "34600000203"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    payload = _last_interactive(mock_wa)
    filas = {
        row["id"]: row
        for section in payload["interactive"]["action"]["sections"]
        for row in section["rows"]
    }
    descripcion = filas["dia:2026-10-24"]["description"]
    assert descripcion.startswith("festivo · ")
    assert len(descripcion) <= 72
    assert not filas["dia:2026-10-23"]["description"].startswith("festivo")

    conv.handle_message(phone, phone, None, "dia:2026-10-24")
    body = _last_interactive(mock_wa)["interactive"]["body"]["text"]
    assert "festivo en Córdoba (San Rafael)" in body
    assert "17:45" in body


# ── Trayectos no vendibles (P12b) ──────────────────────────────────────────


def test_destino_escrito_no_vendible_da_mensaje_propio(mock_wa, freeze_calendario):
    freeze_calendario(HOY)
    phone = "34600000204"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, "Alcolea", None)
    payload = _last_interactive(mock_wa)
    body = payload["interactive"]["body"]["text"]
    assert "no vendemos billetes" in body
    assert "Córdoba" in body and "Alcolea" in body
    assert "No hay trayecto directo" not in body
    assert conv._get(phone).step == conv.flujo.SEL_DESTINO
    # y Alcolea no aparece como destino ofrecido
    assert "loc:alcolea" not in _row_ids(payload)


def test_destino_escrito_sin_trayecto_sigue_dando_sin_trayecto(
    mock_wa, freeze_calendario
):
    freeze_calendario(HOY)
    phone = "34600000205"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, "badajoz", None)
    body = _last_interactive(mock_wa)["interactive"]["body"]["text"]
    assert "No hay trayecto directo" in body
    assert "no vendemos" not in body


def test_cambio_de_origen_a_par_no_vendible_da_mensaje_propio(
    mock_wa, freeze_calendario
):
    # Rama defensiva de "ver la vuelta": se fuerza un estado cuyo par
    # invertido (alcolea -> campus-de-rabanales) es no vendible.
    freeze_calendario(HOY)
    phone = "34600000206"
    conv.handle_message(phone, phone, None, "menu_horarios")
    conv.handle_message(phone, phone, None, "loc:cordoba")
    conv.handle_message(phone, phone, None, "loc:pozoblanco")
    conv.handle_message(phone, phone, None, f"dia:{HOY.isoformat()}")
    state = conv._get(phone)
    state.origen, state.destino = "campus-de-rabanales", "alcolea"
    conv.handle_message(phone, phone, None, "vuelta")
    text = _last_text(mock_wa)
    assert "no vendemos billetes" in text
    assert "No hay trayecto directo" not in text
