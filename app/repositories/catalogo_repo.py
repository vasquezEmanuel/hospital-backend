"""Acceso a datos de los catálogos aseguradora, tratamiento y profesional. Carpeta: app/repositories — Sprint 7.

Regla 5 (por analogía): los catálogos se inactivan, nunca se borran. La unicidad de nombre se valida sin distinguir
mayúsculas/tildes para evitar "Sura" y "SURA" como dos aseguradoras.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Aseguradora, Profesional, Tratamiento
from app.repositories.busqueda import sin_tildes


def listar(db: Session, modelo, *, solo_activos: bool):
    stmt = select(modelo).order_by(modelo.nombre)
    if solo_activos:
        stmt = stmt.where(modelo.activo.is_(True))
    return list(db.scalars(stmt))


def obtener(db: Session, modelo, id_: int):
    return db.get(modelo, id_)


def existe_nombre(db: Session, modelo, nombre: str, *, excluir_id: int | None = None) -> bool:
    from app.repositories.busqueda import normalizar_busqueda

    stmt = select(modelo).where(sin_tildes(modelo.nombre) == normalizar_busqueda(nombre))
    for fila in db.scalars(stmt):
        if excluir_id is None or getattr(fila, _pk(modelo)) != excluir_id:
            return True
    return False


def _pk(modelo) -> str:
    return {Aseguradora: "id_aseguradora", Tratamiento: "id_tratamiento", Profesional: "id_profesional"}[modelo]


def agregar(db: Session, fila):
    db.add(fila)
    db.flush()
    return fila


def profesional_por_auth_id(db: Session, auth_sub: str) -> Profesional | None:
    return db.scalar(select(Profesional).where(Profesional.auth_id == auth_sub))


def profesional_con(
    db: Session,
    *,
    identificacion: str | None = None,
    correo: str | None = None,
    auth_id: str | None = None,
    excluir_id: int | None = None,
) -> str | None:
    """Nombre del campo que choca con otro profesional (identificación, correo o auth_id), o None."""
    campos = (
        ("identificación", Profesional.identificacion, identificacion),
        ("correo", Profesional.correo, correo),
        ("auth_id", Profesional.auth_id, auth_id),
    )
    for nombre, columna, valor in campos:
        if not valor:
            continue
        otro = db.scalar(select(Profesional.id_profesional).where(columna == valor))
        if otro is not None and otro != excluir_id:
            return nombre
    return None
