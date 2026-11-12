"""Acceso a datos de importacion e importacion_fila. Carpeta: app/repositories — Sprint 8.

La escritura de estas tablas la hace el ETL (etl/cargador.py); aquí solo se consulta y se marca una fila como resuelta.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def catalogo_vacio(db: Session) -> bool:
    return db.execute(text("SELECT NOT EXISTS (SELECT 1 FROM cie10)")).scalar_one()


def listar(db: Session, *, page: int, page_size: int) -> tuple[list[dict], int]:
    total = db.execute(text("SELECT count(*) FROM importacion")).scalar_one()
    filas = db.execute(
        text(
            "SELECT i.id_importacion, i.tipo, i.nombre_archivo, i.estado, i.total_registros, i.insertados, "
            "i.actualizados, i.rechazados, i.creado_en, i.finalizado_en, p.nombre AS profesional "
            "FROM importacion i LEFT JOIN profesional p ON p.id_profesional = i.id_profesional "
            "ORDER BY i.id_importacion DESC LIMIT :l OFFSET :o"
        ),
        {"l": page_size, "o": (page - 1) * page_size},
    ).mappings()
    return [dict(f) for f in filas], total


def obtener(db: Session, id_importacion: int) -> dict | None:
    fila = (
        db.execute(
            text(
                "SELECT i.id_importacion, i.tipo, i.nombre_archivo, i.estado, i.total_registros, i.insertados, "
                "i.actualizados, i.rechazados, i.creado_en, i.finalizado_en, p.nombre AS profesional "
                "FROM importacion i LEFT JOIN profesional p ON p.id_profesional = i.id_profesional "
                "WHERE i.id_importacion = :i"
            ),
            {"i": id_importacion},
        )
        .mappings()
        .first()
    )
    return dict(fila) if fila else None


def filas(db: Session, id_importacion: int, estado: str | None, *, page: int, page_size: int) -> tuple[list[dict], int]:
    cond, params = "id_importacion = :i", {"i": id_importacion}
    if estado:
        cond += " AND estado = :e"
        params["e"] = estado
    total = db.execute(text(f"SELECT count(*) FROM importacion_fila WHERE {cond}"), params).scalar_one()  # noqa: S608
    datos = db.execute(
        text(
            "SELECT id_fila, numero_fila, estado, motivo, datos, resuelto_en FROM importacion_fila "  # noqa: S608
            f"WHERE {cond} ORDER BY numero_fila LIMIT :l OFFSET :o"
        ),
        {**params, "l": page_size, "o": (page - 1) * page_size},
    ).mappings()
    return [dict(f) for f in datos], total


def resolver_fila(db: Session, id_importacion: int, id_fila: int, id_profesional: int | None) -> dict | None:
    fila = (
        db.execute(
            text(
                "UPDATE importacion_fila SET estado = 'resuelta', resuelto_por = :p, resuelto_en = now() "
                "WHERE id_fila = :f AND id_importacion = :i "
                "RETURNING id_fila, numero_fila, estado, motivo, datos, resuelto_en"
            ),
            {"p": id_profesional, "f": id_fila, "i": id_importacion},
        )
        .mappings()
        .first()
    )
    return dict(fila) if fila else None
