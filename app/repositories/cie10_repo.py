"""Acceso a datos del catálogo CIE-10. Carpeta: app/repositories."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Cie10


def buscar(
    db: Session, *, q: str | None, odontologico: bool | None, page: int, page_size: int
) -> tuple[list[Cie10], int]:
    stmt = select(Cie10)
    if q:
        q = q.strip()
        stmt = stmt.where(
            or_(
                Cie10.cod_4.istartswith(q, autoescape=True),
                Cie10.descripcion_4.icontains(q, autoescape=True),
                Cie10.descripcion_3.icontains(q, autoescape=True),
            )
        )
    if odontologico is not None:
        stmt = stmt.where(Cie10.es_odontologico.is_(odontologico))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(Cie10.cod_4).limit(page_size).offset((page - 1) * page_size)).all()
    return list(items), total


def obtener(db: Session, cod_4: str) -> Cie10 | None:
    return db.get(Cie10, cod_4.upper())
