"""Sondas de salud (sin autenticación, sin datos de pacientes). Carpeta: app/routers.

Soporta el despliegue (sección 6.6): /health para liveness, /health/ready para el smoke test de CD.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["Salud"])
log = logging.getLogger("uvicorn.error")


@router.get("/health", summary="Liveness")
def health() -> dict:
    return {"status": "ok", "commit": get_settings().git_sha}


@router.get("/health/ready", summary="Readiness (verifica conexión a la base de datos)")
def ready(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        # La causa real (contraseña, usuario, red) queda en el log de Render; al cliente solo se le dice que no está lista.
        causa = str(getattr(exc, "orig", exc)).strip().splitlines()
        log.error(
            "Readiness: falló la conexión a la base de datos (%s): %s", type(exc).__name__, causa[0] if causa else ""
        )
        raise HTTPException(503, "Base de datos no disponible") from exc
    return {"status": "ready"}
