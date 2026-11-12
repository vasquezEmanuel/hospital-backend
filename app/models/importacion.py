"""Entidades importacion e importacion_fila (schema.sql v1.2). Sprint 8: pantalla 'Importar datos' y cola de revisión.

Lo que no coincide NO se descarta: queda en importacion_fila para revisión manual (Fase 3 del documento técnico).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Importacion(Base):
    __tablename__ = "importacion"

    id_importacion: Mapped[int] = mapped_column(primary_key=True)
    id_profesional: Mapped[int | None] = mapped_column(ForeignKey("profesional.id_profesional"))
    tipo: Mapped[str] = mapped_column(String(20))
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(20))
    total_registros: Mapped[int] = mapped_column(Integer)
    insertados: Mapped[int] = mapped_column(Integer)
    actualizados: Mapped[int] = mapped_column(Integer)
    rechazados: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportacionFila(Base):
    __tablename__ = "importacion_fila"

    id_fila: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_importacion: Mapped[int] = mapped_column(ForeignKey("importacion.id_importacion"))
    numero_fila: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(15))
    motivo: Mapped[str] = mapped_column(Text)
    datos: Mapped[dict] = mapped_column(JSONB)
    resuelto_por: Mapped[int | None] = mapped_column(ForeignKey("profesional.id_profesional"))
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
