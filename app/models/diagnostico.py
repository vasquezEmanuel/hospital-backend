"""Entidades diagnostico_hospitalario, diagnostico_bucal y su tabla puente N:M con cie10 (schema.sql).

Reglas 2 y 3: el diagnóstico bucal solo se vincula a códigos odontológicos (lo exige un trigger en la base);
una atención tiene a lo sumo un diagnóstico de hospitalización (UNIQUE sobre id_atencion). El texto original de la
fuente se conserva siempre; el vínculo con CIE-10 puede faltar (diagnóstico pendiente de codificar).
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Table, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.cie10 import Cie10

cie10_x_diagnostico_bucal = Table(
    "cie10_x_diagnostico_bucal",
    Base.metadata,
    Column("cod_4", ForeignKey("cie10.cod_4"), primary_key=True),
    Column("id_diagnostico_bucal", ForeignKey("diagnostico_bucal.id_diagnostico_bucal"), primary_key=True),
)


class DiagnosticoHospitalario(Base):
    __tablename__ = "diagnostico_hospitalario"

    id_diagnostico_hosp: Mapped[int] = mapped_column(primary_key=True)
    id_atencion: Mapped[int] = mapped_column(ForeignKey("atencion.id_atencion"), unique=True)
    descripcion_original: Mapped[str] = mapped_column(Text)
    cod_4: Mapped[str | None] = mapped_column(ForeignKey("cie10.cod_4"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    cie10: Mapped[Cie10 | None] = relationship()


class DiagnosticoBucal(Base):
    __tablename__ = "diagnostico_bucal"

    id_diagnostico_bucal: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()"), unique=True
    )  # lo que expone la API (v1.5)
    id_atencion: Mapped[int] = mapped_column(ForeignKey("atencion.id_atencion"))
    descripcion: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    codigos: Mapped[list[Cie10]] = relationship(secondary=cie10_x_diagnostico_bucal, order_by=Cie10.cod_4)
