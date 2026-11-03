"""Recurso /enfermedades. Carpeta: app/routers — Sprint 4 (búsqueda integrada: enfermedad -> pacientes).

Pantalla 'Diagnósticos' (buscar un código CIE-10 y ver los pacientes relacionados con sus imágenes). Regla 6: cada
paciente que aparece en la respuesta queda registrado en auditoría antes de entregar el resultado.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.common import ErrorResponse
from app.schemas.enfermedad import Ambito, PacientesPorEnfermedadOut
from app.services import enfermedad_service
from app.services.almacenamiento import Almacenamiento, get_almacenamiento
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/enfermedades",
    tags=["Enfermedades"],
    dependencies=[Depends(require_clinical_staff)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get(
    "/{cod_4}/pacientes",
    response_model=PacientesPorEnfermedadOut,
    summary="Pacientes relacionados con un código CIE-10, con sus diagnósticos bucales e imágenes",
    responses={404: {"model": ErrorResponse, "description": "El código no existe en el catálogo CIE-10"}},
)
def pacientes_por_enfermedad(
    cod_4: str,
    en: Ambito = Query(
        Ambito.cualquiera,
        description="Dónde buscar el código: diagnóstico de hospitalización, diagnóstico bucal o cualquiera de los dos",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    max_imagenes: int = Query(
        3, ge=0, le=10, description="Imágenes recientes a incluir por fila ('Consultar imágenes')"
    ),
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
):
    try:
        resultado = enfermedad_service.buscar(
            db, almacen, cod_4, en, page=page, page_size=page_size, max_imagenes=max_imagenes
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    # Regla 6: se registra una consulta por cada paciente expuesto, ANTES de devolver el resultado.
    auditor.registrar(
        "buscar_pacientes_por_enfermedad",
        "paciente",
        ids_pacientes=[i.id_paciente for i in resultado.items] or None,
        detalle={"cod_4": resultado.codigo.cod_4, "en": en.value},
    )
    return resultado
