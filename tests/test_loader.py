"""tests/test_loader.py — cargar() nunca devuelve datos parciales: o carga
horarios/ real con índices precalculados, o lanza HorariosInvalidos con la
lista completa de errores (design.md, 2.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.horarios import loader

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
