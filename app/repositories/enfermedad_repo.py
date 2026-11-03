"""Búsqueda por enfermedad. Carpeta: app/repositories — Sprint 4 (búsqueda integrada: enfermedad -> pacientes).

Entidades: cie10, diagnostico_hospitalario, diagnostico_bucal (tabla puente cie10_x_diagnostico_bucal), atencion,
paciente. Solo cuentan diagnósticos activos (regla 5). Regla 2: un diagnóstico bucal solo se vincula a códigos
odontológicos; el diagnóstico de hospitalización puede ser cualquier código.
"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Atencion, DiagnosticoBucal, DiagnosticoHospitalario, Paciente
from app.models.diagnostico import cie10_x_diagnostico_bucal as puente
from app.schemas.enfermedad import Ambito


def _atenciones_con_codigo(cod_4: str, ambito: Ambito) -> Select:
    hospitalizacion = select(DiagnosticoHospitalario.id_atencion).where(
        DiagnosticoHospitalario.cod_4 == cod_4, DiagnosticoHospitalario.activo.is_(True)
    )
    bucal = (
        select(DiagnosticoBucal.id_atencion)
        .join(puente, puente.c.id_diagnostico_bucal == DiagnosticoBucal.id_diagnostico_bucal)
        .where(puente.c.cod_4 == cod_4, DiagnosticoBucal.activo.is_(True))
    )
    if ambito is Ambito.hospitalizacion:
        return hospitalizacion
    if ambito is Ambito.bucal:
        return bucal
    return hospitalizacion.union(bucal)


def atenciones(
    db: Session, cod_4: str, ambito: Ambito, *, page: int, page_size: int
) -> tuple[list[tuple[Atencion, Paciente]], int]:
    ids = _atenciones_con_codigo(cod_4, ambito).subquery()
    base = (
        select(Atencion, Paciente)
        .join(Paciente, Paciente.id_paciente == Atencion.id_paciente)
        .where(Atencion.id_atencion.in_(select(ids.c.id_atencion)))
    )
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    filas = db.execute(
        base.order_by(Atencion.fecha_atencion.desc(), Atencion.id_atencion.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [tuple(f) for f in filas], total


def hospitalarios(db: Session, ids_atencion: list[int]) -> dict[int, DiagnosticoHospitalario]:
    if not ids_atencion:
        return {}
    filas = db.scalars(
        select(DiagnosticoHospitalario).where(
            DiagnosticoHospitalario.id_atencion.in_(ids_atencion), DiagnosticoHospitalario.activo.is_(True)
        )
    )
    return {d.id_atencion: d for d in filas}


def bucales(db: Session, ids_atencion: list[int]) -> dict[int, list[DiagnosticoBucal]]:
    por_atencion: dict[int, list[DiagnosticoBucal]] = {i: [] for i in ids_atencion}
    if not ids_atencion:
        return por_atencion
    filas = db.scalars(
        select(DiagnosticoBucal)
        .where(DiagnosticoBucal.id_atencion.in_(ids_atencion), DiagnosticoBucal.activo.is_(True))
        .options(selectinload(DiagnosticoBucal.codigos))
        .order_by(DiagnosticoBucal.id_diagnostico_bucal)
    )
    for d in filas:
        por_atencion[d.id_atencion].append(d)
    return por_atencion
