"""Esquemas de paciente. Pantallas 'Pacientes', 'Nuevo paciente' y ficha del paciente."""

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TipoDocumento = Literal["CC", "TI", "RC", "CE", "PA", "PE", "PT"]
Sexo = Literal["M", "F", "O"]

_DOC_SEPARATORS = re.compile(r"[.\s-]")
_DOC_VALID = re.compile(r"^[A-Z0-9]{4,20}$")
_PHONE_VALID = re.compile(r"^[0-9+\s()-]{7,20}$")


def normalizar_documento(valor: str) -> str:
    """'1.025.847.210' -> '1025847210'. El front muestra puntos; la BD guarda solo el valor limpio."""
    limpio = _DOC_SEPARATORS.sub("", valor).upper()
    if not _DOC_VALID.match(limpio):
        raise ValueError("Documento inválido: use 4 a 20 caracteres alfanuméricos")
    return limpio


class _PacienteCampos(BaseModel):
    @field_validator("fecha_nacimiento", check_fields=False)
    @classmethod
    def _no_futura(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura")
        return v

    @field_validator("telefono", check_fields=False)
    @classmethod
    def _telefono(cls, v: str | None) -> str | None:
        if v is not None and not _PHONE_VALID.match(v):
            raise ValueError("Teléfono inválido")
        return v


_MUNICIPIO = r"^\d{5}$"
_DESC_MUNICIPIO = (
    "Código DANE del municipio (GET /municipios). El departamento se deduce de él y `ciudad` se completa con su "
    "nombre. Para quien vive fuera del catálogo, omitirlo y enviar solo `ciudad` como texto libre."
)


class PacienteCreate(_PacienteCampos):
    tipo_documento: TipoDocumento
    documento_identidad: str = Field(examples=["1.025.847.210"])
    nombre: str = Field(min_length=3, max_length=150, examples=["María Rodríguez"])
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    ciudad: str | None = Field(default=None, max_length=100)
    codigo_municipio: str | None = Field(
        default=None, pattern=_MUNICIPIO, description=_DESC_MUNICIPIO, examples=["76001"]
    )

    @field_validator("documento_identidad")
    @classmethod
    def _doc(cls, v: str) -> str:
        return normalizar_documento(v)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return " ".join(v.split())


class PacienteUpdate(_PacienteCampos):
    """'Editar información'. Solo cambia lo enviado. El documento puede corregirse, pero sigue siendo único (regla 1).

    `codigo_municipio: null` quita la ubicación (y `ciudad`, salvo que se envíe otro texto).
    """

    tipo_documento: TipoDocumento | None = None
    documento_identidad: str | None = Field(default=None, examples=["1.025.847.210"])
    nombre: str | None = Field(default=None, min_length=3, max_length=150)
    fecha_nacimiento: date | None = None
    sexo: Sexo | None = None
    telefono: str | None = None
    correo: EmailStr | None = None
    ciudad: str | None = Field(default=None, max_length=100)
    codigo_municipio: str | None = Field(
        default=None, pattern=_MUNICIPIO, description=_DESC_MUNICIPIO, examples=["76001"]
    )

    @field_validator("documento_identidad")
    @classmethod
    def _doc(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("El documento de identidad no puede quedar vacío")
        return normalizar_documento(v)


class PacienteListItem(BaseModel):
    """Fila de la tabla 'Pacientes'."""

    id_paciente: UUID = Field(description="Identificador público del paciente (el que se usa en las rutas)")
    codigo: str = Field(
        examples=["P-001"], description="ID visible en el front (solo para mostrar; no es un identificador de ruta)"
    )
    tipo_documento: str | None
    documento_identidad: str
    nombre: str
    total_atenciones: int
    ultima_atencion: date | None


class PacienteOut(BaseModel):
    """Ficha del paciente. Los conteos de diagnósticos e imágenes llegan en Sprint 3 (/expediente)."""

    model_config = ConfigDict(from_attributes=True)

    id_paciente: UUID
    codigo: str
    tipo_documento: str | None
    documento_identidad: str
    nombre: str
    fecha_nacimiento: date | None
    edad: int | None
    sexo: str | None
    telefono: str | None
    correo: str | None
    ciudad: str | None = Field(description="Nombre del municipio elegido, o el texto libre si no está en el catálogo")
    codigo_municipio: str | None = None
    municipio: str | None = None
    codigo_departamento: str | None = None
    departamento: str | None = None
    aseguradora_actual: str | None = Field(description="Aseguradora de la última atención")
    total_atenciones: int
    ultima_atencion: date | None
    creado_en: datetime
