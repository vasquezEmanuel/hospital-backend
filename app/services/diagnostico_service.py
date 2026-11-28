"""Alta, edición y baja de diagnósticos de una atención ya registrada. Carpeta: app/services — bajas y ediciones.

Reglas 2 (bucal: solo códigos odontológicos; hospitalización: cualquiera), 3 (0+ diagnósticos de cada tipo; v1.7) y
5 (los diagnósticos se inactivan, nunca se borran). Cambiar los códigos de un diagnóstico reemplaza sus vínculos N:M;
la auditoría deja el rastro del cambio.
"""

from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import Atencion, DiagnosticoBucal, DiagnosticoHospitalario
from app.repositories import atencion_repo
from app.schemas.atencion import (
    AtencionDetalle,
    DiagnosticoBucalIn,
    DiagnosticoBucalUpdate,
    DiagnosticoHospitalarioIn,
    DiagnosticoHospitalarioUpdate,
)
from app.services import atencion_service
from app.services.almacenamiento import Almacenamiento
from app.services.errors import DatosInvalidosError, NotFoundError


def _atencion(db: Session, id_atencion: UUID):
    fila = atencion_repo.obtener(db, id_atencion)
    if fila is None:
        raise NotFoundError("Atención no encontrada")
    return fila[0]


def paciente_de_atencion(db: Session, id_atencion: UUID) -> UUID | None:
    return atencion_service.paciente_de(db, id_atencion)


def paciente_de_bucal(db: Session, id_dx: UUID) -> UUID | None:
    """Paciente (UUID) de un diagnóstico bucal, para auditar antes de modificarlo; None si no existe/inactivo."""
    d = atencion_repo.bucal_por_public_id(db, id_dx)
    return atencion_repo.paciente_publico_de_atencion(db, d.id_atencion) if d else None


def _confirmar(db: Session) -> None:
    try:
        db.commit()
    except DBAPIError as exc:  # el trigger de la base también protege la regla 2
        db.rollback()
        raise DatosInvalidosError("La base de datos rechazó el cambio (revise los códigos CIE-10)") from exc


def agregar_bucal(
    db: Session, almacen: Almacenamiento, id_atencion: UUID, datos: DiagnosticoBucalIn
) -> AtencionDetalle:
    atencion = _atencion(db, id_atencion)
    existentes = atencion_service.validar_codigos(db, datos.codigos)
    db.add(
        DiagnosticoBucal(
            id_atencion=atencion.id_atencion,
            descripcion=datos.descripcion,
            codigos=[existentes[c] for c in datos.codigos],
        )
    )
    _confirmar(db)
    return atencion_service.obtener(db, almacen, id_atencion)


def modificar_bucal(
    db: Session, almacen: Almacenamiento, id_dx: UUID, datos: DiagnosticoBucalUpdate
) -> AtencionDetalle:
    d = atencion_repo.bucal_por_public_id(db, id_dx)
    if d is None:
        raise NotFoundError("Diagnóstico bucal no encontrado")
    if datos.codigos is not None:
        existentes = atencion_service.validar_codigos(db, datos.codigos)
        d.codigos = [existentes[c] for c in datos.codigos]
    if datos.descripcion is not None:
        d.descripcion = datos.descripcion
    _confirmar(db)
    return atencion_service.obtener(db, almacen, _public_de_atencion(db, d.id_atencion))


def _public_de_atencion(db: Session, id_atencion: int) -> UUID:
    return db.get(Atencion, id_atencion).public_id


def inactivar_bucal(db: Session, id_dx: UUID) -> None:
    d = atencion_repo.bucal_por_public_id(db, id_dx)
    if d is None:
        raise NotFoundError("Diagnóstico bucal no encontrado")
    d.activo = False
    db.commit()


def paciente_de_hospitalario(db: Session, id_dx: UUID) -> UUID | None:
    """Paciente (UUID) de un diagnóstico de hospitalización, para auditar antes de modificarlo."""
    d = atencion_repo.hospitalario_por_public_id(db, id_dx)
    return atencion_repo.paciente_publico_de_atencion(db, d.id_atencion) if d else None


def agregar_hospitalario(
    db: Session, almacen: Almacenamiento, id_atencion: UUID, datos: DiagnosticoHospitalarioIn
) -> AtencionDetalle:
    atencion = _atencion(db, id_atencion)
    existentes = atencion_service.validar_codigos(db, [], datos.codigos)  # regla 2: cualquier código, pero existente
    db.add(
        DiagnosticoHospitalario(
            id_atencion=atencion.id_atencion,
            descripcion_original=datos.descripcion,
            codigos=[existentes[c] for c in sorted(datos.codigos)],
        )
    )
    _confirmar(db)
    return atencion_service.obtener(db, almacen, id_atencion)


def modificar_hospitalario(
    db: Session, almacen: Almacenamiento, id_dx: UUID, datos: DiagnosticoHospitalarioUpdate
) -> AtencionDetalle:
    d = atencion_repo.hospitalario_por_public_id(db, id_dx)
    if d is None:
        raise NotFoundError("Diagnóstico de hospitalización no encontrado")
    if datos.codigos is not None:
        existentes = atencion_service.validar_codigos(db, [], datos.codigos)
        d.codigos = [existentes[c] for c in sorted(datos.codigos)]
    if datos.descripcion is not None:
        d.descripcion_original = datos.descripcion
    _confirmar(db)
    return atencion_service.obtener(db, almacen, _public_de_atencion(db, d.id_atencion))


def inactivar_hospitalario(db: Session, id_dx: UUID) -> None:
    d = atencion_repo.hospitalario_por_public_id(db, id_dx)
    if d is None:
        raise NotFoundError("Diagnóstico de hospitalización no encontrado")
    d.activo = False
    db.commit()
