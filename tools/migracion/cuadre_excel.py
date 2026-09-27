"""tools/migracion/cuadre_excel.py — cuadre de horas entre el Excel y horarios/.

De un solo uso: se borra en la fase 1b (design.md, 5.4). Compara, para cada
hoja migrada, el multiconjunto de "horas públicas" del Excel (celdas de filas
visibles cuyo valor completo es una hora, con asterisco(s) opcional, fuera de
las columnas RUTA y VALIDADORA) con el multiconjunto de horas de la tabla YAML
de la línea y temporada correspondientes.

Uso: python -m tools.migracion.cuadre_excel
"""

from __future__ import annotations

import datetime
import re
import sys
from collections import Counter
from pathlib import Path

import openpyxl
import yaml

from app.services.horarios.formato import _parse_tabla

RAIZ = Path(__file__).resolve().parent.parent.parent
EXCEL_PATH = RAIZ / "horarios_fuente" / "HORARIOS NUEVOS.xlsx"
HORARIOS_DIR = RAIZ / "horarios"

_HORA_EXCEL_RE = re.compile(r"^\d{1,2}:\d{2}\*{0,2}$")

# hoja -> (fichero de línea, temporadas a incluir; None = todas)
HOJAS = {
    "OCHAVILLOS": ("ochavillos-cordoba", None),
    "POZOB INV": ("pozoblanco-cordoba", {"invierno"}),
    "POZOB VER": ("pozoblanco-cordoba", {"verano"}),
    "BELAL- COR": ("belalcazar-cordoba", None),
    "ADAMUZ INV": ("adamuz-cordoba", {"invierno"}),
    "ADAMUZ VER": ("adamuz-cordoba", {"verano"}),
    "BADAJOZ ": ("badajoz-cordoba", None),
}


def _normalizar(hhmm: str) -> str:
    hhmm = hhmm.rstrip("*").rstrip("A-Za-z").strip()
    hhmm = re.sub(r"[A-Za-z]+$", "", hhmm)
    h, m = hhmm.split(":")
    return f"{int(h):02d}:{m}"


def horas_excel(nombre_hoja: str) -> Counter[str]:
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb[nombre_hoja]
    contador: Counter[str] = Counter()
    for row in ws.iter_rows():
        dim = ws.row_dimensions.get(row[0].row)
        if dim is not None and dim.hidden:
            continue
        for cell in row:
            valor = cell.value
            if isinstance(valor, datetime.time):
                contador[f"{valor.hour:02d}:{valor.minute:02d}"] += 1
            elif isinstance(valor, str) and _HORA_EXCEL_RE.match(valor.strip()):
                contador[_normalizar(valor.strip())] += 1
    return contador


def horas_yaml(fichero_linea: str, temporadas: set[str] | None) -> Counter[str]:
    path = HORARIOS_DIR / "lineas" / f"{fichero_linea}.yaml"
    datos = yaml.safe_load(path.read_text(encoding="utf-8"))
    contador: Counter[str] = Counter()
    for entrada in datos.get("horarios", []):
        if temporadas is not None and entrada.get("temporada") not in temporadas:
            continue
        _cabecera, filas = _parse_tabla(entrada["tabla"])
        for fila in filas:
            for valor in fila.valores:
                if valor == "-":
                    continue
                contador[_normalizar(valor)] += 1
    return contador


def main() -> int:
    todo_ok = True
    for hoja, (fichero_linea, temporadas) in HOJAS.items():
        excel = horas_excel(hoja)
        yaml_ = horas_yaml(fichero_linea, temporadas)
        if excel == yaml_:
            print(f"{hoja}: 100% cuadre ({sum(excel.values())} horas)")
            continue
        todo_ok = False
        print(f"{hoja}: DISCREPANCIAS")
        solo_excel = excel - yaml_
        solo_yaml = yaml_ - excel
        for hora, n in sorted(solo_excel.items()):
            print(f"  en el Excel mas veces: {hora} (x{n})")
        for hora, n in sorted(solo_yaml.items()):
            print(f"  en horarios/ mas veces: {hora} (x{n})")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
