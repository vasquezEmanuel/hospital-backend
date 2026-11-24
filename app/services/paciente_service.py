"""Reglas de negocio de paciente. Carpeta: app/services.

Regla 1: el documento de identidad identifica de forma única al paciente (409 si ya existe).
Auditoría de consultas/modificaciones (regla 6) se conecta en Sprint 4 vía middleware.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Paciente
from app.repositories import paciente_repo, ubicacion_repo
from app.schemas.common import Page
from app.schemas.paciente import PacienteCreate, PacienteListItem, PacienteOut, PacienteUpdate
from app.services.errors import ConflictError, DatosInvalidosError, NotFoundError


def codigo_paciente(id_paciente: int) -> str:
    return f"P-{id_paciente:03d}"


def _edad(nacimiento: date | None) -> int | None:
    if nacimiento is None:
        return None
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def a_salida(db: Session, p: Paciente) -> PacienteOut:
    total, ultima, aseguradora = paciente_repo.resumen_atenciones(db, p.id_paciente)
    ubicacion = ubicacion_repo.ubicacion_de(db, p.codigo_municipio)
    return PacienteOut(
        id_paciente=p.public_id,
        codigo=codigo_paciente(p.id_paciente),
        tipo_documento=p.tipo_documento,
        documento_identidad=p.documento_identidad,
        nombre=p.nombre,
        fecha_nacimiento=p.fecha_nacimiento,
        edad=_edad(p.fecha_nacimiento),
        sexo=p.sexo,
        telefono=p.telefono,
        correo=p.correo,
        ciudad=p.ciudad,
        codigo_municipio=p.codigo_municipio,
        municipio=ubicacion[0].nombre if ubicacion else None,
        codigo_departamento=ubicacion[1].codigo if ubicacion else None,
        departamento=ubicacion[1].nombre if ubicacion else None,
        aseguradora_actual=aseguradora,
        total_atenciones=total,
        ultima_atencion=ultima,
        creado_en=p.creado_en,
    )


def listar(db: Session, *, page: int, page_size: int, **filtros) -> Page[PacienteListItem]:
    filas, total = paciente_repo.listar(db, page=page, page_size=page_size, **filtros)
    items = [
        PacienteListItem(
            id_paciente=p.public_id,
            codigo=codigo_paciente(p.id_paciente),
            tipo_documento=p.tipo_documento,
            documento_identidad=p.documento_identidad,
            nombre=p.nombre,
            total_atenciones=n,
            ultima_atencion=ultima,
        )
        for p, n, ultima in filas
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


def obtener(db: Session, id_paciente: UUID) -> PacienteOut:
    p = paciente_repo.obtener(db, id_paciente)
    if p is None:
        raise NotFoundError("Paciente no encontrado")
    return a_salida(db, p)


def _resolver_ubicacion(db: Session, campos: dict) -> None:
    """Con un municipio del catálogo, `ciudad` toma su nombre (manda el municipio). Sin municipio, es texto libre.

    Quitar el municipio (null) sin enviar `ciudad` también deja `ciudad` vacía: no se conserva un nombre huérfano.
    """
    if "codigo_municipio" not in campos:
        return
    codigo = campos["codigo_municipio"]
    if codigo is None:
        campos.setdefault("ciudad", None)
        return
    municipio = ubicacion_repo.municipio(db, codigo)
    if municipio is None:
        raise DatosInvalidosError(f"El municipio {codigo} no existe en el catálogo (consulte GET /municipios)")
    campos["ciudad"] = municipio.nombre


def crear(db: Session, datos: PacienteCreate) -> PacienteOut:
    if paciente_repo.existe_documento(db, datos.documento_identidad):
        raise ConflictError("Ya existe un paciente con ese documento de identidad")
    campos = datos.model_dump()
    _resolver_ubicacion(db, campos)
    try:
        p = paciente_repo.agregar(db, Paciente(**campos))
        db.commit()
    except IntegrityError as exc:  # carrera entre dos altas simultáneas
        db.rollback()
        raise ConflictError("Ya existe un paciente con ese documento de identidad") from exc
    return a_salida(db, p)


def actualizar(db: Session, id_paciente: UUID, datos: PacienteUpdate) -> PacienteOut:
    p = paciente_repo.obtener(db, id_paciente)
    if p is None:
        raise NotFoundError("Paciente no encontrado")
    campos = datos.model_dump(exclude_unset=True)
    nuevo_doc = campos.get("documento_identidad")
    if nuevo_doc is not None and nuevo_doc != p.documento_identidad and paciente_repo.existe_documento(db, nuevo_doc):
        raise ConflictError("Ya existe un paciente con ese documento de identidad")
    _resolver_ubicacion(db, campos)
    for campo, valor in campos.items():
        setattr(p, campo, valor)
    try:
        db.commit()
    except IntegrityError as exc:  # carrera con otra edición o alta del mismo documento
        db.rollback()
        raise ConflictError("Ya existe un paciente con ese documento de identidad") from exc
    db.refresh(p)
    return a_salida(db, p)
