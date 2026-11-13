"""Esquemas de reportes e inicio. Carpeta: app/schemas — Sprint 9 (pantallas 'Reportes', 'Reporte' e 'Inicio')."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.atencion import AtencionListItem


class TipoReporte(BaseModel):
    tipo: str = Field(examples=["atenciones_por_aseguradora"])
    titulo: str


class FilaReporte(BaseModel):
    etiqueta: str
    etiqueta_secundaria: str | None = Field(None, description="Solo en la relación hospitalario ↔ bucal")
    cantidad: int
    porcentaje: float = Field(description="Sobre la suma de las filas del reporte (1 decimal)")


class TotalesReporte(BaseModel):
    pacientes: int = Field(description="Pacientes distintos con atenciones en el filtro")
    atenciones: int
    imagenes: int = Field(description="Imágenes activas asociadas a las atenciones del filtro")


class FiltrosReporte(BaseModel):
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    id_aseguradora: int | None = None
    cod_4: str | None = None
    id_profesional: int | None = None


class Reporte(BaseModel):
    tipo: str
    titulo: str
    generado_en: datetime
    filtros: FiltrosReporte
    totales: TotalesReporte
    columna_principal: str
    columna_secundaria: str | None = None
    filas: list[FilaReporte]
    hallazgo: str | None = Field(None, description="Frase destacada ('SURA concentra el 35,2 %...')")
    truncado: bool = Field(False, description="true si hay más filas que el límite y se muestran las primeras")


class ConteoInicio(BaseModel):
    etiqueta: str
    cantidad: int


class TotalesInicio(BaseModel):
    pacientes: int
    atenciones: int
    imagenes: int
    diagnosticos: int = Field(description="Códigos CIE-10 distintos usados en diagnósticos activos")


class ResumenInicio(BaseModel):
    totales: TotalesInicio
    atenciones_por_aseguradora: list[ConteoInicio]
    diagnosticos_bucales_frecuentes: list[ConteoInicio]
    ultimas_atenciones: list[AtencionListItem]
