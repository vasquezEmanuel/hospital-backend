"""Esquemas de imagen_clinica. Carpeta: app/schemas — Sprint 3 (pantalla 'Imágenes clínicas')."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ImagenOut(BaseModel):
    id_imagen: int
    id_paciente: int
    paciente_nombre: str
    id_atencion: int | None = None
    fecha_atencion: date | None = None
    id_diagnostico_bucal: int | None = None
    diagnostico: str | None = Field(None, description="Diagnóstico bucal asociado (texto de la fuente)")
    nombre_archivo: str
    fecha_carga: datetime
    url: str = Field(description="Enlace temporal firmado: caduca en url_expira_en_segundos (regla 7)")
    url_expira_en_segundos: int
    activo: bool
