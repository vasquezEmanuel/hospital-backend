"""Acceso a los catálogos de ubicación. Carpeta: app/repositories — departamento y municipio (DIVIPOLA)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Departamento, Municipio
from app.repositories.busqueda import normalizar_busqueda, sin_tildes


def departamentos(db: Session) -> list[Departamento]:
    return list(db.scalars(select(Departamento).order_by(sin_tildes(Departamento.nombre))))


def departamento(db: Session, codigo: str) -> Departamento | None:
    return db.get(Departamento, codigo)


def municipio(db: Session, codigo: str) -> Municipio | None:
    return db.get(Municipio, codigo)


def municipios(
    db: Session, *, codigo_departamento: str | None = None, q: str | None = None, limite: int | None = None
) -> list[tuple[Municipio, str]]:
    """Municipios con el nombre de su departamento, ordenados alfabéticamente; `q` busca sin tildes ni mayúsculas."""
    consulta = (
        select(Municipio, Departamento.nombre)
        .join(Departamento, Departamento.codigo == Municipio.codigo_departamento)
        .order_by(sin_tildes(Municipio.nombre), Municipio.codigo)
    )
    if codigo_departamento:
        consulta = consulta.where(Municipio.codigo_departamento == codigo_departamento)
    if q:
        consulta = consulta.where(sin_tildes(Municipio.nombre).contains(normalizar_busqueda(q), autoescape=True))
    if limite:
        consulta = consulta.limit(limite)
    return [(m, d) for m, d in db.execute(consulta).all()]


def ubicacion_de(db: Session, codigo_municipio: str | None) -> tuple[Municipio, Departamento] | None:
    """Municipio y departamento de un código; None si no hay código o no existe."""
    if not codigo_municipio:
        return None
    m = db.get(Municipio, codigo_municipio)
    return (m, db.get(Departamento, m.codigo_departamento)) if m else None
