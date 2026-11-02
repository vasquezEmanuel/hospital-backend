"""Recurso /imagenes. Carpeta: app/routers — Sprint 3.

Pantalla 'Imágenes clínicas' (listado con filtros paciente / diagnóstico / fecha, 'Subir imagen', 'Ver imagen').
Reglas: 4 (siempre asociada al paciente), 5 (se inactiva, no se borra) y 7 (solo enlaces firmados temporales).
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.schemas.common import ErrorResponse, Page
from app.schemas.imagen import ImagenOut
from app.services import imagen_service
from app.services.almacenamiento import Almacenamiento, get_almacenamiento
from app.services.errors import (
    ArchivoMuyGrandeError,
    ArchivoNoPermitidoError,
    ConflictError,
    DatosInvalidosError,
    NotFoundError,
)

router = APIRouter(
    prefix="/imagenes",
    tags=["Imágenes clínicas"],
    dependencies=[Depends(require_clinical_staff)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get("", response_model=Page[ImagenOut], summary="Listar imágenes clínicas activas")
def listar_imagenes(
    id_paciente: int | None = Query(None, ge=1, description="Filtro 'Paciente' (por identificador)"),
    id_atencion: int | None = Query(None, ge=1, description="Solo las imágenes de esa atención"),
    q: str | None = Query(None, description="Paciente por nombre o documento", max_length=100),
    diagnostico: str | None = Query(None, description="Filtro 'Diagnóstico': código CIE-10 (cod_4)", max_length=10),
    fecha_desde: date | None = Query(None, description="Cargadas desde esta fecha (filtro 'Fecha')"),
    fecha_hasta: date | None = Query(None, description="Cargadas hasta esta fecha"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
):
    return imagen_service.listar(
        db,
        almacen,
        id_paciente=id_paciente,
        id_atencion=id_atencion,
        q=q,
        cod_4=diagnostico,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ImagenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Subir una imagen clínica (JPEG, PNG o WebP)",
    responses={
        404: {"model": ErrorResponse, "description": "El paciente no existe"},
        409: {"model": ErrorResponse, "description": "La imagen ya estaba cargada para ese paciente"},
        413: {"model": ErrorResponse, "description": "El archivo supera el tamaño máximo"},
        415: {"model": ErrorResponse, "description": "El archivo no es una imagen JPEG, PNG o WebP"},
        422: {"model": ErrorResponse, "description": "Atención o diagnóstico que no corresponden al paciente"},
    },
)
def subir_imagen(
    archivo: UploadFile = File(..., description="La imagen"),
    id_paciente: int = Form(..., ge=1, description="Obligatorio: toda imagen pertenece a un paciente"),
    id_atencion: int | None = Form(None, ge=1, description="Opcional: atención en la que se tomó"),
    id_diagnostico_bucal: int | None = Form(None, ge=1, description="Opcional: diagnóstico bucal que ilustra"),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    settings: Settings = Depends(get_settings),
):
    # Se lee un byte más que el máximo para detectar el exceso sin cargar archivos enormes en memoria.
    contenido = archivo.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        return imagen_service.subir(
            db,
            almacen,
            id_paciente=id_paciente,
            id_atencion=id_atencion,
            id_diagnostico_bucal=id_diagnostico_bucal,
            nombre_original=archivo.filename,
            contenido=contenido,
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ArchivoMuyGrandeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except ArchivoNoPermitidoError as exc:
        raise HTTPException(415, str(exc)) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/{id_imagen}",
    response_model=ImagenOut,
    summary="Ver una imagen: devuelve su enlace temporal firmado",
    responses={404: {"model": ErrorResponse}},
)
def obtener_imagen(
    id_imagen: int,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
):
    try:
        return imagen_service.obtener(db, almacen, id_imagen)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.delete(
    "/{id_imagen}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Inactivar una imagen (borrado lógico: el archivo y su registro se conservan)",
    responses={404: {"model": ErrorResponse}},
)
def inactivar_imagen(id_imagen: int, db: Session = Depends(get_db)):
    try:
        imagen_service.inactivar(db, id_imagen)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
