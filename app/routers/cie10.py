"""Recurso /cie10 (catálogo). Carpeta: app/routers — Sprint 1.

Pantalla 'Diagnósticos' (búsqueda por enfermedad o código). La relación código→pacientes
(/enfermedades/{cod_4}/pacientes) es Sprint 4.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.schemas.cie10 import Cie10Out
from app.schemas.common import ErrorResponse, Page
from app.services import cie10_service
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/cie10",
    tags=["Catálogo CIE-10"],
    dependencies=[Depends(require_clinical_staff)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get("", response_model=Page[Cie10Out], summary="Buscar en el catálogo CIE-10")
def buscar_cie10(
    q: str | None = Query(None, description="Prefijo de código o texto de la descripción", max_length=100),
    odontologico: bool | None = Query(None, description="true = solo códigos del área odontológica"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return cie10_service.buscar(db, q=q, odontologico=odontologico, page=page, page_size=page_size)


@router.get(
    "/{cod_4}", response_model=Cie10Out, summary="Detalle de un código", responses={404: {"model": ErrorResponse}}
)
def obtener_cie10(cod_4: str, db: Session = Depends(get_db)):
    try:
        return cie10_service.obtener(db, cod_4)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
