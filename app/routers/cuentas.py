"""Gestión de cuentas de profesionales (pestaña 'Gestión de profesionales'). Carpeta: app/routers.

Solo administrador. Crea la cuenta en el proveedor de identidad + la fila `profesional` enlazada (rol en el IdP).
Regla 6 (trazabilidad): cada acción se audita con el id del profesional y el rol; NUNCA con contraseñas ni correos.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_admin
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.common import ErrorResponse
from app.schemas.cuentas import (
    CuentaCreate,
    CuentaExistente,
    PasswordUpdate,
    ProfesionalGestionOut,
    RolUpdate,
)
from app.services import cuenta_service
from app.services.cuenta_service import ProveedorNoDisponibleError
from app.services.errors import ConflictError, DatosInvalidosError, NotFoundError
from app.services.identidad_service import ProveedorIdentidad, get_identidad

router = APIRouter(
    prefix="/profesionales",
    tags=["Cuentas de profesionales"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        502: {"model": ErrorResponse, "description": "El proveedor de identidad no respondió"},
        503: {"model": ErrorResponse, "description": "Gestión de cuentas no configurada"},
    },
)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ProveedorNoDisponibleError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


_ERRORES = (NotFoundError, ConflictError, DatosInvalidosError, ProveedorNoDisponibleError)


@router.get("/gestion", response_model=list[ProfesionalGestionOut], summary="Lista de la pestaña de gestión")
def listar_gestion(
    db: Session = Depends(get_db),
    identidad: ProveedorIdentidad = Depends(get_identidad),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("consultar_gestion_profesionales", "profesional")
    try:
        return cuenta_service.listar(db, identidad)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.post(
    "/cuenta",
    response_model=ProfesionalGestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear profesional con su cuenta (formulario de creación)",
    responses={409: {"model": ErrorResponse, "description": "Correo o documento ya registrados"}},
)
def crear_con_cuenta(
    datos: CuentaCreate,
    db: Session = Depends(get_db),
    identidad: ProveedorIdentidad = Depends(get_identidad),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("crear_cuenta_profesional", "profesional", detalle={"rol": datos.rol})
    try:
        return cuenta_service.crear_con_cuenta(db, identidad, datos)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.post(
    "/{id_profesional}/cuenta",
    response_model=ProfesionalGestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear la cuenta de un profesional que ya existe y no tiene una",
)
def crear_cuenta_existente(
    id_profesional: int,
    datos: CuentaExistente,
    db: Session = Depends(get_db),
    identidad: ProveedorIdentidad = Depends(get_identidad),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("crear_cuenta_profesional", "profesional", detalle={"id": id_profesional, "rol": datos.rol})
    try:
        return cuenta_service.crear_cuenta_existente(db, identidad, id_profesional, datos)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.put(
    "/{id_profesional}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Definir una nueva contraseña para el profesional",
)
def cambiar_password(
    id_profesional: int,
    datos: PasswordUpdate,
    db: Session = Depends(get_db),
    identidad: ProveedorIdentidad = Depends(get_identidad),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("cambiar_password_profesional", "profesional", detalle={"id": id_profesional})
    try:
        cuenta_service.cambiar_password(db, identidad, id_profesional, datos.password)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.put(
    "/{id_profesional}/rol",
    response_model=ProfesionalGestionOut,
    summary="Cambiar el rol (odontologo | administrador)",
    responses={409: {"model": ErrorResponse, "description": "Te quitarías el rol o no quedaría ningún administrador"}},
)
def cambiar_rol(
    id_profesional: int,
    datos: RolUpdate,
    db: Session = Depends(get_db),
    identidad: ProveedorIdentidad = Depends(get_identidad),
    auditor: Auditor = Depends(get_auditor),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar("cambiar_rol_profesional", "profesional", detalle={"id": id_profesional, "rol": datos.rol})
    try:
        return cuenta_service.cambiar_rol(db, identidad, id_profesional, datos.rol, auth_sub=user.sub)
    except _ERRORES as exc:
        raise _http(exc) from exc
