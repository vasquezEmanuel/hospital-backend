"""Punto de entrada FastAPI. Carpeta: app/.

Swagger UI (/docs), ReDoc (/redoc) y openapi.json se generan solos desde los routers y Pydantic.
En producción se apagan con DOCS_ENABLED=false.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import (
    archivos,
    atenciones,
    auditoria,
    catalogos,
    cie10,
    enfermedades,
    expediente,
    health,
    imagenes,
    importaciones,
    pacientes,
)

DESCRIPCION = """
API del **Sistema de Gestión de Pacientes, Enfermedades e Imágenes Clínicas** — Hospital Alma Mater, Odontología.

Autenticación: `Authorization: Bearer <JWT del proveedor de identidad>`.
Roles requeridos: `odontologo` o `administrador`; la auditoría (`/auditoria`) es solo para `administrador`.
"""


def create_app() -> FastAPI:
    s = get_settings()
    if s.environment == "production" and (problemas := s.problemas_produccion()):
        raise RuntimeError("Configuración insegura para producción: " + "; ".join(problemas))
    app = FastAPI(
        title=s.app_name,
        version="0.1.0",
        description=DESCRIPCION,
        docs_url="/docs" if s.docs_enabled else None,
        redoc_url="/redoc" if s.docs_enabled else None,
        openapi_url="/openapi.json" if s.docs_enabled else None,
    )
    if s.cors_origin_list:  # el front (otro dominio) llama a la API con "Authorization: Bearer": sin cookies
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origin_list,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,  # el token va en la cabecera, no en cookies
            max_age=600,  # el navegador recuerda el permiso 10 min: menos peticiones de verificación (OPTIONS)
        )
    app.include_router(health.router)
    app.include_router(pacientes.router, prefix="/api/v1")
    app.include_router(expediente.router, prefix="/api/v1")
    app.include_router(imagenes.router, prefix="/api/v1")
    app.include_router(archivos.router, prefix="/api/v1")
    app.include_router(atenciones.router, prefix="/api/v1")
    app.include_router(catalogos.aseguradoras, prefix="/api/v1")
    app.include_router(catalogos.tratamientos, prefix="/api/v1")
    app.include_router(catalogos.profesionales, prefix="/api/v1")
    app.include_router(cie10.router, prefix="/api/v1")
    app.include_router(enfermedades.router, prefix="/api/v1")
    app.include_router(importaciones.router, prefix="/api/v1")
    app.include_router(importaciones.router, prefix="/api/v1")
    app.include_router(auditoria.router, prefix="/api/v1")
    return app


app = create_app()
