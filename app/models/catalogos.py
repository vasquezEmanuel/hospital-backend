"""Entidades aseguradora y profesional (schema.sql). Necesarias como FK de atencion.

Regla: roles NO viven aquí; profesional.auth_id enlaza con el IdP (sección 4 del prompt).
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Aseguradora(Base):
    __tablename__ = "aseguradora"

    id_aseguradora: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Profesional(Base):
    __tablename__ = "profesional"

    id_profesional: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    identificacion: Mapped[str] = mapped_column(String(20), unique=True)
    correo: Mapped[str] = mapped_column(String(150), unique=True)
    especializacion: Mapped[str | None] = mapped_column(String(150))
    auth_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
