"""Recursos /aseguradoras, /tratamientos y /profesionales. Carpeta: app/routers — Sprint 7.

Leer: odontólogo o administrador (alimentan las listas desplegables de 'Nueva atención'). Crear/editar: solo
administrador, y queda en auditoría (sin datos de pacientes). Inactivar = PATCH {"activo": false}; nunca se borra.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_admin, require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.models import Aseguradora, Tratamiento
from app.schemas.catalogos import (
    CatalogoCreate,
    CatalogoOut,
    CatalogoUpdate,
    ProfesionalAdminOut,
    ProfesionalCreate,
    ProfesionalOut,
    ProfesionalUpdate,
)
from app.schemas.common import ErrorResponse
from app.services import auditoria_service, catalogo_service
from app.services.errors import ConflictError, NotFoundError

_ERRORES = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


def _traducir(exc: Exception) -> HTTPException:
    codigo = status.HTTP_404_NOT_FOUND if isinstance(exc, NotFoundError) else status.HTTP_409_CONFLICT
    return HTTPException(codigo, str(exc))


def _catalogo(prefijo: str, etiqueta: str, modelo, singular: str) -> APIRouter:
    r = APIRouter(prefix=prefijo, tags=[etiqueta], responses=_ERRORES)

    @r.get("", response_model=list[CatalogoOut], summary=f"Listar {etiqueta.lower()}")
    def listar(
        incluir_inactivas: bool = Query(False, description="Solo administrador necesita verlas"),
        db: Session = Depends(get_db),
        _: CurrentUser = Depends(require_clinical_staff),
    ):
        return catalogo_service.listar(db, modelo, solo_activos=not incluir_inactivas)

    @r.post("", response_model=CatalogoOut, status_code=status.HTTP_201_CREATED, summary=f"Crear {singular} (admin)")
    def crear(
        datos: CatalogoCreate,
        db: Session = Depends(get_db),
        auditor: Auditor = Depends(get_auditor),
        _: CurrentUser = Depends(require_admin),
    ):
        auditor.registrar(f"crear_{singular}", singular)
        try:
            return catalogo_service.crear(db, modelo, datos)
        except ConflictError as exc:
            raise _traducir(exc) from exc

    @r.patch("/{id_}", response_model=CatalogoOut, summary=f"Editar o inactivar {singular} (admin)")
    def editar(
        id_: int,
        datos: CatalogoUpdate,
        db: Session = Depends(get_db),
        auditor: Auditor = Depends(get_auditor),
        _: CurrentUser = Depends(require_admin),
    ):
        auditor.registrar(
            f"editar_{singular}",
            singular,
            detalle={"id": id_, **auditoria_service.filtros_usados(**datos.model_dump(exclude_unset=True))},
        )
        try:
            return catalogo_service.actualizar(db, modelo, id_, datos)
        except (NotFoundError, ConflictError) as exc:
            raise _traducir(exc) from exc

    return r


aseguradoras = _catalogo("/aseguradoras", "Aseguradoras", Aseguradora, "aseguradora")
tratamientos = _catalogo("/tratamientos", "Tratamientos", Tratamiento, "tratamiento")

profesionales = APIRouter(prefix="/profesionales", tags=["Profesionales"], responses=_ERRORES)


@profesionales.get("", response_model=list[ProfesionalOut], summary="Listar profesionales")
def listar_profesionales(
    incluir_inactivos: bool = Query(False),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_clinical_staff),
):
    return catalogo_service.listar_profesionales(db, solo_activos=not incluir_inactivos)


@profesionales.get(
    "/yo",
    response_model=ProfesionalOut,
    summary="Profesional enlazado al usuario que inicia sesión",
    responses={404: {"model": ErrorResponse, "description": "El usuario no está enlazado a un profesional"}},
)
def profesional_actual(db: Session = Depends(get_db), user: CurrentUser = Depends(require_clinical_staff)):
    try:
        return catalogo_service.profesional_actual(db, user.sub)
    except NotFoundError as exc:
        raise _traducir(exc) from exc


@profesionales.post(
    "", response_model=ProfesionalAdminOut, status_code=status.HTTP_201_CREATED, summary="Crear profesional (admin)"
)
def crear_profesional(
    datos: ProfesionalCreate,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_admin),
):
    auditor.registrar("crear_profesional", "profesional")
    try:
        return catalogo_service.crear_profesional(db, datos)
    except ConflictError as exc:
        raise _traducir(exc) from exc


@profesionales.patch("/{id_profesional}", response_model=ProfesionalAdminOut, summary="Editar o inactivar (admin)")
def editar_profesional(
    id_profesional: int,
    datos: ProfesionalUpdate,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_admin),
):
    auditor.registrar(
        "editar_profesional",
        "profesional",
        detalle={"id": id_profesional, **auditoria_service.filtros_usados(**datos.model_dump(exclude_unset=True))},
    )
    try:
        return catalogo_service.actualizar_profesional(db, id_profesional, datos)
    except (NotFoundError, ConflictError) as exc:
        raise _traducir(exc) from exc
