"""tests/test_loader.py — cargar() nunca devuelve datos parciales: o carga
horarios/ real con índices precalculados, o lanza HorariosInvalidos con la
lista completa de errores (design.md, 2.4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.horarios import formato, loader

REPO_ROOT = Path(__file__).parent.parent
HORARIOS_REAL = REPO_ROOT / "horarios"
FIXTURES = Path(__file__).parent / "fixtures"


def test_cargar_horarios_real():
    horarios = loader.cargar(HORARIOS_REAL)
    assert horarios.modelo is not None
    assert horarios.modelo.calendario is not None
    # Pozoblanco tiene dos paradas físicas (pueblo/hospital, P10).
    assert set(horarios.localidad_paradas["pozoblanco"]) == {"POZ", "PZH"}
    # Todo viaje que pare en alguna parada de Pozoblanco debe estar indexado.
    for viaje in horarios.localidad_viajes["pozoblanco"]:
        codigos_localidad = set(horarios.localidad_paradas["pozoblanco"])
        assert any(p.parada in codigos_localidad for p in viaje.pasos)


def test_cargar_directorio_invalido_lanza_horarios_invalidos(tmp_path):
    horarios_dir = tmp_path / "horarios"
    (horarios_dir / "lineas").mkdir(parents=True)
    (horarios_dir / "paradas.yaml").write_text(
        (FIXTURES / "paradas_base.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (horarios_dir / "observaciones.yaml").write_text(
        (FIXTURES / "observaciones_base.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # calendario.yaml ausente a propósito: horarios/ no valida.
    with pytest.raises(loader.HorariosInvalidos) as exc_info:
        loader.cargar(horarios_dir)
    assert any("calendario.yaml" in e for e in exc_info.value.errores)


def test_cargar_motor_fixture():
    horarios = loader.cargar(FIXTURES / "horarios_motor")
    assert "linea-viernes" in horarios.modelo.lineas
    assert set(horarios.localidad_paradas["pueblo-a"]) == {"AAA"}


def test_festivos_por_linea_real_las_7_lineas_que_tocan_cordoba():
    horarios = loader.cargar(HORARIOS_REAL)
    esperado = {
        date(2026, 9, 8): ("Virgen de la Fuensanta", "cordoba"),
        date(2026, 10, 24): ("San Rafael", "cordoba"),
    }
    sin_cordoba = {
        "belalcazar-pozoblanco",
        "torrecampo-pozoblanco",
        "santa-eufemia-villaralto-pozoblanco",
        "cardena-pozoblanco",
        "pozoblanco-estacion-ave",
    }
    assert set(horarios.modelo.lineas) >= sin_cordoba
    assert set(horarios.festivos_por_linea) == set(horarios.modelo.lineas) - sin_cordoba
    assert len(horarios.festivos_por_linea) == 7
    assert {"fuente-carreteros-cordoba", "villaviciosa-cordoba"} <= set(
        horarios.festivos_por_linea
    )
    for lid, festivos in horarios.festivos_por_linea.items():
        assert festivos == esperado, lid


def test_festivos_por_linea_solo_las_lineas_que_tocan_la_localidad():
    horarios = loader.cargar(FIXTURES / "horarios_festivo_local")
    assert set(horarios.festivos_por_linea) == {"linea-con-a", "linea-viernes-a"}
    assert horarios.festivos_por_linea["linea-con-a"][date(2026, 10, 14)] == (
        "Fiesta local de A",
        "pueblo-a",
    )


def test_festivos_locales_localidad_sin_lineas_avisa_sin_fallar():
    resultado = formato.validar(HORARIOS_REAL)
    assert resultado.errores == []
    assert not any("festivos_locales" in a for a in resultado.avisos)
