"""Catálogos aseguradora, tratamiento y profesional. Carpeta: app/services — Sprint 7.

Crear y editar es solo del administrador; leer, del personal clínico. Se inactivan, no se borran (regla 5).
Nombre único sin distinguir mayúsculas ni tildes. profesional.auth_id enlaza con el usuario del IdP.
"""

from sqlalchemy.orm import Session

from app.models import Aseguradora, Profesional, Tratamiento
from app.repositories import catalogo_repo
from app.schemas.catalogos import (
    CatalogoCreate,
    CatalogoOut,
    CatalogoUpdate,
    ProfesionalAdminOut,
    ProfesionalCreate,
    ProfesionalOut,
    ProfesionalUpdate,
)
from app.services.errors import ConflictError, NotFoundError

_PK = {Aseguradora: "id_aseguradora", Tratamiento: "id_tratamiento"}
_ETIQUETA = {Aseguradora: "aseguradora", Tratamiento: "tratamiento"}


def _salida(modelo, fila) -> CatalogoOut:
    return CatalogoOut(id=getattr(fila, _PK[modelo]), nombre=fila.nombre, activo=fila.activo)


def listar(db: Session, modelo, *, solo_activos: bool) -> list[CatalogoOut]:
    return [_salida(modelo, f) for f in catalogo_repo.listar(db, modelo, solo_activos=solo_activos)]


def crear(db: Session, modelo, datos: CatalogoCreate) -> CatalogoOut:
    if catalogo_repo.existe_nombre(db, modelo, datos.nombre):
        raise ConflictError(f"Ya existe una {_ETIQUETA[modelo]} con ese nombre")
    fila = catalogo_repo.agregar(db, modelo(nombre=datos.nombre, activo=True))
    db.commit()
    return _salida(modelo, fila)


def actualizar(db: Session, modelo, id_: int, datos: CatalogoUpdate) -> CatalogoOut:
    fila = catalogo_repo.obtener(db, modelo, id_)
    if fila is None:
        raise NotFoundError(f"{_ETIQUETA[modelo].capitalize()} no encontrada")
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if "nombre" in cambios and catalogo_repo.existe_nombre(db, modelo, cambios["nombre"], excluir_id=id_):
        raise ConflictError(f"Ya existe una {_ETIQUETA[modelo]} con ese nombre")
    for campo, valor in cambios.items():
        setattr(fila, campo, valor)
    db.commit()
    return _salida(modelo, fila)


# --- profesionales ---------------------------------------------------------------------------------------------


def _prof_out(p: Profesional) -> ProfesionalOut:
    return ProfesionalOut(
        id_profesional=p.id_profesional, nombre=p.nombre, especializacion=p.especializacion, activo=p.activo
    )


def _prof_admin(p: Profesional) -> ProfesionalAdminOut:
    return ProfesionalAdminOut(
        **_prof_out(p).model_dump(), identificacion=p.identificacion, correo=p.correo, auth_id=p.auth_id
    )


def listar_profesionales(db: Session, *, solo_activos: bool) -> list[ProfesionalOut]:
    return [_prof_out(p) for p in catalogo_repo.listar(db, Profesional, solo_activos=solo_activos)]


def profesional_actual(db: Session, auth_sub: str) -> ProfesionalOut:
    p = catalogo_repo.profesional_por_auth_id(db, auth_sub)
    if p is None:
        raise NotFoundError("Tu usuario no está enlazado a ningún profesional")
    return _prof_out(p)


def crear_profesional(db: Session, datos: ProfesionalCreate) -> ProfesionalAdminOut:
    choque = catalogo_repo.profesional_con(
        db, identificacion=datos.identificacion, correo=datos.correo, auth_id=datos.auth_id
    )
    if choque:
        raise ConflictError(f"Ya existe un profesional con ese {choque}")
    p = catalogo_repo.agregar(db, Profesional(**datos.model_dump(), activo=True))
    db.commit()
    return _prof_admin(p)


def actualizar_profesional(db: Session, id_: int, datos: ProfesionalUpdate) -> ProfesionalAdminOut:
    p = catalogo_repo.obtener(db, Profesional, id_)
    if p is None:
        raise NotFoundError("Profesional no encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("nombre", "correo", "activo"):  # columnas NOT NULL: no se pueden dejar vacías
        if campo in cambios and cambios[campo] is None:
            del cambios[campo]
    choque = catalogo_repo.profesional_con(
        db, correo=cambios.get("correo"), auth_id=cambios.get("auth_id"), excluir_id=id_
    )
    if choque:
        raise ConflictError(f"Ya existe un profesional con ese {choque}")
    for campo, valor in cambios.items():
        setattr(p, campo, valor)
    db.commit()
    return _prof_admin(p)
