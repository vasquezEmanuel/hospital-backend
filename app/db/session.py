"""Engine y sesión de SQLAlchemy. Carpeta: app/db.

Pool pequeño (los pooladores gestionados tienen pocas conexiones) y prepare_threshold=None
para que funcione también detrás de PgBouncer/Supavisor en modo transacción.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return create_engine(
        s.sqlalchemy_url,
        pool_size=s.db_pool_size,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"prepare_threshold": None},
    )


def get_db() -> Iterator[Session]:
    """Una sesión por solicitud; commit lo decide el servicio, rollback ante error."""
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
