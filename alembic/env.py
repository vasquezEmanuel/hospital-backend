"""Entorno de Alembic.

Las migraciones son SQL escrito a mano (no autogenerate): schema.sql es la fuente de verdad
e incluye funciones y triggers que autogenerate no maneja. scripts/check_schema_drift.py
verifica en CI que schema.sql y las migraciones produzcan el mismo esquema.
"""

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings

config = context.config


def run_migrations_online() -> None:
    engine = create_engine(get_settings().sqlalchemy_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Modo offline no soportado: ejecute las migraciones contra una base real.")
run_migrations_online()
