"""tests/test_query.py — motor de consulta (design.md, sección 3).

Pruebas doradas contra `horarios/` real (verificadas a mano contra
horarios/lineas/*.yaml) más pruebas sobre la mezcla sintética
tests/fixtures/horarios_motor/ para los casos especiales (a demanda, viernes
lectivo, no_circula, sin_datos, fusión)."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.horarios import loader, query

REPO_ROOT = Path(__file__).parent.parent
HORARIOS_REAL = REPO_ROOT / "horarios"
FIXTURES = Path(__file__).parent / "fixtures"

HORARIOS = loader.cargar(HORARIOS_REAL)
MOTOR = loader.cargar(FIXTURES / "horarios_motor")

MADRID = ZoneInfo("Europe/Madrid")


def _horas(consulta: query.Consulta) -> list[tuple[str, str]]:
    return [
        (s.hora_salida.strftime("%H:%M"), s.hora_llegada.strftime("%H:%M"))
        for s in consulta.salidas
    ]


# ── Doradas: Pozoblanco <-> Córdoba ──────────────────────────────────────────


def test_pozoblanco_cordoba_miercoles_laborable():
    c = query.consultar(HORARIOS, "pozoblanco", "cordoba", date(2026, 9, 30))
    assert c.estado == "con_salidas"
    assert _horas(c) == [
        ("06:55", "08:15"),
        ("08:15", "09:30"),
        ("10:00", "11:25"),
        ("15:15", "16:30"),
        ("18:00", "19:15"),
    ]
    assert all(
        s.parada_origen == "POZ" and s.parada_destino == "COR" for s in c.salidas
    )


def test_pozoblanco_cordoba_festivo_lunes():
    c = query.consultar(HORARIOS, "pozoblanco", "cordoba", date(2026, 10, 12))
    assert c.estado == "con_salidas"
    assert c.info_dia.es_festivo is True
    assert _horas(c) == [("08:15", "09:30"), ("15:15", "16:30"), ("17:45", "19:00")]


def test_pozoblanco_cordoba_festivo_en_sabado():
    c = query.consultar(HORARIOS, "pozoblanco", "cordoba", date(2027, 5, 1))
    assert c.estado == "con_salidas"
    assert c.info_dia.es_festivo is True
    # mismas 3 salidas que el festivo anterior, no el conjunto de sábado.
    assert _horas(c) == [("08:15", "09:30"), ("15:15", "16:30"), ("17:45", "19:00")]


def test_pozoblanco_cordoba_ya_salio():
    ahora = datetime(2026, 9, 30, 10, 30, tzinfo=MADRID)
    c = query.consultar(
        HORARIOS, "pozoblanco", "cordoba", date(2026, 9, 30), ahora=ahora
    )
    ya_salio = [s.ya_salio for s in c.salidas]
    assert ya_salio == [True, True, True, False, False]


def test_cordoba_villaharta_a_demanda():
    c = query.consultar(HORARIOS, "cordoba", "villaharta", date(2026, 9, 30))
    assert _horas(c) == [("13:10", "13:45"), ("18:30", "19:05"), ("20:00", "20:35")]
    for s in c.salidas:
        assert any("957 42 90 30" in n for n in s.notas)


def test_cordoba_villanueva_de_cordoba_solo_una_con_viajeros_desde_cordoba():
    c = query.consultar(
        HORARIOS, "cordoba", "villanueva-de-cordoba", date(2026, 9, 30)
    )
    assert _horas(c) == [
        ("12:00", "13:35"),
        ("13:10", "15:10"),
        ("18:30", "20:10"),
        ("20:00", "21:45"),
    ]
    con_nota = [s for s in c.salidas if s.notas]
    assert len(con_nota) == 1
    assert con_nota[0].hora_salida == time(20, 0)
    assert any("viajeros" in n for n in con_nota[0].notas)


def test_ochavillos_cordoba_sabado_sin_servicio():
    c = query.consultar(HORARIOS, "ochavillos", "cordoba", date(2026, 10, 3))
    assert c.estado == "sin_servicio"
    assert c.siguiente_con_servicio == date(2026, 10, 5)


def test_ochavillos_cordoba_festivo_lunes_sin_servicio():
    c = query.consultar(HORARIOS, "ochavillos", "cordoba", date(2026, 10, 12))
    assert c.estado == "sin_servicio"
    assert c.siguiente_con_servicio == date(2026, 10, 13)


def test_ochavillos_pozoblanco_sin_trayecto():
    c = query.consultar(HORARIOS, "ochavillos", "pozoblanco", date(2026, 9, 30))
    assert c.estado == "sin_trayecto"
    assert c.siguiente_con_servicio is None


def test_pozoblanco_cordoba_fuera_de_calendario():
    c = query.consultar(HORARIOS, "pozoblanco", "cordoba", date(2028, 1, 1))
    assert c.estado == "sin_datos"
    assert c.fuera_de_calendario is True
    assert c.salidas == ()


def test_origen_igual_destino_lanza_valueerror():
    with pytest.raises(ValueError):
        query.consultar(HORARIOS, "cordoba", "cordoba", date(2026, 9, 30))


def test_localidad_desconocida_lanza_valueerror():
    with pytest.raises(ValueError):
        query.consultar(HORARIOS, "cordoba", "no-existe", date(2026, 9, 30))


def test_destinos_desde_ochavillos():
    destinos = query.destinos_desde(HORARIOS, "ochavillos")
    assert destinos == frozenset(
        {"la-herreria", "fuente-palmera", "la-ventilla", "fuencubierta", "cordoba"}
    )
    assert "ochavillos" not in destinos


# ── Sintéticas: tests/fixtures/horarios_motor/ ───────────────────────────────


def test_viernes_lectivo_parada_no_lectivo_falla_pero_intermedia_sin_condicion_pasa():
    # 28/08/2026 es viernes pero anterior a inicio_clases: no es lectivo.
    fecha = date(2026, 8, 28)
    c_b = query.consultar(MOTOR, "pueblo-a", "pueblo-b", fecha)
    assert c_b.estado == "con_salidas"
    assert any(s.hora_salida == time(8, 0) for s in c_b.salidas)

    c_c = query.consultar(MOTOR, "pueblo-a", "pueblo-c", fecha)
    # la salida de las 08:00 (condición V solo en C) no debe aparecer; la de
    # las 09:00 (condición de viaje) tampoco.
    assert c_c.estado == "sin_servicio"


def test_viernes_lectivo_si_es_lectivo_aparecen_ambas():
    # 04/09/2026 es viernes, dentro de curso: es lectivo.
    fecha = date(2026, 9, 4)
    c_c = query.consultar(MOTOR, "pueblo-a", "pueblo-c", fecha)
    assert c_c.estado == "con_salidas"
    assert _horas(c_c) == [("08:00", "08:20"), ("09:00", "09:20")]
    salida_v = next(s for s in c_c.salidas if s.hora_salida == time(8, 0))
    assert any("viernes" in n.lower() for n in salida_v.notas)


def test_no_circula_en_agosto():
    c_agosto = query.consultar(MOTOR, "pueblo-n", "pueblo-o", date(2026, 8, 5))
    assert c_agosto.estado == "sin_servicio"

    c_septiembre = query.consultar(MOTOR, "pueblo-n", "pueblo-o", date(2026, 9, 2))
    assert c_septiembre.estado == "con_salidas"


def test_sin_servicio_en_7_dias_da_siguiente_con_servicio_none():
    c = query.consultar(MOTOR, "pueblo-p", "pueblo-q", date(2026, 8, 28))
    assert c.estado == "sin_servicio"
    assert c.siguiente_con_servicio is None


def test_sin_datos_combinado_con_horario_muestra_salidas_y_aviso():
    c = query.consultar(MOTOR, "pueblo-e", "pueblo-f", date(2026, 9, 2))
    assert c.estado == "con_salidas"
    assert _horas(c) == [("09:00", "09:15")]
    assert "linea-sin-datos" in c.lineas_sin_datos


def test_sin_datos_solo_es_sin_datos_nunca_sin_servicio():
    c = query.consultar(MOTOR, "pueblo-g", "pueblo-h", date(2026, 9, 2))
    assert c.estado == "sin_datos"
    assert c.salidas == ()


def test_fusion_de_lineas_con_mismo_autobus():
    c = query.consultar(MOTOR, "pueblo-i", "pueblo-j", date(2026, 9, 2))
    assert len(c.salidas) == 1
    salida = c.salidas[0]
    assert set(salida.lineas) == {"linea-fusion-1", "linea-fusion-2"}
    assert "Aviso uno." in salida.notas
    assert "Aviso dos." in salida.notas


def test_a_demanda_en_origen_lleva_nota():
    c = query.consultar(MOTOR, "pueblo-k", "pueblo-l", date(2026, 9, 2))
    salida_demanda = next(s for s in c.salidas if s.hora_salida == time(10, 0))
    assert any("957 00 00 00" in n for n in salida_demanda.notas)


def test_a_demanda_en_parada_intermedia_no_lleva_nota():
    c = query.consultar(MOTOR, "pueblo-k", "pueblo-l", date(2026, 9, 2))
    salida_normal = next(s for s in c.salidas if s.hora_salida == time(11, 0))
    assert salida_normal.notas == ()
