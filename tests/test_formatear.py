"""tests/test_formatear.py — formatear.py es idempotente y no cambia datos."""

from __future__ import annotations

from pathlib import Path

from app.services.horarios import formato
from tools.formatear import formatear_texto

REPO_ROOT = Path(__file__).parent.parent
LINEAS_DIR = REPO_ROOT / "horarios" / "lineas"


def _parse_lineas_dir(lineas_dir: Path) -> dict:
    """Extrae, por fichero, la lista de filas (tuplas de valores) de todas
    las tablas, para comparar el modelo de datos antes/después de formatear."""
    resultado = {}
    for path in sorted(lineas_dir.glob("*.yaml")):
        import yaml

        datos = yaml.safe_load(path.read_text(encoding="utf-8"))
        filas_totales = []
        for entrada in datos.get("horarios", []):
            _cabecera, filas = formato._parse_tabla(entrada["tabla"])
            for fila in filas:
                filas_totales.append(tuple(fila.valores))
        resultado[path.name] = filas_totales
    return resultado


def test_formatear_es_idempotente(tmp_path):
    destino = tmp_path / "lineas"
    destino.mkdir()
    for path in LINEAS_DIR.glob("*.yaml"):
        (destino / path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    primeras = {}
    for path in sorted(destino.glob("*.yaml")):
        original = path.read_text(encoding="utf-8")
        formateado_1 = formatear_texto(original)
        formateado_2 = formatear_texto(formateado_1)
        assert formateado_1 == formateado_2, f"{path.name}: no es idempotente"
        primeras[path.name] = formateado_1


def test_formatear_no_cambia_los_datos(tmp_path):
    destino = tmp_path / "lineas"
    destino.mkdir()
    for path in LINEAS_DIR.glob("*.yaml"):
        (destino / path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    antes = _parse_lineas_dir(destino)

    for path in destino.glob("*.yaml"):
        original = path.read_text(encoding="utf-8")
        path.write_text(formatear_texto(original), encoding="utf-8")

    despues = _parse_lineas_dir(destino)
    assert antes == despues
