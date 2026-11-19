"""Esquemas de la gestión de cuentas de profesionales. Carpeta: app/schemas.

La contraseña solo entra (crear / cambiar): nunca se guarda en nuestra base, ni se audita ni se devuelve.
"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.core.config import get_settings
from app.schemas.catalogos import ProfesionalAdminOut

Rol = Literal["odontologo", "administrador"]


def _contrasena_valida(v: str) -> str:
    minimo = get_settings().password_min_length
    if len(v) < minimo:
        raise ValueError(f"La contraseña debe tener al menos {minimo} caracteres")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("La contraseña debe combinar letras y números")
    if v != v.strip():
        raise ValueError("La contraseña no puede empezar ni terminar con espacios")
    return v


Contrasena = Annotated[str, Field(max_length=72), AfterValidator(_contrasena_valida)]


class CuentaCreate(BaseModel):
    nombre: str = Field(min_length=3, max_length=150, examples=["Dra. Ana Pérez"])
    identificacion: str = Field(min_length=4, max_length=20)
    correo: EmailStr
    especializacion: str | None = Field(default=None, max_length=150)
    password: Contrasena
    rol: Rol = "odontologo"

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("correo")
    @classmethod
    def _correo(cls, v: str) -> str:
        return v.lower()


class CuentaExistente(BaseModel):
    password: Contrasena
    rol: Rol = "odontologo"


class PasswordUpdate(BaseModel):
    password: Contrasena


class RolUpdate(BaseModel):
    rol: Rol


class ProfesionalGestionOut(ProfesionalAdminOut):
    """Fila de la pestaña 'Gestión de profesionales'."""

    tiene_cuenta: bool
    rol: str | None = Field(None, description="odontologo | administrador (leído del proveedor de identidad)")
    cuenta_bloqueada: bool | None = None
