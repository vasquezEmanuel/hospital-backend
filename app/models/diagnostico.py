"""Entidades diagnostico_hospitalario, diagnostico_bucal y sus tablas puente N:M con cie10 (schema.sql v1.7).

Regla 2: el diagnóstico bucal solo se vincula a códigos odontológicos (lo exige un trigger en la base); el de
hospitalización admite cualquier código. Regla 3: una atención tiene 0..N diagnósticos bucales y 0..N de
hospitalización (antes de v1.7 solo uno). El texto original de la fuente se conserva siempre; el vínculo con CIE-10
puede faltar (diagnóstico pendiente de codificar).
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


cie10_x_diagnostico_hospitalario = Table(
    "cie10_x_diagnostico_hospitalario",
    Base.metadata,
    Column("cod_4", ForeignKey("cie10.cod_4"), primary_key=True),
    Column("id_diagnostico_hosp", ForeignKey("diagnostico_hospitalario.id_diagnostico_hosp"), primary_key=True),
)


class DiagnosticoHospitalario(Base):
    __tablename__ = "diagnostico_hospitalario"

    id_diagnostico_hosp: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()"), unique=True
    )  # lo que expone la API (v1.7)
    id_atencion: Mapped[int] = mapped_column(ForeignKey("atencion.id_atencion"))
    descripcion_original: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    codigos: Mapped[list[Cie10]] = relationship(secondary=cie10_x_diagnostico_hospitalario, order_by=Cie10.cod_4)


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
