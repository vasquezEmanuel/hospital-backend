"""Acceso a datos de auditoria. Carpeta: app/repositories — Sprint 4.

Regla 6. Solo se inserta y se consulta: la base de datos impide modificar o borrar eventos (esquema v1.4).
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Auditoria, ImagenClinica, Profesional
from app.repositories.imagen_repo import COLOMBIA

FilaAuditoria = tuple[Auditoria, str | None]  # (evento, nombre del profesional si está registrado)


def profesional_por_auth_id(db: Session, auth_sub: str) -> int | None:
    return db.scalar(select(Profesional.id_profesional).where(Profesional.auth_id == auth_sub))


def paciente_de_imagen(db: Session, id_imagen: int) -> int | None:
    return db.scalar(select(ImagenClinica.id_paciente).where(ImagenClinica.id_imagen == id_imagen))


def agregar(db: Session, eventos: list[Auditoria]) -> None:
    db.add_all(eventos)
    db.flush()


def listar(
    db: Session,
    *,
    id_paciente: int | None,
    id_profesional: int | None,
    auth_sub: str | None,
    accion: str | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
    page: int,
    page_size: int,
) -> tuple[list[FilaAuditoria], int]:
    base = select(Auditoria, Profesional.nombre).outerjoin(
        Profesional, Profesional.id_profesional == Auditoria.id_profesional
    )
    if id_paciente is not None:
        base = base.where(Auditoria.id_paciente == id_paciente)
    if id_profesional is not None:
        base = base.where(Auditoria.id_profesional == id_profesional)
    if auth_sub:
        base = base.where(Auditoria.auth_sub == auth_sub)
    if accion:
        base = base.where(Auditoria.accion == accion)
    if fecha_desde:  # hora de Colombia, igual que el resto de los filtros de fecha
        base = base.where(Auditoria.fecha_hora >= datetime.combine(fecha_desde, time.min, COLOMBIA))
    if fecha_hasta:
        base = base.where(Auditoria.fecha_hora < datetime.combine(fecha_hasta + timedelta(days=1), time.min, COLOMBIA))
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    filas = db.execute(
        base.order_by(Auditoria.fecha_hora.desc(), Auditoria.id_evento.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [tuple(f) for f in filas], total
