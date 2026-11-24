"""Catálogos de ubicación (schema.sql v1.6): departamento y municipio, códigos DIVIPOLA del DANE."""

from sqlalchemy import CHAR, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Departamento(Base):
    __tablename__ = "departamento"

    codigo: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)


class Municipio(Base):
    __tablename__ = "municipio"

    codigo: Mapped[str] = mapped_column(CHAR(5), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    codigo_departamento: Mapped[str] = mapped_column(CHAR(2), ForeignKey("departamento.codigo"))
