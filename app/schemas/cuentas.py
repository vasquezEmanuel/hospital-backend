"""Esquemas de la gestión de cuentas de profesionales. Carpeta: app/schemas.

La contraseña solo entra (crear / cambiar): nunca se guarda en nuestra base, ni se audita ni se devuelve.
"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings
from app.schemas.catalogos import ProfesionalAdminOut, ProfesionalCreate

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


class ProfesionalCrear(ProfesionalCreate):
    """Crear un profesional. Con `password` también se crea su cuenta (con `rol`); sin `password` solo la ficha
    (p. ej. un profesional histórico que no usa el sistema). `auth_id` enlaza una cuenta que ya existe: no se combina
    con `password`."""

    password: Contrasena | None = None
    rol: Rol = "odontologo"

    @field_validator("correo")
    @classmethod
    def _correo(cls, v: str) -> str:
        return v.lower()

    @model_validator(mode="after")
    def _exclusivos(self):
        if self.password and self.auth_id:
            raise ValueError("Envía `password` (crear la cuenta) o `auth_id` (enlazar una existente), no ambos")
        return self


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
