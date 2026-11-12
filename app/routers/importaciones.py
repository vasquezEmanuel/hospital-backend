"""Recurso /importaciones. Carpeta: app/routers — Sprint 8 (pantalla 'Importar datos', Fase 3 del documento técnico).

Solo administrador (la matriz de roles final se valida con la Dra. Alvarez). Regla 6: toda importación y toda
consulta de la cola de revisión (que contiene datos de pacientes) queda en auditoría antes de ejecutarse.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser, require_admin
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.common import ErrorResponse, Page
from app.schemas.importacion import (
    FilaRevisionOut,
    FilaRevisionUpdate,
    ImportacionOut,
    ResultadoImportacion,
)
from app.services import importacion_service
from app.services.errors import (
    ArchivoMuyGrandeError,
    ArchivoNoPermitidoError,
    ConflictError,
    DatosInvalidosError,
    NotFoundError,
)

router = APIRouter(
    prefix="/importaciones",
    tags=["Importaciones"],
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

_ERRORES_ARCHIVO = {
    413: {"model": ErrorResponse, "description": "El archivo supera el tamaño máximo"},
    415: {"model": ErrorResponse, "description": "No es un Excel (.xls/.xlsx) o CSV válido"},
    422: {"model": ErrorResponse, "description": "El archivo no tiene la estructura esperada"},
}


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ArchivoMuyGrandeError):
        return HTTPException(413, str(exc))
    if isinstance(exc, ArchivoNoPermitidoError):
        return HTTPException(415, str(exc))
    return HTTPException(422, str(exc))


_TRADUCIBLES = (NotFoundError, ConflictError, ArchivoMuyGrandeError, ArchivoNoPermitidoError, DatosInvalidosError)


@router.post(
    "/catalogo-cie10",
    response_model=ResultadoImportacion,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar el catálogo CIE-10 (una sola vez)",
    description=(
        "Sube el Excel original del catálogo. Los códigos odontológicos se leen del subrayado o resaltado de las "
        "celdas (no sirve un CSV sin columna ES_ODONTOLOGICO). Solo funciona con el catálogo vacío."
    ),
    responses={409: {"model": ErrorResponse, "description": "El catálogo ya está cargado"}, **_ERRORES_ARCHIVO},
)
def importar_catalogo(
    archivo: UploadFile = File(..., description="Excel (.xls/.xlsx) del catálogo CIE-10"),
    solo_filas_marcadas: bool = Form(
        False, description="true = marcar solo las filas resaltadas, sin extender la marca a toda su categoría"
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auditor: Auditor = Depends(get_auditor),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar("importar_catalogo_cie10", "importacion")
    try:
        return importacion_service.importar_catalogo(
            db, archivo, auth_sub=user.sub, maximo_mb=settings.max_import_mb, solo_filas_marcadas=solo_filas_marcadas
        )
    except _TRADUCIBLES as exc:
        raise _http(exc) from exc


@router.post(
    "/atenciones",
    response_model=ResultadoImportacion,
    status_code=status.HTTP_201_CREATED,
    summary="Importar la hoja de atenciones (crea pacientes, atenciones y diagnósticos)",
    description=(
        "Requiere el catálogo CIE-10 cargado. Repetir el mismo archivo no duplica nada. Las filas que no coinciden "
        "no se descartan: quedan en la cola de revisión (GET /importaciones/{id}/filas)."
    ),
    responses=_ERRORES_ARCHIVO,
)
def importar_atenciones(
    archivo: UploadFile = File(..., description="Excel (.xls/.xlsx) o CSV de atenciones"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auditor: Auditor = Depends(get_auditor),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar("importar_atenciones", "importacion")
    try:
        return importacion_service.importar_atenciones(db, archivo, auth_sub=user.sub, maximo_mb=settings.max_import_mb)
    except _TRADUCIBLES as exc:
        raise _http(exc) from exc


@router.get("", response_model=Page[ImportacionOut], summary="Historial de importaciones")
def listar_importaciones(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
):
    auditor.registrar("consultar_importaciones", "importacion")
    return importacion_service.listar(db, page=page, page_size=page_size)


@router.get(
    "/{id_importacion}",
    response_model=ImportacionOut,
    summary="Resumen de una importación",
    responses={404: {"model": ErrorResponse}},
)
def obtener_importacion(id_importacion: int, db: Session = Depends(get_db), auditor: Auditor = Depends(get_auditor)):
    auditor.registrar("consultar_importacion", "importacion", detalle={"id_importacion": id_importacion})
    try:
        return importacion_service.obtener(db, id_importacion)
    except NotFoundError as exc:
        raise _http(exc) from exc


@router.get(
    "/{id_importacion}/filas",
    response_model=Page[FilaRevisionOut],
    summary="Cola de revisión: filas que no se pudieron cargar y por qué",
    responses={404: {"model": ErrorResponse}},
)
def filas_importacion(
    id_importacion: int,
    estado: str | None = Query(None, pattern="^(revision|rechazada|resuelta)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
):
    # Las filas traen datos de pacientes tal como venían en el archivo: la consulta se audita (regla 6).
    auditor.registrar("consultar_cola_importacion", "importacion", detalle={"id_importacion": id_importacion})
    try:
        return importacion_service.filas_en_revision(db, id_importacion, estado, page=page, page_size=page_size)
    except NotFoundError as exc:
        raise _http(exc) from exc


@router.patch(
    "/{id_importacion}/filas/{id_fila}",
    response_model=FilaRevisionOut,
    summary="Marcar una fila de la cola como resuelta (después de registrarla a mano)",
    responses={404: {"model": ErrorResponse}},
)
def resolver_fila(
    id_importacion: int,
    id_fila: int,
    datos: FilaRevisionUpdate,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    user: CurrentUser = Depends(require_admin),
):
    auditor.registrar(
        "resolver_fila_importacion", "importacion", detalle={"id_importacion": id_importacion, "id_fila": id_fila}
    )
    try:
        return importacion_service.resolver_fila(db, id_importacion, id_fila, auth_sub=user.sub)
    except NotFoundError as exc:
        raise _http(exc) from exc
