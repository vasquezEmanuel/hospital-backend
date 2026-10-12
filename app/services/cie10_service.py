"""Consulta del catálogo CIE-10. Carpeta: app/services. La carga del catálogo es del ETL (Sprint 2)."""

from sqlalchemy.orm import Session

from app.repositories import cie10_repo
from app.schemas.cie10 import Cie10Out
from app.schemas.common import Page
from app.services.errors import NotFoundError


def buscar(db: Session, *, q: str | None, odontologico: bool | None, page: int, page_size: int) -> Page[Cie10Out]:
    items, total = cie10_repo.buscar(db, q=q, odontologico=odontologico, page=page, page_size=page_size)
    return Page(items=[Cie10Out.model_validate(i) for i in items], total=total, page=page, page_size=page_size)


def obtener(db: Session, cod_4: str) -> Cie10Out:
    fila = cie10_repo.obtener(db, cod_4)
    if fila is None:
        raise NotFoundError("Código CIE-10 no encontrado")
    return Cie10Out.model_validate(fila)
