"""Expediente del paciente: GET /pacientes/{id}/expediente. Carpeta: app/routers — Sprint 3.

Pantalla de detalle del paciente / 'Detalle de atención' ('Ver imágenes'). Búsqueda por paciente -> enfermedades e
imágenes. Auditoría de la consulta (regla 6): Sprint 4.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.expediente import ExpedienteOut
from app.services import expediente_service
from app.services.almacenamiento import Almacenamiento, get_almacenamiento
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
    dependencies=[Depends(require_clinical_staff)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get(
    "/{id_paciente}/expediente",
    response_model=ExpedienteOut,
    summary="Expediente: atenciones, diagnósticos (CIE-10) e imágenes del paciente",
    responses={404: {"model": ErrorResponse}},
)
def obtener_expediente(
    id_paciente: int,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
):
    try:
        return expediente_service.obtener(db, almacen, id_paciente)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
