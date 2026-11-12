"""Esquemas del importador. Carpeta: app/schemas — Sprint 8 (pantalla Importar datos, Fase 3)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.imagen import ImagenOut


class ResultadoImportacion(BaseModel):
    id_importacion: int
    tipo: str
    archivo: str
    total: int = Field(description="Registros encontrados en el archivo")
    insertados: int
    actualizados: int
    omitidos: int = Field(description="Ya existían tal cual: no se duplican")
    rechazados: int = Field(description="Filas que fueron a la cola de revisión manual")
    pacientes_nuevos: int = 0
    aseguradoras_nuevas: int = 0
    odontologicos: int = Field(0, description="Catálogo: códigos marcados como odontológicos")
    bucales_sin_codigo: int = Field(0, description="Diagnósticos bucales guardados solo como texto")
    ejemplos: list[str] = Field(description="Primeros motivos de revisión")


class ImportacionOut(BaseModel):
    id_importacion: int
    tipo: str
    nombre_archivo: str
    estado: str
    total_registros: int
    insertados: int
    actualizados: int
    rechazados: int
    creado_en: datetime
    finalizado_en: datetime | None = None
    profesional: str | None = None


class FilaRevisionOut(BaseModel):
    id_fila: int
    numero_fila: int = Field(description="Número de fila en el archivo original")
    estado: str
    motivo: str
    datos: dict = Field(description="La fila original tal como vino del archivo")
    resuelto_en: datetime | None = None


class FilaRevisionUpdate(BaseModel):
    estado: str = Field(pattern="^resuelta$", description="Solo se permite marcarla como 'resuelta'")


class ResultadoImagenLote(BaseModel):
    nombre_archivo: str | None
    imagen: ImagenOut | None = None
    error: str | None = None


class LoteImagenesOut(BaseModel):
    total: int
    subidas: int
    fallidas: int
    resultados: list[ResultadoImagenLote]
