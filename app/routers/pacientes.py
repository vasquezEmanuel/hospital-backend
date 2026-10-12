"""Recurso /pacientes. Carpeta: app/routers — Sprint 1.

Pantallas: 'Pacientes' (lista + filtros), 'Nuevo paciente', ficha del paciente / 'Editar información'.
Reglas: 1 (documento único). El expediente completo (/expediente) llega en Sprint 3.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.schemas.common import ErrorResponse, Page
from app.schemas.paciente import PacienteCreate, PacienteListItem, PacienteOut, PacienteUpdate, Sexo
from app.services import paciente_service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
    dependencies=[Depends(require_clinical_staff)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get("", response_model=Page[PacienteListItem], summary="Listar y buscar pacientes")
def listar_pacientes(
    q: str | None = Query(None, description="Texto libre: nombre, documento o ID visible (P-001)", max_length=100),
    documento: str | None = Query(None, description="Búsqueda exacta por documento de identidad", max_length=25),
    sexo: Sexo | None = Query(None, description="Filtro 'Género'"),
    fecha_desde: date | None = Query(None, description="Con atención desde esta fecha (filtro 'Fecha')"),
    fecha_hasta: date | None = Query(None, description="Con atención hasta esta fecha"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return paciente_service.listar(
        db,
        q=q,
        documento=documento,
        sexo=sexo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=PacienteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar paciente",
    responses={409: {"model": ErrorResponse, "description": "El documento ya está registrado"}},
)
def crear_paciente(datos: PacienteCreate, db: Session = Depends(get_db)):
    try:
        return paciente_service.crear(db, datos)
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get(
    "/{id_paciente}",
    response_model=PacienteOut,
    summary="Ficha del paciente",
    responses={404: {"model": ErrorResponse}},
)
def obtener_paciente(id_paciente: int, db: Session = Depends(get_db)):
    try:
        return paciente_service.obtener(db, id_paciente)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.patch(
    "/{id_paciente}",
    response_model=PacienteOut,
    summary="Editar información del paciente (el documento no es editable)",
    responses={404: {"model": ErrorResponse}},
)
def editar_paciente(id_paciente: int, datos: PacienteUpdate, db: Session = Depends(get_db)):
    try:
        return paciente_service.actualizar(db, id_paciente, datos)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
