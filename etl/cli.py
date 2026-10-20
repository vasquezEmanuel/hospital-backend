"""Línea de comandos del ETL. Carpeta: etl/ — Sprint 2, Fase 3 del documento técnico.

Uso (desde la raíz del repo, con el entorno virtual activo y la base de datos en marcha):
    python -m etl.cli catalogo  RUTA_DEL_CATALOGO.xlsx      # primero el catálogo CIE-10
    python -m etl.cli atenciones RUTA_DE_ATENCIONES.xlsx    # después la hoja de atenciones
La base de datos destino sale de DATABASE_URL (archivo .env).
"""

import argparse
import sys

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from etl.cargador import ResultadoCarga, cargar_atenciones, cargar_catalogo
from etl.comunes import ErrorFormato


def ejecutar(comando: str, archivo: str, db: Session) -> ResultadoCarga:
    if comando == "catalogo":
        return cargar_catalogo(db, archivo)
    if comando == "atenciones":
        return cargar_atenciones(db, archivo)
    raise ValueError(f"Comando desconocido: {comando}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.cli", description="Importador de datos del hospital.")
    parser.add_argument("comando", choices=("catalogo", "atenciones"))
    parser.add_argument("archivo", help="Ruta del archivo XLSX o CSV")
    args = parser.parse_args(argv)

    engine = get_engine()
    print(f"Base de datos destino: {engine.url.render_as_string(hide_password=True)}")
    try:
        with Session(engine) as db:
            resultado = ejecutar(args.comando, args.archivo, db)
    except (ErrorFormato, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OperationalError:
        print("ERROR: no se pudo conectar a la base de datos. ¿Está encendida y es correcta DATABASE_URL en .env?",
              file=sys.stderr)  # fmt: skip
        return 3
    print("\n".join(resultado.lineas()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())