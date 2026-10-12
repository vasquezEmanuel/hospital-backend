"""Reglas de negocio de paciente. Carpeta: app/services.

Regla 1: el documento de identidad identifica de forma única al paciente (409 si ya existe).
Auditoría de consultas/modificaciones (regla 6) se conecta en Sprint 4 vía middleware.
"""

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Paciente
from app.repositories import paciente_repo
from app.schemas.common import Page
from app.schemas.paciente import PacienteCreate, PacienteListItem, PacienteOut, PacienteUpdate
from app.services.errors import ConflictError, NotFoundError


def codigo_paciente(id_paciente: int) -> str:
    return f"P-{id_paciente:03d}"


def _edad(nacimiento: date | None) -> int | None:
    if nacimiento is None:
        return None
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _a_salida(db: Session, p: Paciente) -> PacienteOut:
    total, ultima, aseguradora = paciente_repo.resumen_atenciones(db, p.id_paciente)
    return PacienteOut(
        id_paciente=p.id_paciente,
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
        aseguradora_actual=aseguradora,
        total_atenciones=total,
        ultima_atencion=ultima,
        creado_en=p.creado_en,
    )


def listar(db: Session, *, page: int, page_size: int, **filtros) -> Page[PacienteListItem]:
    filas, total = paciente_repo.listar(db, page=page, page_size=page_size, **filtros)
    items = [
        PacienteListItem(
            id_paciente=p.id_paciente,
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


def obtener(db: Session, id_paciente: int) -> PacienteOut:
    p = paciente_repo.obtener(db, id_paciente)
    if p is None:
        raise NotFoundError("Paciente no encontrado")
    return _a_salida(db, p)


def crear(db: Session, datos: PacienteCreate) -> PacienteOut:
    if paciente_repo.existe_documento(db, datos.documento_identidad):
        raise ConflictError("Ya existe un paciente con ese documento de identidad")
    try:
        p = paciente_repo.agregar(db, Paciente(**datos.model_dump()))
        db.commit()
    except IntegrityError as exc:  # carrera entre dos altas simultáneas
        db.rollback()
        raise ConflictError("Ya existe un paciente con ese documento de identidad") from exc
    return _a_salida(db, p)


def actualizar(db: Session, id_paciente: int, datos: PacienteUpdate) -> PacienteOut:
    p = paciente_repo.obtener(db, id_paciente)
    if p is None:
        raise NotFoundError("Paciente no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(p, campo, valor)
    db.commit()
    db.refresh(p)
    return _a_salida(db, p)
