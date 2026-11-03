"""Entidad auditoria (schema.sql v1.4). Regla 6: toda consulta o modificación de datos de un paciente se registra.

La tabla es inmutable en la base de datos (triggers): la aplicación solo inserta y lee.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Auditoria(Base):
    __tablename__ = "auditoria"

    id_evento: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_profesional: Mapped[int | None] = mapped_column(ForeignKey("profesional.id_profesional"))
    accion: Mapped[str] = mapped_column(String(100))
    entidad_afectada: Mapped[str | None] = mapped_column(String(100))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    auth_sub: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(150))
    id_paciente: Mapped[int | None] = mapped_column()  # sin FK a propósito (ver schema.sql)
    detalle: Mapped[dict | None] = mapped_column(JSONB)
