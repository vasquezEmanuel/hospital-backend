"""Esquemas del catálogo CIE-10. Pantalla 'Diagnósticos' del front."""

from pydantic import BaseModel, ConfigDict, Field


class Cie10Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cod_4: str = Field(examples=["K021"], description="Código CIE-10 de 4 caracteres (clave de toda relación)")
    descripcion_4: str = Field(examples=["Caries de la dentina"])
    cod_3: str | None = Field(default=None, examples=["K02"])
    descripcion_3: str | None = Field(default=None, examples=["Caries dental"])
    es_odontologico: bool
