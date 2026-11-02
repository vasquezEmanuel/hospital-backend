"""Expediente del paciente. Carpeta: app/services — Sprint 3.

Búsqueda "por paciente -> enfermedades e imágenes": reúne la ficha, las atenciones (más reciente primero), sus
diagnósticos de hospitalización y bucales con los códigos CIE-10 vinculados, y las imágenes activas. Reglas 2 y 3
(los códigos del diagnóstico bucal son odontológicos; a lo sumo un diagnóstico de hospitalización por atención), 4 y 5
(solo imágenes activas) y 7 (enlaces firmados). La auditoría de la consulta (regla 6) se conecta en el Sprint 4.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Atencion, Cie10, DiagnosticoBucal, DiagnosticoHospitalario
from app.repositories import imagen_repo
from app.schemas.expediente import (
    AtencionExpediente,
    CodigoCie10,
    DiagnosticoBucalOut,
    DiagnosticoHospitalarioOut,
    ExpedienteOut,
)
from app.services import imagen_service, paciente_service
from app.services.almacenamiento import Almacenamiento


def _codigo(c: Cie10) -> CodigoCie10:
    return CodigoCie10(cod_4=c.cod_4, descripcion=c.descripcion_4, es_odontologico=c.es_odontologico)


def obtener(db: Session, almacen: Almacenamiento, id_paciente: int) -> ExpedienteOut:
    paciente = paciente_service.obtener(db, id_paciente)  # NotFoundError si no existe

    atenciones = db.scalars(
        select(Atencion)
        .where(Atencion.id_paciente == id_paciente)
        .options(joinedload(Atencion.aseguradora), joinedload(Atencion.profesional))
        .order_by(Atencion.fecha_atencion.desc(), Atencion.id_atencion.desc())
    ).all()
    ids = [a.id_atencion for a in atenciones]

    hospitalarios: dict[int, DiagnosticoHospitalario] = {}
    bucales: dict[int, list[DiagnosticoBucal]] = defaultdict(list)
    if ids:
        for d in db.scalars(
            select(DiagnosticoHospitalario)
            .where(DiagnosticoHospitalario.id_atencion.in_(ids), DiagnosticoHospitalario.activo.is_(True))
            .options(joinedload(DiagnosticoHospitalario.cie10))
        ):
            hospitalarios[d.id_atencion] = d
        for d in db.scalars(
            select(DiagnosticoBucal)
            .where(DiagnosticoBucal.id_atencion.in_(ids), DiagnosticoBucal.activo.is_(True))
            .options(selectinload(DiagnosticoBucal.codigos))
            .order_by(DiagnosticoBucal.id_diagnostico_bucal)
        ):
            bucales[d.id_atencion].append(d)

    imagenes_por_atencion = defaultdict(list)
    sin_atencion = []
    filas = imagen_repo.por_paciente(db, id_paciente)
    for fila in filas:
        salida = imagen_service.a_salida(almacen, fila)
        if salida.id_atencion is None:
            sin_atencion.append(salida)
        else:
            imagenes_por_atencion[salida.id_atencion].append(salida)

    items = []
    for a in atenciones:
        hosp = hospitalarios.get(a.id_atencion)
        items.append(
            AtencionExpediente(
                id_atencion=a.id_atencion,
                fecha_atencion=a.fecha_atencion,
                hora_atencion=a.hora_atencion,
                aseguradora=a.aseguradora.nombre if a.aseguradora else None,
                ubicacion=a.ubicacion,
                profesional=a.profesional.nombre if a.profesional else a.profesional_texto,
                plan_tratamiento=a.plan_tratamiento,
                observaciones=a.observaciones,
                registrada_en=a.creado_en,
                diagnostico_hospitalario=(
                    DiagnosticoHospitalarioOut(
                        descripcion_original=hosp.descripcion_original,
                        codigo=_codigo(hosp.cie10) if hosp.cie10 else None,
                    )
                    if hosp
                    else None
                ),
                diagnosticos_bucales=[
                    DiagnosticoBucalOut(
                        id_diagnostico_bucal=d.id_diagnostico_bucal,
                        descripcion=d.descripcion,
                        codigos=[_codigo(c) for c in d.codigos],
                        codificado=bool(d.codigos),
                    )
                    for d in bucales.get(a.id_atencion, [])
                ],
                imagenes=imagenes_por_atencion.get(a.id_atencion, []),
            )
        )
    return ExpedienteOut(
        paciente=paciente, atenciones=items, imagenes_sin_atencion=sin_atencion, total_imagenes=len(filas)
    )
