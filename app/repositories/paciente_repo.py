"""Acceso a datos de paciente (+ agregados de atencion). Carpeta: app/repositories.

Soporta la búsqueda enfermedad↔paciente a futuro (índices sobre documento_identidad / id_paciente).
"""

import re
from datetime import date

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Aseguradora, Atencion, Paciente

_CODIGO = re.compile(r"^P-?(\d+)$", re.IGNORECASE)
_DOC_SEPARATORS = re.compile(r"[.\s-]")


def _agregados():
    return (
        select(
            Atencion.id_paciente.label("id_paciente"),
            func.count().label("total"),
            func.max(Atencion.fecha_atencion).label("ultima"),
        )
        .group_by(Atencion.id_paciente)
        .subquery()
    )


def listar(
    db: Session,
    *,
    q: str | None,
    documento: str | None,
    sexo: str | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Paciente, int, date | None]], int]:
    agg = _agregados()
    base: Select = select(Paciente, func.coalesce(agg.c.total, 0), agg.c.ultima).outerjoin(
        agg, agg.c.id_paciente == Paciente.id_paciente
    )
    if documento:
        base = base.where(Paciente.documento_identidad == _DOC_SEPARATORS.sub("", documento).upper())
    if q:
        q = q.strip()
        condiciones = [Paciente.nombre.icontains(q, autoescape=True)]
        solo_doc = _DOC_SEPARATORS.sub("", q)
        if solo_doc:
            condiciones.append(Paciente.documento_identidad.icontains(solo_doc, autoescape=True))
        m = _CODIGO.match(q)
        if m:
            condiciones.append(Paciente.id_paciente == int(m.group(1)))
        base = base.where(or_(*condiciones))
    if sexo:
        base = base.where(Paciente.sexo == sexo)
    if fecha_desde or fecha_hasta:
        sub = select(Atencion.id_atencion).where(Atencion.id_paciente == Paciente.id_paciente)
        if fecha_desde:
            sub = sub.where(Atencion.fecha_atencion >= fecha_desde)
        if fecha_hasta:
            sub = sub.where(Atencion.fecha_atencion <= fecha_hasta)
        base = base.where(exists(sub))

    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    rows = db.execute(
        base.order_by(agg.c.ultima.desc().nulls_last(), Paciente.id_paciente)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [(p, int(t), u) for p, t, u in rows], total


def obtener(db: Session, id_paciente: int) -> Paciente | None:
    return db.get(Paciente, id_paciente)


def existe_documento(db: Session, documento: str) -> bool:
    return db.scalar(select(exists().where(Paciente.documento_identidad == documento))) or False


def resumen_atenciones(db: Session, id_paciente: int) -> tuple[int, date | None, str | None]:
    """(total, fecha de la última atención, aseguradora de la última atención)."""
    total, ultima = db.execute(
        select(func.count(), func.max(Atencion.fecha_atencion)).where(Atencion.id_paciente == id_paciente)
    ).one()
    aseguradora = db.scalar(
        select(Aseguradora.nombre)
        .join(Atencion, Atencion.id_aseguradora == Aseguradora.id_aseguradora)
        .where(Atencion.id_paciente == id_paciente)
        .order_by(Atencion.fecha_atencion.desc(), Atencion.id_atencion.desc())
        .limit(1)
    )
    return int(total), ultima, aseguradora


def agregar(db: Session, paciente: Paciente) -> Paciente:
    db.add(paciente)
    db.flush()
    db.refresh(paciente)
    return paciente
