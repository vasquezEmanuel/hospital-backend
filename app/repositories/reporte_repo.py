"""Consultas agregadas de reportes e inicio. Carpeta: app/repositories — Sprint 9.

Solo lectura. Todas parten de las atenciones que cumplen los filtros (fecha, aseguradora, diagnóstico, profesional) y
cuentan únicamente diagnósticos e imágenes activos (regla 5).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, distinct, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Aseguradora,
    Atencion,
    Cie10,
    DiagnosticoBucal,
    DiagnosticoHospitalario,
    ImagenClinica,
    Profesional,
    Tratamiento,
)
from app.models.atencion import atencion_x_tratamiento
from app.models.diagnostico import cie10_x_diagnostico_bucal as puente
from app.repositories.busqueda import sin_tildes


@dataclass(frozen=True)
class Filtros:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    id_aseguradora: int | None = None
    cod_4: str | None = None
    id_profesional: int | None = None


def _atenciones(f: Filtros) -> Select:
    """ids de las atenciones que cumplen el filtro (se usa como subconsulta en todos los reportes)."""
    stmt = select(Atencion.id_atencion)
    if f.fecha_desde:
        stmt = stmt.where(Atencion.fecha_atencion >= f.fecha_desde)
    if f.fecha_hasta:
        stmt = stmt.where(Atencion.fecha_atencion <= f.fecha_hasta)
    if f.id_aseguradora is not None:
        stmt = stmt.where(Atencion.id_aseguradora == f.id_aseguradora)
    if f.id_profesional is not None:
        stmt = stmt.where(Atencion.id_profesional == f.id_profesional)
    if f.cod_4:
        hosp = exists().where(
            DiagnosticoHospitalario.id_atencion == Atencion.id_atencion,
            DiagnosticoHospitalario.cod_4 == f.cod_4,
            DiagnosticoHospitalario.activo.is_(True),
        )
        bucal = (
            exists()
            .where(DiagnosticoBucal.id_atencion == Atencion.id_atencion, DiagnosticoBucal.activo.is_(True))
            .where(puente.c.id_diagnostico_bucal == DiagnosticoBucal.id_diagnostico_bucal, puente.c.cod_4 == f.cod_4)
        )
        stmt = stmt.where(or_(hosp, bucal))
    return stmt


def totales(db: Session, f: Filtros) -> tuple[int, int, int]:
    ids = _atenciones(f).subquery()
    atenciones = db.scalar(select(func.count()).select_from(ids)) or 0
    pacientes = (
        db.scalar(select(func.count(distinct(Atencion.id_paciente))).where(Atencion.id_atencion.in_(select(ids)))) or 0
    )
    imagenes = (
        db.scalar(
            select(func.count()).where(ImagenClinica.activo.is_(True), ImagenClinica.id_atencion.in_(select(ids)))
        )
        or 0
    )
    return pacientes, atenciones, imagenes


def _filas(db: Session, stmt: Select, limite: int) -> list[tuple]:
    return [tuple(r) for r in db.execute(stmt.limit(limite + 1)).all()]


def _donde_ids(f: Filtros):
    return Atencion.id_atencion.in_(_atenciones(f).scalar_subquery())


def total_atenciones(db: Session, f: Filtros, limite: int):
    n = db.scalar(select(func.count()).select_from(_atenciones(f).subquery())) or 0
    return [("Total de atenciones odontológicas", None, n)]


def por_aseguradora(db: Session, f: Filtros, limite: int):
    nombre = func.coalesce(Aseguradora.nombre, "Sin aseguradora").label("etiqueta")
    cantidad = func.count()
    stmt = (
        select(nombre, cantidad)
        .select_from(Atencion)
        .outerjoin(Aseguradora, Aseguradora.id_aseguradora == Atencion.id_aseguradora)
        .where(_donde_ids(f))
        .group_by(nombre)
        .order_by(cantidad.desc(), nombre)
    )
    return [(e, None, c) for e, c in _filas(db, stmt, limite)]


def _dx_hospitalario():
    cod = DiagnosticoHospitalario.cod_4
    return func.coalesce(
        func.nullif(func.concat_ws(" · ", cod, Cie10.descripcion_4), ""),
        DiagnosticoHospitalario.descripcion_original,
    )


def por_dx_hospitalario(db: Session, f: Filtros, limite: int):
    etiqueta = func.coalesce(_dx_hospitalario(), "Sin diagnóstico hospitalario").label("etiqueta")
    cantidad = func.count()
    stmt = (
        select(etiqueta, cantidad)
        .select_from(Atencion)
        .outerjoin(
            DiagnosticoHospitalario,
            and_(DiagnosticoHospitalario.id_atencion == Atencion.id_atencion, DiagnosticoHospitalario.activo.is_(True)),
        )
        .outerjoin(Cie10, Cie10.cod_4 == DiagnosticoHospitalario.cod_4)
        .where(_donde_ids(f))
        .group_by(etiqueta)
        .order_by(cantidad.desc(), etiqueta)
    )
    return [(e, None, c) for e, c in _filas(db, stmt, limite)]


def _clave_bucal():
    return sin_tildes(func.trim(DiagnosticoBucal.descripcion))


def distribucion_bucales(db: Session, f: Filtros, limite: int):
    clave = _clave_bucal()
    cantidad = func.count()
    stmt = (
        select(func.min(DiagnosticoBucal.descripcion), cantidad)
        .where(DiagnosticoBucal.activo.is_(True), DiagnosticoBucal.id_atencion.in_(_atenciones(f).scalar_subquery()))
        .group_by(clave)
        .order_by(cantidad.desc(), func.min(DiagnosticoBucal.descripcion))
    )
    return [(e, None, c) for e, c in _filas(db, stmt, limite)]


def tratamientos(db: Session, f: Filtros, limite: int):
    cantidad = func.count()
    stmt = (
        select(Tratamiento.nombre, cantidad)
        .join(atencion_x_tratamiento, atencion_x_tratamiento.c.id_tratamiento == Tratamiento.id_tratamiento)
        .where(atencion_x_tratamiento.c.id_atencion.in_(_atenciones(f).scalar_subquery()))
        .group_by(Tratamiento.nombre)
        .order_by(cantidad.desc(), Tratamiento.nombre)
    )
    return [(e, None, c) for e, c in _filas(db, stmt, limite)]


def por_profesional(db: Session, f: Filtros, limite: int):
    nombre = func.coalesce(Profesional.nombre, func.nullif(Atencion.profesional_texto, ""), "Sin profesional").label(
        "etiqueta"
    )
    cantidad = func.count()
    stmt = (
        select(nombre, cantidad)
        .select_from(Atencion)
        .outerjoin(Profesional, Profesional.id_profesional == Atencion.id_profesional)
        .where(_donde_ids(f))
        .group_by(nombre)
        .order_by(cantidad.desc(), nombre)
    )
    return [(e, None, c) for e, c in _filas(db, stmt, limite)]


def por_fecha(db: Session, f: Filtros, limite: int):
    stmt = (
        select(Atencion.fecha_atencion, func.count())
        .where(_donde_ids(f))
        .group_by(Atencion.fecha_atencion)
        .order_by(Atencion.fecha_atencion)
    )
    return [(e.strftime("%Y-%m-%d"), None, c) for e, c in _filas(db, stmt, limite)]


def relacion_hospitalario_bucal(db: Session, f: Filtros, limite: int):
    hosp = _dx_hospitalario().label("etiqueta")
    cantidad = func.count()
    clave = _clave_bucal()
    stmt = (
        select(hosp, func.min(DiagnosticoBucal.descripcion), cantidad)
        .select_from(DiagnosticoBucal)
        .join(
            DiagnosticoHospitalario,
            and_(
                DiagnosticoHospitalario.id_atencion == DiagnosticoBucal.id_atencion,
                DiagnosticoHospitalario.activo.is_(True),
            ),
        )
        .outerjoin(Cie10, Cie10.cod_4 == DiagnosticoHospitalario.cod_4)
        .where(DiagnosticoBucal.activo.is_(True), DiagnosticoBucal.id_atencion.in_(_atenciones(f).scalar_subquery()))
        .group_by(hosp, clave)
        .order_by(cantidad.desc(), hosp)
    )
    return [(h, b, c) for h, b, c in _filas(db, stmt, limite)]


def diagnosticos_distintos(db: Session) -> int:
    hosp = select(DiagnosticoHospitalario.cod_4.label("c")).where(
        DiagnosticoHospitalario.activo.is_(True), DiagnosticoHospitalario.cod_4.is_not(None)
    )
    bucal = (
        select(puente.c.cod_4.label("c"))
        .join(DiagnosticoBucal, DiagnosticoBucal.id_diagnostico_bucal == puente.c.id_diagnostico_bucal)
        .where(DiagnosticoBucal.activo.is_(True))
    )
    return db.scalar(select(func.count(distinct(hosp.union(bucal).subquery().c.c)))) or 0
