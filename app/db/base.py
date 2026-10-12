"""Base declarativa. Carpeta: app/db. El esquema real lo crean schema.sql + Alembic, no el ORM."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
