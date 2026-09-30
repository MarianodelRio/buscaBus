"""tools/migracion/cuadre_excel.py — cuadre de horas entre el Excel y horarios/.

De un solo uso: se borra en la fase 1b (design.md, 5.4). Compara, para cada
hoja migrada, el multiconjunto de "horas públicas" del Excel (celdas de filas
visibles cuyo valor completo es una hora, con asterisco(s) opcional, fuera de
las columnas RUTA y VALIDADORA) con el multiconjunto de horas de la tabla YAML
de la línea y temporada correspondientes.

Hojas de la fase 1b-1: FTE CARRET, VILLAVIC INV/VER, BELAL - POZ INV/VER y
TORR INV/VER (esta ultima suma 4 ficheros de linea). Caso especial: la celda
"VIERNES ESCOLAR 16:00" (VILLAVIC INV) cuenta como hora; es un patron
explicito, no una busqueda generica de horas dentro de texto.

Única discrepancia aceptada: hoja POZOB VER, fila 48, 17:50 (x1) y 19:05 (x1).
Negocio indica (P09b) que ese viaje no está en vigor en verano; se borró del
YAML y el Excel modificado conserva la fila. El cuadre sale con código 1.

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
EXCEL_PATH = RAIZ / "horarios_fuente" / "HORARIOS NUEVOS MODIFICADO.xlsx"
HORARIOS_DIR = RAIZ / "horarios"

_HORA_EXCEL_RE = re.compile(r"^\d{1,2}:\d{2}\*{0,2}$")
_VIERNES_ESCOLAR_RE = re.compile(r"^VIERNES ESCOLAR\s+(\d{1,2}:\d{2})\*{0,2}$")

# hoja -> lista de (fichero de línea, temporadas a incluir; None = todas)
_TORR = ["torrecampo-pozoblanco", "santa-eufemia-villaralto-pozoblanco",
         "cardena-pozoblanco", "pozoblanco-estacion-ave"]
HOJAS = {
    "OCHAVILLOS": [("ochavillos-cordoba", None)],
    "POZOB INV": [("pozoblanco-cordoba", {"invierno"})],
    "POZOB VER": [("pozoblanco-cordoba", {"verano"})],
    "BELAL- COR": [("belalcazar-cordoba", None)],
    "ADAMUZ INV": [("adamuz-cordoba", {"invierno"})],
    "ADAMUZ VER": [("adamuz-cordoba", {"verano"})],
    "BADAJOZ ": [("badajoz-cordoba", None)],
    "FTE CARRET": [("fuente-carreteros-cordoba", None)],
    "VILLAVIC INV": [("villaviciosa-cordoba", {"invierno"})],
    "VILLAVIC VER": [("villaviciosa-cordoba", {"verano"})],
    "BELAL - POZ INV": [("belalcazar-pozoblanco", {"invierno"})],
    "BELAL - POZ VER": [("belalcazar-pozoblanco", {"verano"})],
    "TORR INV": [(f, {"invierno"}) for f in _TORR],
    "TORR VER": [(f, {"verano"}) for f in _TORR],
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
            elif isinstance(valor, str):
                m = _VIERNES_ESCOLAR_RE.match(valor.strip())
                if m:
                    contador[_normalizar(m.group(1))] += 1
    return contador


def horas_yaml(ficheros: list[tuple[str, set[str] | None]]) -> Counter[str]:
    total: Counter[str] = Counter()
    for fichero_linea, temporadas in ficheros:
        total += _horas_fichero(fichero_linea, temporadas)
    return total


def _horas_fichero(fichero_linea: str, temporadas: set[str] | None) -> Counter[str]:
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
    for hoja, ficheros in HOJAS.items():
        excel = horas_excel(hoja)
        yaml_ = horas_yaml(ficheros)
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
