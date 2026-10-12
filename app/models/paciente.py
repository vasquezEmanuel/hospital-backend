"""Entidad paciente (schema.sql v1.1). Regla 1: el documento de identidad es único."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Paciente(Base):
    __tablename__ = "paciente"

    id_paciente: Mapped[int] = mapped_column(primary_key=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(3))
    documento_identidad: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    sexo: Mapped[str | None] = mapped_column(String(1))
    telefono: Mapped[str | None] = mapped_column(String(20))
    correo: Mapped[str | None] = mapped_column(String(150))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
