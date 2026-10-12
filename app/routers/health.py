"""Sondas de salud (sin autenticación, sin datos de pacientes). Carpeta: app/routers.

Soporta el despliegue (sección 6.6): /health para liveness, /health/ready para el smoke test de CD.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["Salud"])


@router.get("/health", summary="Liveness")
def health() -> dict:
    return {"status": "ok", "commit": get_settings().git_sha}


@router.get("/health/ready", summary="Readiness (verifica conexión a la base de datos)")
def ready(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Base de datos no disponible") from exc
    return {"status": "ready"}
