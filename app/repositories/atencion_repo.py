"""Acceso a datos de atencion y sus tablas hijas. Carpeta: app/repositories — Sprint 7.

Entidades: atencion, diagnostico_hospitalario, diagnostico_bucal (+ puente CIE-10), atencion_x_tratamiento.
Regla 5: solo cuentan diagnósticos e imágenes activos. Regla 2: el trigger fn_validar_cie10_odontologico es la red de
seguridad final; el servicio ya valida antes de insertar.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Atencion,
    Cie10,
    DiagnosticoBucal,
    DiagnosticoHospitalario,
    ImagenClinica,
    Paciente,
    Tratamiento,
)
from app.models.diagnostico import cie10_x_diagnostico_bucal as puente
from app.repositories.busqueda import normalizar_busqueda, sin_tildes


def _filtrada(
    *,
    q: str | None,
    cod_4: str | None,
    id_paciente_interno: int | None,
    id_aseguradora: int | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
) -> Select:
    stmt = (
        select(Atencion, Paciente)
        .join(Paciente, Paciente.id_paciente == Atencion.id_paciente)
        .options(joinedload(Atencion.aseguradora), joinedload(Atencion.profesional))
    )
    if q:
        texto = normalizar_busqueda(q.strip())
        digitos = "".join(ch for ch in q if ch.isalnum()).upper()
        condiciones = [
            sin_tildes(Paciente.nombre).contains(texto, autoescape=True),
            Paciente.documento_identidad.contains(digitos, autoescape=True) if digitos else False,
        ]
        stmt = stmt.where(or_(*condiciones))
    if cod_4:
        hosp = exists().where(
            DiagnosticoHospitalario.id_atencion == Atencion.id_atencion,
            DiagnosticoHospitalario.cod_4 == cod_4,
            DiagnosticoHospitalario.activo.is_(True),
        )
        bucal = (
            exists()
            .where(DiagnosticoBucal.id_atencion == Atencion.id_atencion)
            .where(DiagnosticoBucal.activo.is_(True))
            .where(puente.c.id_diagnostico_bucal == DiagnosticoBucal.id_diagnostico_bucal)
            .where(puente.c.cod_4 == cod_4)
        )
        stmt = stmt.where(or_(hosp, bucal))
    if id_paciente_interno is not None:
        stmt = stmt.where(Atencion.id_paciente == id_paciente_interno)
    if id_aseguradora is not None:
        stmt = stmt.where(Atencion.id_aseguradora == id_aseguradora)
    if fecha_desde:
        stmt = stmt.where(Atencion.fecha_atencion >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Atencion.fecha_atencion <= fecha_hasta)
    return stmt


def listar(db: Session, *, page: int, page_size: int, **filtros) -> tuple[list[tuple[Atencion, Paciente]], int]:
    base = _filtrada(**filtros)
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    filas = db.execute(
        base.order_by(Atencion.fecha_atencion.desc(), Atencion.id_atencion.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [tuple(f) for f in filas], total


def obtener(db: Session, public_id: UUID) -> tuple[Atencion, Paciente] | None:
    fila = db.execute(
        select(Atencion, Paciente)
        .join(Paciente, Paciente.id_paciente == Atencion.id_paciente)
        .where(Atencion.public_id == public_id)
        .options(joinedload(Atencion.aseguradora), joinedload(Atencion.profesional))
    ).first()
    return tuple(fila) if fila else None


def conteo_imagenes(db: Session, ids_atencion: list[int]) -> dict[int, int]:
    if not ids_atencion:
        return {}
    filas = db.execute(
        select(ImagenClinica.id_atencion, func.count())
        .where(ImagenClinica.id_atencion.in_(ids_atencion), ImagenClinica.activo.is_(True))
        .group_by(ImagenClinica.id_atencion)
    )
    return {i: n for i, n in filas}


def codigos_existentes(db: Session, codigos: list[str]) -> dict[str, Cie10]:
    if not codigos:
        return {}
    return {c.cod_4: c for c in db.scalars(select(Cie10).where(Cie10.cod_4.in_(codigos)))}


def tratamientos_por_ids(db: Session, ids: list[int]) -> list[Tratamiento]:
    if not ids:
        return []
    return list(db.scalars(select(Tratamiento).where(Tratamiento.id_tratamiento.in_(ids))))


def agregar(db: Session, atencion: Atencion) -> Atencion:
    db.add(atencion)
    db.flush()
    return atencion
