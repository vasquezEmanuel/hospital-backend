"""Esquemas de imagen_clinica. Carpeta: app/schemas — Sprint 3 (pantalla 'Imágenes clínicas')."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ImagenOut(BaseModel):
    id_imagen: UUID
    id_paciente: UUID
    paciente_nombre: str
    id_atencion: UUID | None = None
    fecha_atencion: date | None = None
    id_diagnostico_bucal: UUID | None = None
    diagnostico: str | None = Field(None, description="Diagnóstico bucal asociado (texto de la fuente)")
    nombre_archivo: str
    fecha_carga: datetime
    url: str = Field(description="Enlace temporal firmado: caduca en url_expira_en_segundos (regla 7)")
    url_expira_en_segundos: int
    activo: bool


class ImagenUpdate(BaseModel):
    """PATCH de una imagen: reasignar la atención y/o el diagnóstico bucal. `null` desvincula (la imagen sigue
    siendo del paciente, regla 4). Un diagnóstico implica su atención. Si cambias solo la atención, el diagnóstico
    anterior se desvincula."""

    id_atencion: UUID | None = None
    id_diagnostico_bucal: UUID | None = None

    @model_validator(mode="after")
    def _algo_que_cambiar(self) -> "ImagenUpdate":
        if not self.model_fields_set:
            raise ValueError("Envía id_atencion y/o id_diagnostico_bucal")
        return self
