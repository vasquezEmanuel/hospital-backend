"""Recurso /diagnosticos-bucales. Carpeta: app/routers — bajas y ediciones.

Editar o dar de baja un diagnóstico bucal de una atención ya registrada. Regla 5: la baja es lógica. Regla 6: se
audita antes de modificar. Los diagnósticos nuevos se agregan desde /atenciones/{id}/diagnosticos-bucales.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.atencion import AtencionDetalle, DiagnosticoBucalUpdate
from app.schemas.common import ErrorResponse
from app.services import diagnostico_service
from app.services.almacenamiento import Almacenamiento, get_almacenamiento
from app.services.errors import DatosInvalidosError, NotFoundError

router = APIRouter(
    prefix="/diagnosticos-bucales",
    tags=["Diagnósticos"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.patch(
    "/{id_diagnostico_bucal}",
    response_model=AtencionDetalle,
    summary="Corregir un diagnóstico bucal (texto y/o códigos CIE-10); devuelve la atención completa",
    description="`codigos` reemplaza la lista completa y deben ser odontológicos (regla 2).",
    responses={422: {"model": ErrorResponse, "description": "Código inexistente o no odontológico"}},
)
def modificar_diagnostico_bucal(
    id_diagnostico_bucal: UUID,
    datos: DiagnosticoBucalUpdate,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "editar_diagnostico_bucal",
        "diagnostico_bucal",
        id_paciente=diagnostico_service.paciente_de_bucal(db, id_diagnostico_bucal),
        detalle={"id_diagnostico_bucal": str(id_diagnostico_bucal), "campos": sorted(datos.model_fields_set)},
    )
    try:
        return diagnostico_service.modificar_bucal(db, almacen, id_diagnostico_bucal, datos)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete(
    "/{id_diagnostico_bucal}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja un diagnóstico bucal (borrado lógico: se conserva, deja de mostrarse)",
)
def inactivar_diagnostico_bucal(
    id_diagnostico_bucal: UUID,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "inactivar_diagnostico_bucal",
        "diagnostico_bucal",
        id_paciente=diagnostico_service.paciente_de_bucal(db, id_diagnostico_bucal),
        detalle={"id_diagnostico_bucal": str(id_diagnostico_bucal)},
    )
    try:
        diagnostico_service.inactivar_bucal(db, id_diagnostico_bucal)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
