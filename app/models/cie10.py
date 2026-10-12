"""Entidad cie10 (schema.sql). Clave de toda relación: cod_4. Fase 1 — catálogo CIE-10."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cie10(Base):
    __tablename__ = "cie10"

    cod_4: Mapped[str] = mapped_column(String(10), primary_key=True)
    cod_3: Mapped[str | None] = mapped_column(String(5))
    descripcion_3: Mapped[str | None] = mapped_column(Text)
    descripcion_4: Mapped[str] = mapped_column(Text)
    es_odontologico: Mapped[bool] = mapped_column(Boolean, default=False)
