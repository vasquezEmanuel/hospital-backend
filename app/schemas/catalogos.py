"""Esquemas de los catálogos aseguradora, tratamiento y profesional. Carpeta: app/schemas — Sprint 7.

Aseguradoras y tratamientos los administra el administrador sin tocar código (sección 4 del prompt); se inactivan,
nunca se borran (regla 5). `profesional.auth_id` enlaza con el usuario del proveedor de identidad (su "sub").
"""

from pydantic import BaseModel, EmailStr, Field, field_validator


def _limpiar(v: str) -> str:
    return " ".join(v.split())


class CatalogoOut(BaseModel):
    id: int
    nombre: str
    activo: bool


class CatalogoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150, examples=["SURA"])

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _limpiar(v)


class CatalogoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return _limpiar(v) if v else v


class ProfesionalOut(BaseModel):
    id_profesional: int
    nombre: str
    especializacion: str | None = None
    activo: bool


class ProfesionalAdminOut(ProfesionalOut):
    identificacion: str
    correo: str
    auth_id: str | None = None


class ProfesionalCreate(BaseModel):
    nombre: str = Field(min_length=3, max_length=150)
    identificacion: str = Field(min_length=4, max_length=20)
    correo: EmailStr
    especializacion: str | None = Field(default=None, max_length=150)
    auth_id: str | None = Field(
        default=None,
        max_length=255,
        description="Id del usuario en Supabase Auth (Authentication > Users)",
    )

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _limpiar(v)


class ProfesionalUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=3, max_length=150)
    correo: EmailStr | None = None
    especializacion: str | None = Field(default=None, max_length=150)
    auth_id: str | None = Field(default=None, max_length=255)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return _limpiar(v) if v else v
