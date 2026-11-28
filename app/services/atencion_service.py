"""Atenciones. Carpeta: app/services — Sprint 7 (pantallas 'Atenciones', 'Nueva atención', 'Detalle de atención').

Reglas: 2 (códigos del diagnóstico bucal odontológicos; el de hospitalización, cualquiera), 3 (0+ diagnósticos
bucales y 0+ de hospitalización, v1.7), 5 (solo diagnósticos activos), 1 (la atención se asocia a un paciente
existente, por su UUID).
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
    AtencionUpdate,
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
                diagnosticos_hospitalarios=[
                    DiagnosticoHospitalarioOut(
                        id_diagnostico_hospitalario=d.public_id,
                        descripcion=d.descripcion_original,
                        codigos=[_codigo(c) for c in d.codigos],
                        codificado=bool(d.codigos),
                    )
                    for d in hospitalarios.get(a.id_atencion, [])
                ],
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
        items.append(
            AtencionListItem(
                id_atencion=a.public_id,
                codigo_atencion=codigo_atencion(a.id_atencion),
                fecha_atencion=a.fecha_atencion,
                hora_atencion=a.hora_atencion,
                paciente=_resumen(p),
                aseguradora=a.aseguradora.nombre if a.aseguradora else None,
                profesional=a.profesional.nombre if a.profesional else a.profesional_texto,
                diagnosticos_hospitalarios=[d.descripcion_original for d in hospitalarios.get(a.id_atencion, [])],
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


def validar_codigos(
    db: Session, codigos_bucales: list[str], codigos_hospitalarios: list[str] | None = None
) -> dict[str, Cie10]:
    """Regla 2: todos los códigos existen en el catálogo y los de diagnóstico bucal son odontológicos."""
    pedidos = set(codigos_bucales) | set(codigos_hospitalarios or [])
    existentes = atencion_repo.codigos_existentes(db, sorted(pedidos))
    faltan = sorted(pedidos - existentes.keys())
    if faltan:
        raise DatosInvalidosError("Códigos CIE-10 que no existen en el catálogo: " + ", ".join(faltan))
    no_odonto = sorted({c for c in codigos_bucales if not existentes[c].es_odontologico})
    if no_odonto:
        raise DatosInvalidosError(
            "Un diagnóstico bucal solo admite códigos odontológicos; no lo son: " + ", ".join(no_odonto)
        )
    return existentes


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
    existentes = validar_codigos(
        db,
        [c for d in datos.diagnosticos_bucales for c in d.codigos],
        [c for d in datos.diagnosticos_hospitalarios for c in d.codigos],
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
        for d in datos.diagnosticos_hospitalarios:
            db.add(
                DiagnosticoHospitalario(
                    id_atencion=atencion.id_atencion,
                    descripcion_original=d.descripcion,
                    codigos=[existentes[c] for c in d.codigos],
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


def paciente_de(db: Session, id_atencion: UUID) -> UUID | None:
    """UUID del paciente de una atención (para auditar antes de modificarla); None si la atención no existe."""
    fila = atencion_repo.obtener(db, id_atencion)
    return fila[1].public_id if fila else None


_COLUMNAS_EDITABLES = (
    "fecha_atencion",
    "hora_atencion",
    "id_aseguradora",
    "ubicacion",
    "id_profesional",
    "profesional_texto",
    "plan_tratamiento",
    "observaciones",
)


def actualizar(db: Session, almacen: Almacenamiento, id_atencion: UUID, datos: AtencionUpdate) -> AtencionDetalle:
    fila = atencion_repo.obtener(db, id_atencion)
    if fila is None:
        raise NotFoundError("Atención no encontrada")
    atencion, _ = fila
    enviados = datos.model_fields_set
    if "id_aseguradora" in enviados:
        _activo(db, Aseguradora, datos.id_aseguradora, "Aseguradora")
    if "id_profesional" in enviados:
        _activo(db, Profesional, datos.id_profesional, "Profesional")
    nuevos_tratamientos = None
    if "ids_tratamientos" in enviados:
        pedidos = set(datos.ids_tratamientos or [])
        nuevos_tratamientos = atencion_repo.tratamientos_por_ids(db, sorted(pedidos))
        if {t.id_tratamiento for t in nuevos_tratamientos} != pedidos:
            raise DatosInvalidosError("Algún tratamiento no existe")
        actuales = {t.id_tratamiento for t in atencion.tratamientos}
        if any(not t.activo and t.id_tratamiento not in actuales for t in nuevos_tratamientos):
            raise DatosInvalidosError("Algún tratamiento está inactivo")
    for campo in _COLUMNAS_EDITABLES:
        if campo in enviados:
            setattr(atencion, campo, getattr(datos, campo))
    if nuevos_tratamientos is not None:
        atencion.tratamientos = sorted(nuevos_tratamientos, key=lambda t: t.nombre)
    try:
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise DatosInvalidosError("La base de datos rechazó el cambio") from exc
    db.refresh(atencion)
    return obtener(db, almacen, id_atencion)


__all__ = [
    "actualizar",
    "armar",
    "codigo_atencion",
    "crear",
    "listar",
    "obtener",
    "paciente_de",
    "validar_codigos",
    "Tratamiento",
]
