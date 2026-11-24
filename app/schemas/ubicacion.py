"""Esquemas de los catálogos de ubicación (departamento y municipio, códigos DANE)."""

from pydantic import BaseModel, Field


class DepartamentoOut(BaseModel):
    codigo: str = Field(examples=["76"], description="Código DANE de 2 dígitos")
    nombre: str = Field(examples=["Valle del Cauca"])


class MunicipioOut(BaseModel):
    codigo: str = Field(examples=["76001"], description="Código DANE de 5 dígitos (los 2 primeros son el departamento)")
    nombre: str = Field(examples=["Santiago de Cali"])
    codigo_departamento: str = Field(examples=["76"])
    departamento: str = Field(examples=["Valle del Cauca"])
