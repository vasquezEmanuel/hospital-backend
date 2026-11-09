"""Recurso /auditoria. Carpeta: app/routers — Sprint 4 (solo rol administrador, validado con los claims del IdP).

Consulta del registro de auditoría (regla 6). Consultar la auditoría también queda registrado.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.auditoria import AuditoriaOut
from app.schemas.common import ErrorResponse, Page
from app.services import auditoria_service

router = APIRouter(
    prefix="/auditoria",
    tags=["Auditoría"],
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse, "description": "Requiere administrador"}},
)


@router.get("", response_model=Page[AuditoriaOut], summary="Registro de auditoría (solo administrador)")
def listar_auditoria(
    id_paciente: UUID | None = Query(
        None, description="Quién consultó o modificó a este paciente (identificador público)"
    ),
    id_profesional: int | None = Query(None, ge=1, description="Acciones de este profesional registrado"),
    auth_sub: str | None = Query(
        None, max_length=255, description="Acciones de este usuario del proveedor de identidad"
    ),
    accion: str | None = Query(None, max_length=100, description="p. ej. consultar_expediente, editar_paciente"),
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar(
        "consultar_auditoria",
        "auditoria",
        detalle=auditoria_service.filtros_usados(
            id_paciente=id_paciente,
            id_profesional=id_profesional,
            auth_sub=auth_sub,
            accion=accion,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        ),
    )
    return auditoria_service.listar(
        db,
        id_paciente=id_paciente,
        id_profesional=id_profesional,
        auth_sub=auth_sub,
        accion=accion,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        page=page,
        page_size=page_size,
    )
