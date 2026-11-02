"""Entrega de archivos del almacenamiento LOCAL. Carpeta: app/routers — Sprint 3.

Regla 7: el acceso a imágenes es siempre por enlaces temporales firmados. Aquí el enlace mismo es la credencial: no pide
sesión (el navegador lo usa en una etiqueta <img>) pero solo sirve mientras la firma sea válida y no haya vencido.
Con el almacenamiento S3 de producción esta ruta no se usa: el proveedor entrega sus propios enlaces prefirmados.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.services.almacenamiento import Almacenamiento, AlmacenamientoLocal, get_almacenamiento

router = APIRouter(prefix="/archivos", tags=["Archivos"])


@router.get("/{token}", summary="Descargar un archivo con enlace firmado (almacenamiento local)")
def servir_archivo(token: str, almacen: Almacenamiento = Depends(get_almacenamiento)):
    resuelto = almacen.resolver(token) if isinstance(almacen, AlmacenamientoLocal) else None
    if resuelto is None:  # firma inválida, enlace vencido o archivo inexistente: no se distingue a propósito
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enlace inválido o vencido")
    ruta, tipo = resuelto
    return FileResponse(
        ruta, media_type=tipo, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    )
