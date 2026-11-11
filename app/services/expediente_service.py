"""Expediente del paciente. Carpeta: app/services — Sprint 3.

Búsqueda "por paciente -> enfermedades e imágenes": reúne la ficha, las atenciones (más reciente primero), sus
diagnósticos de hospitalización y bucales con los códigos CIE-10 vinculados, y las imágenes activas. Reglas 2 y 3
(los códigos del diagnóstico bucal son odontológicos; a lo sumo un diagnóstico de hospitalización por atención), 4 y 5
(solo imágenes activas) y 7 (enlaces firmados). La auditoría de la consulta (regla 6) se conecta en el Sprint 4.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Atencion, Cie10
from app.repositories import imagen_repo, paciente_repo
from app.schemas.expediente import (
    CodigoCie10,
    ExpedienteOut,
)
from app.services import atencion_service, imagen_service, paciente_service
from app.services.almacenamiento import Almacenamiento
from app.services.errors import NotFoundError


def _codigo(c: Cie10) -> CodigoCie10:
    return CodigoCie10(cod_4=c.cod_4, descripcion=c.descripcion_4, es_odontologico=c.es_odontologico)


def obtener(db: Session, almacen: Almacenamiento, id_paciente: UUID) -> ExpedienteOut:
    registro = paciente_repo.obtener(db, id_paciente)
    if registro is None:
        raise NotFoundError("Paciente no encontrado")
    paciente = paciente_service.a_salida(db, registro)
    id_interno = registro.id_paciente

    atenciones = db.scalars(
        select(Atencion)
        .where(Atencion.id_paciente == id_interno)
        .options(joinedload(Atencion.aseguradora), joinedload(Atencion.profesional))
        .order_by(Atencion.fecha_atencion.desc(), Atencion.id_atencion.desc())
    ).all()
    imagenes_por_atencion = defaultdict(list)
    sin_atencion = []
    filas = imagen_repo.por_paciente(db, id_interno)
    for fila in filas:
        salida = imagen_service.a_salida(almacen, fila)
        if salida.id_atencion is None:
            sin_atencion.append(salida)
        else:
            imagenes_por_atencion[salida.id_atencion].append(salida)

    items = atencion_service.armar(db, atenciones, imagenes_por_atencion)
    return ExpedienteOut(
        paciente=paciente, atenciones=items, imagenes_sin_atencion=sin_atencion, total_imagenes=len(filas)
    )
