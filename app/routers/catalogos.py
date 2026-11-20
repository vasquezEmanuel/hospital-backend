"""Recursos /aseguradoras, /tratamientos y /profesionales. Carpeta: app/routers — Sprint 7.

Leer: odontólogo o administrador (alimentan las listas desplegables de 'Nueva atención'). Crear/editar: solo
administrador, y queda en auditoría (sin datos de pacientes). Inactivar = PATCH {"activo": false}; nunca se borra.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    ProfesionalOut,
    ProfesionalUpdate,
)
from app.schemas.common import ErrorResponse
from app.schemas.cuentas import ProfesionalCrear, ProfesionalGestionOut
from app.services import auditoria_service, catalogo_service, cuenta_service
from app.services.cuenta_service import ProveedorNoDisponibleError
from app.services.errors import ConflictError, DatosInvalidosError, NotFoundError
from app.services.identidad_service import ProveedorIdentidad, get_identidad_opcional

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

    @r.delete(
        "/{id_}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Dar de baja {singular} (admin): se inactiva, no se borra",
        responses={404: {"model": ErrorResponse}},
    )
    def dar_de_baja(
        id_: int,
        db: Session = Depends(get_db),
        auditor: Auditor = Depends(get_auditor),
        _: CurrentUser = Depends(require_admin),
    ):
        auditor.registrar(f"baja_{singular}", singular, detalle={"id": id_})
        try:
            catalogo_service.actualizar(db, modelo, id_, CatalogoUpdate(activo=False))
        except NotFoundError as exc:
            raise _traducir(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return r


aseguradoras = _catalogo("/aseguradoras", "Aseguradoras", Aseguradora, "aseguradora")
tratamientos = _catalogo("/tratamientos", "Tratamientos", Tratamiento, "tratamiento")

profesionales = APIRouter(prefix="/profesionales", tags=["Profesionales"], responses=_ERRORES)


@profesionales.get(
    "",
    response_model=list[ProfesionalOut],
    summary="Lista corta para desplegables (nombre y especialidad; cualquier personal clínico)",
)
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
    "",
    response_model=ProfesionalGestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear profesional, con o sin cuenta de acceso (admin)",
    description=(
        "Con `password` se crea también la cuenta de acceso en el proveedor de identidad, con el `rol` indicado "
        "(odontologo por defecto). Sin `password` solo se crea la ficha. `auth_id` enlaza una cuenta que ya existe."
    ),
    responses={
        409: {"model": ErrorResponse, "description": "Correo o documento ya registrados"},
        502: {"model": ErrorResponse, "description": "El proveedor de identidad no respondió"},
        503: {"model": ErrorResponse, "description": "Gestión de cuentas no configurada"},
    },
)
def crear_profesional(
    datos: ProfesionalCrear,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    identidad: ProveedorIdentidad | None = Depends(get_identidad_opcional),
    _: CurrentUser = Depends(require_admin),
):
    if datos.password:
        if identidad is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "La gestión de cuentas no está configurada (falta SUPABASE_SERVICE_ROLE_KEY)",
            )
        auditor.registrar("crear_cuenta_profesional", "profesional", detalle={"rol": datos.rol})
    else:
        identidad = None
        auditor.registrar("crear_profesional", "profesional")
    try:
        if identidad is not None:
            return cuenta_service.crear_con_cuenta(db, identidad, datos)
        return cuenta_service.crear_solo_ficha(db, datos)
    except (ConflictError, DatosInvalidosError, ProveedorNoDisponibleError) as exc:
        if isinstance(exc, ProveedorNoDisponibleError):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        if isinstance(exc, DatosInvalidosError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        raise _traducir(exc) from exc


@profesionales.patch("/{id_profesional}", response_model=ProfesionalAdminOut, summary="Editar o inactivar (admin)")
def editar_profesional(
    id_profesional: int,
    datos: ProfesionalUpdate,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    identidad: ProveedorIdentidad | None = Depends(get_identidad_opcional),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar(
        "editar_profesional",
        "profesional",
        detalle={"id": id_profesional, **auditoria_service.filtros_usados(**datos.model_dump(exclude_unset=True))},
    )
    try:
        return cuenta_service.actualizar_profesional(db, identidad, id_profesional, datos, auth_sub=user.sub)
    except (NotFoundError, ConflictError) as exc:
        raise _traducir(exc) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ProveedorNoDisponibleError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@profesionales.delete(
    "/{id_profesional}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja un profesional (admin): se inactiva y se bloquea su cuenta; la ficha se conserva",
    description=(
        "Baja lógica: el profesional tiene atenciones a su nombre, por eso la ficha nunca se borra. Se bloquea el "
        'acceso de inmediato. Para reactivarlo: `PATCH /profesionales/{id}` con `{"activo": true}`. Un administrador '
        "no puede darse de baja a sí mismo ni dejar el sistema sin administrador activo."
    ),
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def dar_de_baja_profesional(
    id_profesional: int,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    identidad: ProveedorIdentidad | None = Depends(get_identidad_opcional),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar("baja_profesional", "profesional", detalle={"id": id_profesional})
    try:
        cuenta_service.actualizar_profesional(
            db, identidad, id_profesional, ProfesionalUpdate(activo=False), auth_sub=user.sub
        )
    except (NotFoundError, ConflictError) as exc:
        raise _traducir(exc) from exc
    except ProveedorNoDisponibleError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
