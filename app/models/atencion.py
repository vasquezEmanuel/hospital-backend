"""Entidad atencion (schema.sql v1.1). profesional_texto = respaldo de atenciones históricas."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Time, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.catalogos import Aseguradora, Profesional
from app.models.paciente import Paciente


class Atencion(Base):
    __tablename__ = "atencion"

    id_atencion: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()"), unique=True
    )  # lo que expone la API (v1.5)
    id_paciente: Mapped[int] = mapped_column(ForeignKey("paciente.id_paciente"))
    fecha_atencion: Mapped[date] = mapped_column(Date)
    hora_atencion: Mapped[time | None] = mapped_column(Time)
    id_aseguradora: Mapped[int | None] = mapped_column(ForeignKey("aseguradora.id_aseguradora"))
    ubicacion: Mapped[str | None] = mapped_column(String(150))
    id_profesional: Mapped[int | None] = mapped_column(ForeignKey("profesional.id_profesional"))
    profesional_texto: Mapped[str | None] = mapped_column(String(150))
    plan_tratamiento: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paciente: Mapped[Paciente] = relationship()
    aseguradora: Mapped[Aseguradora | None] = relationship()
    profesional: Mapped[Profesional | None] = relationship()
