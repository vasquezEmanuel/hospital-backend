"""Atenciones. Carpeta: app/services — Sprint 7 (pantallas 'Atenciones', 'Nueva atención', 'Detalle de atención').

Reglas: 2 (códigos del diagnóstico bucal odontológicos; el de hospitalización, cualquiera), 3 (0+ bucales, a lo sumo un
hospitalario), 5 (solo diagnósticos activos), 1 (la atención se asocia a un paciente existente, por su UUID).
La atención se guarda completa o no se guarda (una sola transacción). Las imágenes se suben después con
POST /imagenes indicando id_atencion / id_diagnostico_bucal.
"""

from collections import defaultdict
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import (
    Aseguradora,
    Atencion,
    Cie10,
    DiagnosticoBucal,
    DiagnosticoHospitalario,
    Paciente,
    Profesional,
    Tratamiento,
)
from app.repositories import atencion_repo, catalogo_repo, enfermedad_repo, imagen_repo, paciente_repo
from app.schemas.atencion import (
    AtencionCreate,
    AtencionDetalle,
    AtencionListItem,
    PacienteResumen,
)
from app.schemas.common import Page
from app.schemas.expediente import (
    AtencionExpediente,
    CodigoCie10,
    DiagnosticoBucalOut,
    DiagnosticoHospitalarioOut,
    TratamientoOut,
)
from app.services import imagen_service
from app.services.almacenamiento import Almacenamiento
from app.services.enfermedad_service import normalizar_codigo
from app.services.errors import DatosInvalidosError, NotFoundError
from app.services.paciente_service import codigo_paciente


def codigo_atencion(id_atencion: int) -> str:
    return f"A{id_atencion:03d}"  # solo para mostrar; las rutas usan el UUID


def _codigo(c: Cie10) -> CodigoCie10:
    return CodigoCie10(cod_4=c.cod_4, descripcion=c.descripcion_4, es_odontologico=c.es_odontologico)


def armar(db: Session, atenciones: list[Atencion], imagenes: dict[UUID, list]) -> list[AtencionExpediente]:
    """Arma las atenciones con diagnósticos, tratamientos e imágenes (la comparte el expediente y el detalle)."""
    ids = [a.id_atencion for a in atenciones]
    hospitalarios = enfermedad_repo.hospitalarios(db, ids)
    bucales = enfermedad_repo.bucales(db, ids)
    items = []
    for a in atenciones:
        hosp = hospitalarios.get(a.id_atencion)
        items.append(
            AtencionExpediente(
                id_atencion=a.public_id,
                codigo_atencion=codigo_atencion(a.id_atencion),
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
                        id_diagnostico_bucal=d.public_id,
                        descripcion=d.descripcion,
                        codigos=[_codigo(c) for c in d.codigos],
                        codificado=bool(d.codigos),
                    )
                    for d in bucales.get(a.id_atencion, [])
                ],
                tratamientos=[TratamientoOut(id_tratamiento=t.id_tratamiento, nombre=t.nombre) for t in a.tratamientos],
                imagenes=imagenes.get(a.public_id, []),
            )
        )
    return items


def _resumen(p: Paciente) -> PacienteResumen:
    return PacienteResumen(
        id_paciente=p.public_id,
        codigo=codigo_paciente(p.id_paciente),
        nombre=p.nombre,
        documento_identidad=p.documento_identidad,
    )


def listar(db: Session, *, page: int, page_size: int, cod_4: str | None, id_paciente: UUID | None, **filtros):
    cod = normalizar_codigo(cod_4) if cod_4 else None
    interno = None
    if id_paciente is not None:
        p = paciente_repo.obtener(db, id_paciente)
        if p is None:
            return Page(items=[], total=0, page=page, page_size=page_size)
        interno = p.id_paciente
    filas, total = atencion_repo.listar(
        db, page=page, page_size=page_size, cod_4=cod, id_paciente_interno=interno, **filtros
    )
    ids = [a.id_atencion for a, _ in filas]
    hospitalarios = enfermedad_repo.hospitalarios(db, ids)
    bucales = enfermedad_repo.bucales(db, ids)
    imagenes = atencion_repo.conteo_imagenes(db, ids)
    items = []
    for a, p in filas:
        hosp = hospitalarios.get(a.id_atencion)
        items.append(
            AtencionListItem(
                id_atencion=a.public_id,
                codigo_atencion=codigo_atencion(a.id_atencion),
                fecha_atencion=a.fecha_atencion,
                hora_atencion=a.hora_atencion,
                paciente=_resumen(p),
                aseguradora=a.aseguradora.nombre if a.aseguradora else None,
                profesional=a.profesional.nombre if a.profesional else a.profesional_texto,
                diagnostico_hospitalario=(hosp.cod_4 or hosp.descripcion_original) if hosp else None,
                diagnosticos_bucales=[d.descripcion for d in bucales.get(a.id_atencion, [])],
                total_imagenes=imagenes.get(a.id_atencion, 0),
            )
        )
    return Page(items=items, total=total, page=page, page_size=page_size)


