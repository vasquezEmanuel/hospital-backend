"""Esquemas del registro de auditoría. Carpeta: app/schemas — Sprint 4 (GET /auditoria, solo administrador)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditoriaOut(BaseModel):
    id_evento: int
    fecha_hora: datetime
    accion: str = Field(description="Qué se hizo, p. ej. consultar_expediente, editar_paciente")
    entidad_afectada: str | None = None
    id_paciente: UUID | None = Field(
        None, description="Identificador público del paciente consultado o modificado, si aplica"
    )
    id_profesional: int | None = Field(None, description="Fila de profesional, si el usuario tiene una registrada")
    profesional_nombre: str | None = None
    auth_sub: str | None = Field(None, description="Identificador del usuario en el proveedor de identidad")
    email: str | None = None
    ip_origen: str | None = None
    detalle: dict | None = Field(None, description="Contexto sin datos clínicos (nombres de filtros, identificadores)")
