"""Entidad imagen_clinica (schema.sql v1.3). Reglas 4, 5 y 7.

Regla 4: toda imagen pertenece, como mínimo, a un paciente. Regla 5: borrado lógico (activo), nunca DELETE.
Regla 7: la base solo guarda la CLAVE del objeto; el acceso es siempre por enlace temporal firmado.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImagenClinica(Base):
    __tablename__ = "imagen_clinica"

    id_imagen: Mapped[int] = mapped_column(primary_key=True)
    id_paciente: Mapped[int] = mapped_column(ForeignKey("paciente.id_paciente"))
    id_atencion: Mapped[int | None] = mapped_column(ForeignKey("atencion.id_atencion"))
    id_diagnostico_bucal: Mapped[int | None] = mapped_column(ForeignKey("diagnostico_bucal.id_diagnostico_bucal"))
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    url_almacenamiento: Mapped[str] = mapped_column(Text, unique=True)  # clave del objeto en el almacenamiento
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadatos: Mapped[dict | None] = mapped_column("metadata", JSONB)  # "metadata" está reservado en SQLAlchemy
    checksum: Mapped[str | None] = mapped_column(String(64))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
