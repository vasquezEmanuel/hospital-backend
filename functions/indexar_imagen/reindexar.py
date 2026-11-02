"""Indexar archivos que YA estaban en el almacenamiento (p. ej. las carpetas históricas).
Carpeta: functions/indexar_imagen.

Los eventos solo avisan de archivos nuevos. Para los que ya existían se genera una lista de claves (una por línea; por
ejemplo con la herramienta de listado del proveedor) y se procesa con la misma lógica y la misma idempotencia:
    python -m functions.indexar_imagen.reindexar claves.txt
Imprime un resumen y termina con código 1 si algún archivo no pudo asociarse a un paciente (la lista de pendientes
queda en pantalla para revisarla con el hospital; repetir la ejecución no duplica nada).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import get_engine
from functions.indexar_imagen.nucleo import indexar_claves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m functions.indexar_imagen.reindexar")
    parser.add_argument("archivo", help="Archivo de texto con una clave del almacenamiento por línea")
    args = parser.parse_args(argv)
    try:
        claves = [(linea.strip(), None) for linea in Path(args.archivo).read_text(encoding="utf-8").splitlines()]
    except FileNotFoundError:
        print(f"ERROR: no existe el archivo {args.archivo}", file=sys.stderr)
        return 2
    with Session(get_engine(), expire_on_commit=False) as db:
        resultados = indexar_claves(db, [c for c in claves if c[0]])
    for estado, n in sorted(Counter(r.estado for r in resultados).items()):
        print(f"{estado:<14}{n}")
    pendientes = [r for r in resultados if r.estado in ("sin_paciente", "error")]
    for r in pendientes:
        print(f"PENDIENTE {r.clave}: {r.detalle}")
    return 1 if pendientes else 0


if __name__ == "__main__":
    raise SystemExit(main())
