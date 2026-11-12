"""Recurso /imagenes. Carpeta: app/routers — Sprint 3.

Pantalla 'Imágenes clínicas' (listado con filtros paciente / diagnóstico / fecha, 'Subir imagen', 'Ver imagen').
Reglas: 4 (siempre asociada al paciente), 5 (se inactiva, no se borra), 6 (todo acceso o cambio queda en auditoría
antes de ejecutarse) y 7 (solo enlaces firmados temporales).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.common import ErrorResponse, Page
from app.schemas.imagen import ImagenOut
from app.schemas.importacion import LoteImagenesOut, ResultadoImagenLote
from app.services import auditoria_service, imagen_service
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
    id_paciente: UUID | None = Query(None, description="Filtro 'Paciente' (identificador público)"),
    id_atencion: UUID | None = Query(None, description="Solo las imágenes de esa atención (identificador público)"),
    q: str | None = Query(None, description="Paciente por nombre o documento", max_length=100),
    diagnostico: str | None = Query(None, description="Filtro 'Diagnóstico': código CIE-10 (cod_4)", max_length=10),
    fecha_desde: date | None = Query(None, description="Cargadas desde esta fecha (filtro 'Fecha')"),
    fecha_hasta: date | None = Query(None, description="Cargadas hasta esta fecha"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar(
        "consultar_imagenes",
        "imagen",
        id_paciente=id_paciente,
        detalle=auditoria_service.filtros_usados(
            id_paciente=id_paciente,
            id_atencion=id_atencion,
            q=q,
            diagnostico=diagnostico,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        ),
    )
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
    id_paciente: UUID = Form(
        ..., description="Obligatorio: toda imagen pertenece a un paciente (identificador público)"
    ),
    id_atencion: UUID | None = Form(None, description="Opcional: atención en la que se tomó"),
    id_diagnostico_bucal: UUID | None = Form(None, description="Opcional: diagnóstico bucal que ilustra"),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    settings: Settings = Depends(get_settings),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("subir_imagen", "imagen", id_paciente=id_paciente)
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


@router.post(
    "/lote",
    response_model=LoteImagenesOut,
    summary="Subir varias imágenes de un mismo paciente de una vez",
    description=(
        "Cada archivo se procesa por separado: si uno falla (formato, tamaño, duplicado) los demás se suben igual y el "
        "resultado indica el error de cada uno. Máximo de archivos por solicitud: MAX_IMPORT_IMAGES (50)."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "El paciente no existe"},
        413: {"model": ErrorResponse, "description": "Demasiados archivos en una solicitud"},
        422: {"model": ErrorResponse, "description": "Atención que no corresponde al paciente"},
    },
)
def subir_imagenes_lote(
    archivos: list[UploadFile] = File(..., description="Las imágenes (JPEG, PNG o WebP)"),
    id_paciente: UUID = Form(..., description="Paciente dueño de todas las imágenes"),
    id_atencion: UUID | None = Form(None, description="Opcional: atención en la que se tomaron"),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    settings: Settings = Depends(get_settings),
    auditor: Auditor = Depends(get_auditor),
):
    if len(archivos) > settings.max_import_images:
        raise HTTPException(413, f"Máximo {settings.max_import_images} imágenes por solicitud")
    auditor.registrar("subir_imagenes_lote", "imagen", id_paciente=id_paciente, detalle={"cantidad": len(archivos)})
    resultados: list[ResultadoImagenLote] = []
    for archivo in archivos:
        contenido = archivo.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        try:
            imagen = imagen_service.subir(
                db,
                almacen,
                id_paciente=id_paciente,
                id_atencion=id_atencion,
                id_diagnostico_bucal=None,
                nombre_original=archivo.filename,
                contenido=contenido,
            )
            resultados.append(ResultadoImagenLote(nombre_archivo=archivo.filename, imagen=imagen))
        except NotFoundError as exc:  # el paciente no existe: no tiene sentido seguir con el resto
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except DatosInvalidosError as exc:
            if "atención" in str(exc).lower() or "diagnóstico" in str(exc).lower():
                raise HTTPException(422, str(exc)) from exc
            resultados.append(ResultadoImagenLote(nombre_archivo=archivo.filename, error=str(exc)))
        except (ConflictError, ArchivoMuyGrandeError, ArchivoNoPermitidoError) as exc:
            resultados.append(ResultadoImagenLote(nombre_archivo=archivo.filename, error=str(exc)))
    subidas = sum(r.imagen is not None for r in resultados)
    return LoteImagenesOut(
        total=len(resultados), subidas=subidas, fallidas=len(resultados) - subidas, resultados=resultados
    )


@router.get(
    "/{id_imagen}",
    response_model=ImagenOut,
    summary="Ver una imagen: devuelve su enlace temporal firmado",
    responses={404: {"model": ErrorResponse}},
)
def obtener_imagen(
    id_imagen: UUID,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("consultar_imagen", "imagen", id_imagen=id_imagen)
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
def inactivar_imagen(id_imagen: UUID, db: Session = Depends(get_db), auditor: Auditor = Depends(get_auditor)):
    auditor.registrar("inactivar_imagen", "imagen", id_imagen=id_imagen)
    try:
        imagen_service.inactivar(db, id_imagen)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
