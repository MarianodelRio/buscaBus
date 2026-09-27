"""tests/test_diff.py — altas, bajas y cambios de hora, de observaciones, de
temporadas y de días, en lenguaje de negocio (design.md, sección 9).

Construye Modelo/Linea/Viaje/Paso/Temporada a mano: diff.py es puro y no toca
disco ni invoca formato.validar()."""

from __future__ import annotations

from app.services.horarios import diff
from app.services.horarios.formato import Modelo
from app.services.horarios.modelo import (
    Linea,
    Observacion,
    Parada,
    Paso,
    Tabla,
    Temporada,
    Viaje,
)

PARADAS = {
    "AAA": Parada(codigo="AAA", nombre="Pueblo A", localidad="pueblo-a"),
    "BBB": Parada(codigo="BBB", nombre="Pueblo B", localidad="pueblo-b"),
    "CCC": Parada(codigo="CCC", nombre="Pueblo C", localidad="pueblo-c"),
    "DDD": Parada(codigo="DDD", nombre="Pueblo D", localidad="pueblo-d"),
}

OBSERVACIONES = {
    "entra_en_pueblo": Observacion(
        id="entra_en_pueblo",
        letra="P",
        tipo="aviso",
        ambitos=("parada",),
        texto="Este autobús entra en el pueblo.",
    ),
    "pasa_por_rivero": Observacion(
        id="pasa_por_rivero",
        letra=None,
        tipo="aviso",
        ambitos=("viaje",),
        texto="Pasa por Rivero de Posadas.",
    ),
}


def _modelo(lineas: dict[str, Linea]) -> Modelo:
    return Modelo(
        zonas={},
        localidades={},
        paradas=PARADAS,
        observaciones=OBSERVACIONES,
        lineas=lineas,
    )


def _tabla(
    linea="l1",
    temporada="anual",
    dias="lunes-viernes",
    codigos=("AAA", "BBB", "CCC"),
    posicion=0,
) -> Tabla:
    return Tabla(
        linea=linea,
        temporada=temporada,
        dias=dias,
        paradas=tuple(codigos),
        posicion=posicion,
    )


def _viaje(
    linea="l1",
    temporada="anual",
    dias="lunes-viernes",
    horas=("08:00", "08:10", "08:20"),
    obs_viaje=(),
    pendientes=(),
    obs_por_paso=None,
    codigos=("AAA", "BBB", "CCC"),
    tabla=None,
) -> Viaje:
    obs_por_paso = obs_por_paso or {}
    pasos = tuple(
        Paso(
            parada=codigo,
            hora=hora,
            observaciones=tuple(obs_por_paso.get(codigo, ())),
        )
        for codigo, hora in zip(codigos, horas)
    )
    if tabla is None:
        tabla = _tabla(linea=linea, temporada=temporada, dias=dias, codigos=codigos)
    return Viaje(
        linea=linea,
        temporada=temporada,
        dias=dias,
        tabla=tabla,
        observaciones=tuple(obs_viaje),
        pendientes=tuple(pendientes),
        pasos=pasos,
    )


def _linea(
    lid="l1",
    nombre="Línea 1",
    temporadas=(Temporada(nombre="anual", rango="todo el año"),),
    dias=None,
    viajes=(),
) -> Linea:
    dias = dias if dias is not None else {
        "anual": {
            "lunes": "horario",
            "martes": "horario",
            "miercoles": "horario",
            "jueves": "horario",
            "viernes": "horario",
            "sabado": "sin_servicio",
            "domingo": "sin_servicio",
            "festivos": "sin_servicio",
        }
    }
    return Linea(
        id=lid,
        nombre=nombre,
        telefono_demanda=None,
        avisos=(),
        no_circula=(),
        temporadas=temporadas,
        dias=dias,
        pendientes=(),
        viajes=viajes,
    )


def test_sin_cambios():
    v = _viaje()
    linea = _linea(viajes=(v,))
    modelo = _modelo({"l1": linea})
    assert diff.comparar(modelo, modelo) == []


def test_viaje_anadido():
    v1 = _viaje(horas=("08:00", "08:10", "08:20"))
    v2 = _viaje(horas=("09:00", "09:10", "09:20"))
    anterior = _modelo({"l1": _linea(viajes=(v1,))})
    actual = _modelo({"l1": _linea(viajes=(v1, v2))})
    mensajes = diff.comparar(anterior, actual)
    assert any("viaje añadido" in m for m in mensajes)


