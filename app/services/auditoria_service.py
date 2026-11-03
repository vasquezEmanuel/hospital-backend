"""Servicio de auditoría. Carpeta: app/services — Sprint 4.

Regla 6: toda consulta o modificación de datos de un paciente queda registrada (quién, qué, cuándo, desde dónde).
Principios:
- Se registra ANTES de entregar o modificar el dato, en una transacción propia confirmada. Si el registro falla,
  la operación falla: nunca se entregan datos de un paciente sin dejar rastro.
- El detalle no lleva datos clínicos ni valores de búsqueda: solo qué filtros se usaron y qué ids se tocaron.
- El usuario se identifica siempre por su "sub" del proveedor de identidad; si además tiene fila en `profesional`,
  se enlaza.
"""

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models import Auditoria
from app.repositories import auditoria_repo
from app.schemas.auditoria import AuditoriaOut
from app.schemas.common import Page


def filtros_usados(**filtros) -> dict:
    """{"filtros": ["q", "sexo"]}: nombres de los filtros aplicados, nunca sus valores (nombres, documentos)."""
    return {"filtros": sorted(k for k, v in filtros.items() if v not in (None, ""))}


def registrar(
    db: Session,
    user: CurrentUser,
    ip: str | None,
    accion: str,
    entidad: str | None,
    *,
    id_paciente: int | None = None,
    ids_pacientes: list[int] | None = None,
    id_imagen: int | None = None,
    detalle: dict | None = None,
) -> None:
    """Inserta uno o más eventos y confirma. ids_pacientes genera un evento por paciente (búsquedas que los exponen)."""
    detalle = dict(detalle or {})
    if id_imagen is not None:
        detalle["id_imagen"] = id_imagen
        if id_paciente is None:
            id_paciente = auditoria_repo.paciente_de_imagen(db, id_imagen)
    pacientes = list(dict.fromkeys(ids_pacientes)) if ids_pacientes else [id_paciente]
    id_profesional = auditoria_repo.profesional_por_auth_id(db, user.sub)
    auditoria_repo.agregar(
        db,
        [
            Auditoria(
                id_profesional=id_profesional,
                auth_sub=user.sub[:255],
                email=user.email[:150] if user.email else None,
                accion=accion,
                entidad_afectada=entidad,
                id_paciente=paciente,
                ip_origen=ip[:45] if ip else None,
                detalle=detalle or None,
            )
            for paciente in pacientes
        ],
    )
    db.commit()


def listar(db: Session, *, page: int, page_size: int, **filtros) -> Page[AuditoriaOut]:
    filas, total = auditoria_repo.listar(db, page=page, page_size=page_size, **filtros)
    items = [
        AuditoriaOut(
            id_evento=e.id_evento,
            fecha_hora=e.fecha_hora,
            accion=e.accion,
            entidad_afectada=e.entidad_afectada,
            id_paciente=e.id_paciente,
            id_profesional=e.id_profesional,
            profesional_nombre=nombre,
            auth_sub=e.auth_sub,
            email=e.email,
            ip_origen=e.ip_origen,
            detalle=e.detalle,
        )
        for e, nombre in filas
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
