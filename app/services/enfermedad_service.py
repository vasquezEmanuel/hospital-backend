"""Búsqueda por enfermedad -> pacientes. Carpeta: app/services — Sprint 4 (documento técnico, 'búsqueda bidireccional').

Dado un código CIE-10 (cod_4) devuelve las atenciones en que aparece, con el paciente, sus diagnósticos bucales y sus
imágenes. El código se busca en el diagnóstico de hospitalización, en los diagnósticos bucales o en ambos (parámetro
`en`). Regla 5: solo diagnósticos e imágenes activos. Regla 7: las imágenes salen con enlace firmado.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.repositories import cie10_repo, enfermedad_repo, imagen_repo
from app.schemas.enfermedad import Ambito, EnfermedadPacienteOut, PacientesPorEnfermedadOut
from app.schemas.expediente import CodigoCie10
from app.services import imagen_service
from app.services.almacenamiento import Almacenamiento
from app.services.errors import NotFoundError
from app.services.paciente_service import codigo_paciente


def normalizar_codigo(cod_4: str) -> str:
    return cod_4.replace(".", "").strip().upper()


def buscar(
    db: Session,
    almacen: Almacenamiento,
    cod_4: str,
    ambito: Ambito,
    *,
    page: int,
    page_size: int,
    max_imagenes: int,
) -> PacientesPorEnfermedadOut:
    cod = normalizar_codigo(cod_4)
    cie10 = cie10_repo.obtener(db, cod)
    if cie10 is None:
        raise NotFoundError("Código CIE-10 no encontrado")

    filas, total = enfermedad_repo.atenciones(db, cod, ambito, page=page, page_size=page_size)
    ids_atencion = [a.id_atencion for a, _ in filas]
    hospitalarios = enfermedad_repo.hospitalarios(db, ids_atencion)
    bucales = enfermedad_repo.bucales(db, ids_atencion)

    imagenes_de: dict[int, list] = defaultdict(list)
    for fila in imagen_repo.por_pacientes(db, list({p.id_paciente for _, p in filas})):
        imagenes_de[fila[0].id_paciente].append(fila)

    items = []
    for atencion, paciente in filas:
        hosp = hospitalarios.get(atencion.id_atencion)
        dx_bucales = bucales[atencion.id_atencion]
        coincide = []
        if hosp is not None and hosp.cod_4 == cod:
            coincide.append("hospitalizacion")
        if any(c.cod_4 == cod for d in dx_bucales for c in d.codigos):
            coincide.append("bucal")
        todas = imagenes_de.get(paciente.id_paciente, [])
        items.append(
            EnfermedadPacienteOut(
                id_paciente=paciente.public_id,
                codigo_paciente=codigo_paciente(paciente.id_paciente),
                documento_identidad=paciente.documento_identidad,
                nombre=paciente.nombre,
                id_atencion=atencion.public_id,
                fecha_atencion=atencion.fecha_atencion,
                coincide_en=coincide,
                diagnostico_hospitalario=hosp.descripcion_original if hosp else None,
                diagnosticos_bucales=[d.descripcion for d in dx_bucales],
                total_imagenes=len(todas),
                imagenes=[imagen_service.a_salida(almacen, f) for f in todas[:max_imagenes]],
            )
        )
    return PacientesPorEnfermedadOut(
        codigo=CodigoCie10(cod_4=cie10.cod_4, descripcion=cie10.descripcion_4, es_odontologico=cie10.es_odontologico),
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