def test_viaje_quitado():
    v1 = _viaje(horas=("08:00", "08:10", "08:20"))
    v2 = _viaje(horas=("09:00", "09:10", "09:20"))
    anterior = _modelo({"l1": _linea(viajes=(v1, v2))})
    actual = _modelo({"l1": _linea(viajes=(v1,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("viaje quitado" in m for m in mensajes)


def test_hora_cambiada_en_un_paso():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"))
    v_act = _viaje(horas=("08:00", "08:15", "08:20"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "Pasa por Pueblo B: de las 08:10 a las 08:15" in m for m in mensajes
    )


def test_hora_cambiada_en_la_ultima_parada_dice_llega_a():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"))
    v_act = _viaje(horas=("08:00", "08:10", "08:25"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("Llega a Pueblo C: de las 08:20 a las 08:25" in m for m in mensajes)
    assert not any(
        "Pasa por Pueblo C" in m or "Sale de Pueblo C" in m for m in mensajes
    )


def test_hora_cambiada_en_la_primera_parada_dice_sale_de():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"))
    v_act = _viaje(horas=("08:05", "08:10", "08:20"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("Sale de Pueblo A: de las 08:00 a las 08:05" in m for m in mensajes)


def test_quitar_un_viaje_de_un_grupo_no_genera_cambios_falsos():
    v1 = _viaje(horas=("07:00", "07:10", "07:20"))
    v2 = _viaje(horas=("08:00", "08:10", "08:20"))
    v3 = _viaje(horas=("09:00", "09:10", "09:20"))
    v4 = _viaje(horas=("10:00", "10:10", "10:20"))
    anterior = _modelo({"l1": _linea(viajes=(v1, v2, v3, v4))})
    actual = _modelo({"l1": _linea(viajes=(v1, v2, v4))})
    mensajes = diff.comparar(anterior, actual)
    mensajes_viaje_quitado = [m for m in mensajes if "viaje quitado" in m]
    assert len(mensajes_viaje_quitado) == 1
    assert "09:00" in mensajes_viaje_quitado[0]
    assert not any("de las" in m and "a las" in m for m in mensajes)


def test_mover_un_viaje_dos_horas_es_alta_y_baja():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"))
    v_act = _viaje(horas=("10:00", "10:10", "10:20"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("viaje añadido" in m for m in mensajes)
    assert any("viaje quitado" in m for m in mensajes)
    assert not any("de las" in m and "a las" in m for m in mensajes)


def test_anadir_una_parada_al_viaje():
    v_ant = _viaje(horas=("08:00", "08:20"), codigos=("AAA", "CCC"))
    v_act = _viaje(horas=("08:00", "08:10", "08:20"), codigos=("AAA", "BBB", "CCC"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("ahora para en Pueblo B a las 08:10" in m for m in mensajes)


def test_quitar_una_parada_del_viaje():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"), codigos=("AAA", "BBB", "CCC"))
    v_act = _viaje(horas=("08:00", "08:20"), codigos=("AAA", "CCC"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any("ya no para en Pueblo B" in m for m in mensajes)


def test_reordenar_cabecera_sin_cambiar_horas_no_genera_cambios():
    # AAA y DDD (los extremos) se mantienen; solo se reordenan BBB y CCC en
    # medio, sin cambiar ninguna hora.
    tabla_ant = _tabla(codigos=("AAA", "BBB", "CCC", "DDD"))
    tabla_act = _tabla(codigos=("AAA", "CCC", "BBB", "DDD"))
    v_ant = _viaje(
        horas=("08:00", "08:10", "08:15", "08:20"),
        codigos=("AAA", "BBB", "CCC", "DDD"),
        tabla=tabla_ant,
    )
    v_act = _viaje(
        horas=("08:00", "08:15", "08:10", "08:20"),
        codigos=("AAA", "CCC", "BBB", "DDD"),
        tabla=tabla_act,
    )
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert mensajes == []


def test_observacion_anadida_en_paso():
    v_ant = _viaje(horas=("08:00", "08:10", "08:20"))
    v_act = _viaje(
        horas=("08:00", "08:10", "08:20"),
        obs_por_paso={"BBB": ("entra_en_pueblo",)},
    )
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "en Pueblo B: se añade la observación 'entra_en_pueblo'" in m
        for m in mensajes
    )


def test_observacion_quitada_en_paso():
    v_ant = _viaje(
        horas=("08:00", "08:10", "08:20"),
        obs_por_paso={"BBB": ("entra_en_pueblo",)},
    )
    v_act = _viaje(horas=("08:00", "08:10", "08:20"))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "en Pueblo B: se quita la observación 'entra_en_pueblo'" in m
        for m in mensajes
    )


def test_observacion_anadida_en_viaje():
    v_ant = _viaje()
    v_act = _viaje(obs_viaje=("pasa_por_rivero",))
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "se añade la observación de viaje 'pasa_por_rivero'" in m for m in mensajes
    )


def test_observacion_quitada_en_viaje():
    v_ant = _viaje(obs_viaje=("pasa_por_rivero",))
    v_act = _viaje()
    anterior = _modelo({"l1": _linea(viajes=(v_ant,))})
    actual = _modelo({"l1": _linea(viajes=(v_act,))})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "se quita la observación de viaje 'pasa_por_rivero'" in m for m in mensajes
    )


def test_temporada_rango_cambiada():
    anterior = _modelo(
        {
            "l1": _linea(
                temporadas=(Temporada(nombre="invierno", rango="01/09 - 22/06"),)
            )
        }
    )
    actual = _modelo(
        {
            "l1": _linea(
                temporadas=(Temporada(nombre="invierno", rango="01/09 - 30/06"),)
            )
        }
    )
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "la temporada 'invierno' pasa de del 1 de septiembre al 22 de junio a "
        "del 1 de septiembre al 30 de junio" in m
        for m in mensajes
    )


def test_temporada_anadida():
    anterior = _modelo(
        {"l1": _linea(temporadas=(Temporada(nombre="anual", rango="todo el año"),))}
    )
    actual = _modelo(
        {
            "l1": _linea(
                temporadas=(
                    Temporada(nombre="anual", rango="todo el año"),
                    Temporada(nombre="verano", rango="23/06 - 31/08"),
                )
            )
        }
    )
    mensajes = diff.comparar(anterior, actual)
    assert any("se añade la temporada 'verano'" in m for m in mensajes)


def test_temporada_eliminada():
    anterior = _modelo(
        {
            "l1": _linea(
                temporadas=(
                    Temporada(nombre="anual", rango="todo el año"),
                    Temporada(nombre="verano", rango="23/06 - 31/08"),
                )
            )
        }
    )
    actual = _modelo(
        {"l1": _linea(temporadas=(Temporada(nombre="anual", rango="todo el año"),))}
    )
    mensajes = diff.comparar(anterior, actual)
    assert any("se quita la temporada 'verano'" in m for m in mensajes)


def test_estado_dia_cambiado_horario_a_sin_datos():
    dias_ant = {"anual": {"lunes": "horario"}}
    dias_act = {"anual": {"lunes": "sin_datos"}}
    anterior = _modelo({"l1": _linea(dias=dias_ant)})
    actual = _modelo({"l1": _linea(dias=dias_act)})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "lunes: pasa de hay servicio a sin datos" in m for m in mensajes
    )
    # nunca se debe confundir "sin datos" con "sin servicio"
    assert not any("pasa de hay servicio a sin servicio" in m for m in mensajes)


def test_estado_dia_cambiado_sin_datos_a_sin_servicio():
    dias_ant = {"anual": {"lunes": "sin_datos"}}
    dias_act = {"anual": {"lunes": "sin_servicio"}}
    anterior = _modelo({"l1": _linea(dias=dias_ant)})
    actual = _modelo({"l1": _linea(dias=dias_act)})
    mensajes = diff.comparar(anterior, actual)
    assert any(
        "lunes: pasa de sin datos a sin servicio" in m for m in mensajes
    )


def test_linea_nueva():
    anterior = _modelo({})
    actual = _modelo({"l1": _linea(nombre="Línea Nueva")})
    mensajes = diff.comparar(anterior, actual)
    assert mensajes == ["Línea nueva: Línea Nueva."]


def test_linea_eliminada():
    anterior = _modelo({"l1": _linea(nombre="Línea Vieja")})
    actual = _modelo({})
    mensajes = diff.comparar(anterior, actual)
    assert mensajes == ["Línea eliminada: Línea Vieja."]
