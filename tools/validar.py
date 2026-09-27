"""tools/validar.py — make validar.

Valida `horarios/` con app/services/horarios/formato.py e imprime errores y
avisos agrupados. Sale con código 1 si hay errores, 0 en caso contrario.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.services.horarios.formato import validar

HORARIOS_DIR = Path(__file__).resolve().parent.parent / "horarios"


def main() -> int:
    resultado = validar(HORARIOS_DIR)

    if resultado.errores:
        print(f"ERRORES ({len(resultado.errores)}):")
        for error in resultado.errores:
            print(f"  ✗ {error}")
    else:
        print("Sin errores.")

    if resultado.avisos:
        print(f"\nAVISOS ({len(resultado.avisos)}):")
        for aviso in resultado.avisos:
            print(f"  ⚠ {aviso}")

    return 1 if resultado.errores else 0


if __name__ == "__main__":
    sys.exit(main())