def obtener(db: Session, almacen: Almacenamiento, id_atencion: UUID) -> AtencionDetalle:
    fila = atencion_repo.obtener(db, id_atencion)
    if fila is None:
        raise NotFoundError("Atención no encontrada")
    a, p = fila
    imagenes: dict[UUID, list] = defaultdict(list)
    for f in imagen_repo.por_paciente(db, p.id_paciente):
        salida = imagen_service.a_salida(almacen, f)
        if salida.id_atencion == a.public_id:
            imagenes[a.public_id].append(salida)
    base = armar(db, [a], imagenes)[0]
    return AtencionDetalle(**base.model_dump(), paciente=_resumen(p))


def _activo(db: Session, modelo, id_: int | None, etiqueta: str) -> None:
    if id_ is None:
        return
    fila = catalogo_repo.obtener(db, modelo, id_)
    if fila is None or not fila.activo:
        raise DatosInvalidosError(f"{etiqueta} {id_} no existe o está inactivo")


def crear(db: Session, almacen: Almacenamiento, datos: AtencionCreate, *, auth_sub: str) -> AtencionDetalle:
    paciente = paciente_repo.obtener(db, datos.id_paciente)
    if paciente is None:
        raise NotFoundError("Paciente no encontrado")
    _activo(db, Aseguradora, datos.id_aseguradora, "Aseguradora")
    _activo(db, Profesional, datos.id_profesional, "Profesional")

    tratamientos = atencion_repo.tratamientos_por_ids(db, list(dict.fromkeys(datos.ids_tratamientos)))
    pedidos = set(datos.ids_tratamientos)
    if {t.id_tratamiento for t in tratamientos} != pedidos:
        raise DatosInvalidosError("Algún tratamiento no existe")
    if any(not t.activo for t in tratamientos):
        raise DatosInvalidosError("Algún tratamiento está inactivo")

    # Regla 2: hospitalario = cualquier código existente; bucal = código existente Y odontológico.
    dh = datos.diagnostico_hospitalario
    hosp_cod = normalizar_codigo(dh.cod_4) if dh and dh.cod_4 else None
    pedidos_cie = {c for d in datos.diagnosticos_bucales for c in d.codigos} | ({hosp_cod} if hosp_cod else set())
    existentes = atencion_repo.codigos_existentes(db, sorted(pedidos_cie))
    faltan = sorted(pedidos_cie - existentes.keys())
    if faltan:
        raise DatosInvalidosError("Códigos CIE-10 que no existen en el catálogo: " + ", ".join(faltan))
    no_odonto = sorted({c for d in datos.diagnosticos_bucales for c in d.codigos if not existentes[c].es_odontologico})
    if no_odonto:
        raise DatosInvalidosError(
            "Un diagnóstico bucal solo admite códigos odontológicos; no lo son: " + ", ".join(no_odonto)
        )

    # Profesional: el indicado; si no, el que está enlazado con el usuario que registra (auth_id = su "sub").
    id_prof, texto = datos.id_profesional, datos.profesional_texto
    if id_prof is None and not texto:
        enlazado = catalogo_repo.profesional_por_auth_id(db, auth_sub)
        id_prof = enlazado.id_profesional if enlazado and enlazado.activo else None

    atencion = Atencion(
        id_paciente=paciente.id_paciente,
        fecha_atencion=datos.fecha_atencion,
        hora_atencion=datos.hora_atencion,
        id_aseguradora=datos.id_aseguradora,
        ubicacion=datos.ubicacion,
        id_profesional=id_prof,
        profesional_texto=texto,
        plan_tratamiento=datos.plan_tratamiento,
        observaciones=datos.observaciones,
    )
    atencion.tratamientos = sorted(tratamientos, key=lambda t: t.nombre)
    try:
        atencion_repo.agregar(db, atencion)
        if datos.diagnostico_hospitalario:
            db.add(
                DiagnosticoHospitalario(
                    id_atencion=atencion.id_atencion,
                    descripcion_original=datos.diagnostico_hospitalario.descripcion_original,
                    cod_4=hosp_cod,
                )
            )
        for d in datos.diagnosticos_bucales:
            db.add(
                DiagnosticoBucal(
                    id_atencion=atencion.id_atencion,
                    descripcion=d.descripcion,
                    codigos=[existentes[c] for c in d.codigos],
                )
            )
        db.commit()
    except DBAPIError as exc:  # red de seguridad: el trigger de la base también protege la regla 2
        db.rollback()
        raise DatosInvalidosError("La base de datos rechazó la atención (revise los códigos CIE-10)") from exc
    return obtener(db, almacen, atencion.public_id)


__all__ = ["armar", "codigo_atencion", "crear", "listar", "obtener", "Tratamiento"]
