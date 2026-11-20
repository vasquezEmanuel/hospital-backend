"""Cuentas de profesionales: alta, baja lógica, contraseña y rol. Carpeta: app/services.

Una sola acción del administrador crea la cuenta en el proveedor de identidad (con su rol) y la fila `profesional`
enlazada por `auth_id`. Los roles NO se guardan en nuestra base (sección 4). Protecciones: un administrador no puede
desactivarse ni quitarse el rol a sí mismo, y el sistema nunca queda sin un administrador activo.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Profesional
from app.repositories import catalogo_repo
from app.schemas.catalogos import ProfesionalAdminOut, ProfesionalUpdate
from app.schemas.cuentas import (
    CuentaExistente,
    ProfesionalCrear,
    ProfesionalGestionOut,
)
from app.services import catalogo_service
from app.services.errors import ConflictError, DatosInvalidosError, NotFoundError
from app.services.identidad_service import (
    IdentidadError,
    ProveedorIdentidad,
    UsuarioIdentidad,
    UsuarioYaExisteError,
)


class ProveedorNoDisponibleError(Exception):
    """El proveedor de identidad no respondió o la configuración es inválida (el router responde 502)."""


def _rol_de(u: UsuarioIdentidad | None) -> str | None:
    if u is None:
        return None
    admin = get_settings().role_administrador
    return admin if admin in u.roles else (u.roles[0] if u.roles else None)


def _llamar(funcion, *args):
    try:
        return funcion(*args)
    except UsuarioYaExisteError as exc:
        raise ConflictError(str(exc)) from exc
    except IdentidadError as exc:
        if exc.sin_conexion:
            raise ProveedorNoDisponibleError(str(exc)) from exc
        raise DatosInvalidosError(str(exc)) from exc


def _gestion(p: Profesional, usuarios: dict[str, UsuarioIdentidad]) -> ProfesionalGestionOut:
    u = usuarios.get(p.auth_id) if p.auth_id else None
    base = catalogo_service._prof_admin(p)
    return ProfesionalGestionOut(
        **base.model_dump(),
        tiene_cuenta=u is not None,
        rol=_rol_de(u),
        cuenta_bloqueada=u.bloqueado if u else None,
    )


def listar(db: Session, identidad: ProveedorIdentidad) -> list[ProfesionalGestionOut]:
    usuarios = {u.id: u for u in _llamar(identidad.listar_usuarios)}
    return [_gestion(p, usuarios) for p in catalogo_repo.listar(db, Profesional, solo_activos=False)]


def _verificar_duplicados(db: Session, *, identificacion: str | None, correo: str | None) -> None:
    choque = catalogo_repo.profesional_con(db, identificacion=identificacion, correo=correo)
    if choque:
        raise ConflictError(f"Ya existe un profesional con ese {choque}")


def crear_con_cuenta(db: Session, identidad: ProveedorIdentidad, datos: ProfesionalCrear) -> ProfesionalGestionOut:
    _verificar_duplicados(db, identificacion=datos.identificacion, correo=datos.correo)
    uid = _llamar(identidad.crear_usuario, datos.correo, datos.password, datos.rol)
    try:
        p = catalogo_repo.agregar(
            db,
            Profesional(
                nombre=datos.nombre,
                identificacion=datos.identificacion,
                correo=datos.correo,
                especializacion=datos.especializacion,
                auth_id=uid,
                activo=True,
            ),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _deshacer(identidad, uid)  # no dejar una cuenta huérfana sin profesional
        raise ConflictError("Ya existe un profesional con esos datos") from exc
    except Exception:
        db.rollback()
        _deshacer(identidad, uid)
        raise
    return _gestion(p, {uid: UsuarioIdentidad(uid, datos.correo, (datos.rol,), False)})


def crear_solo_ficha(db: Session, datos: ProfesionalCrear) -> ProfesionalGestionOut:
    """Profesional sin cuenta nueva (histórico, o enlazado a una cuenta existente por `auth_id`)."""
    base = catalogo_service.crear_profesional(db, datos)
    return ProfesionalGestionOut(**base.model_dump(), tiene_cuenta=bool(base.auth_id), rol=None, cuenta_bloqueada=None)


def _deshacer(identidad: ProveedorIdentidad, uid: str) -> None:
    try:
        identidad.borrar_usuario(uid)
    except IdentidadError:
        pass  # queda registrado por el log del proveedor; el administrador puede borrarla desde el panel


def _profesional(db: Session, id_: int) -> Profesional:
    p = catalogo_repo.obtener(db, Profesional, id_)
    if p is None:
        raise NotFoundError("Profesional no encontrado")
    return p


def _administradores_activos(identidad: ProveedorIdentidad, excluyendo: str | None = None) -> int:
    admin = get_settings().role_administrador
    return sum(
        1 for u in _llamar(identidad.listar_usuarios) if admin in u.roles and not u.bloqueado and u.id != excluyendo
    )


def crear_cuenta_existente(
    db: Session, identidad: ProveedorIdentidad, id_: int, datos: CuentaExistente
) -> ProfesionalGestionOut:
    p = _profesional(db, id_)
    if p.auth_id:
        raise ConflictError("Este profesional ya tiene una cuenta")
    uid = _llamar(identidad.crear_usuario, p.correo.lower(), datos.password, datos.rol)
    try:
        p.auth_id = uid
        db.commit()
    except Exception:
        db.rollback()
        _deshacer(identidad, uid)
        raise
    return _gestion(p, {uid: UsuarioIdentidad(uid, p.correo, (datos.rol,), False)})


def cambiar_password(db: Session, identidad: ProveedorIdentidad, id_: int, password: str) -> None:
    p = _profesional(db, id_)
    if not p.auth_id:
        raise DatosInvalidosError("Este profesional no tiene cuenta")
    _llamar(identidad.cambiar_password, p.auth_id, password)


def cambiar_rol(
    db: Session, identidad: ProveedorIdentidad, id_: int, rol: str, *, auth_sub: str
) -> ProfesionalGestionOut:
    p = _profesional(db, id_)
    if not p.auth_id:
        raise DatosInvalidosError("Este profesional no tiene cuenta")
    admin = get_settings().role_administrador
    if rol != admin:
        if p.auth_id == auth_sub:
            raise ConflictError("No puedes quitarte el rol de administrador a ti mismo")
        if _administradores_activos(identidad, excluyendo=p.auth_id) == 0:
            raise ConflictError("El sistema no puede quedarse sin un administrador activo")
    _llamar(identidad.cambiar_rol, p.auth_id, rol)
    usuarios = {u.id: u for u in _llamar(identidad.listar_usuarios)}
    return _gestion(p, usuarios)


def actualizar_profesional(
    db: Session,
    identidad: ProveedorIdentidad | None,
    id_: int,
    datos: ProfesionalUpdate,
    *,
    auth_sub: str,
) -> ProfesionalAdminOut:
    """PATCH del profesional. Si cambia `activo` y tiene cuenta, también bloquea o desbloquea la cuenta."""
    p = _profesional(db, id_)
    nuevo = datos.activo
    if nuevo is not None and nuevo != p.activo and p.auth_id:
        if not nuevo:
            if p.auth_id == auth_sub:
                raise ConflictError("No puedes desactivarte a ti mismo")
            if identidad is not None and _administradores_activos(identidad, excluyendo=p.auth_id) == 0:
                admins = [u for u in _llamar(identidad.listar_usuarios) if u.id == p.auth_id]
                if admins and get_settings().role_administrador in admins[0].roles:
                    raise ConflictError("El sistema no puede quedarse sin un administrador activo")
        if identidad is not None:  # sin proveedor, el bloqueo lo aplica igual la API (profesional inactivo => 403)
            _llamar(identidad.bloquear, p.auth_id, not nuevo)
    return catalogo_service.actualizar_profesional(db, id_, datos)
