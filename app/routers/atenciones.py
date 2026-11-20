"""Recurso /atenciones. Carpeta: app/routers — Sprint 7.

Pantallas 'Atenciones', 'Nueva atención' y 'Detalle de atención'. Regla 6: toda consulta o alta queda en auditoría
antes de entregar o modificar el dato. Rol: odontólogo o administrador.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.atencion import (
    AtencionCreate,
    AtencionDetalle,
    AtencionListItem,
    AtencionUpdate,
    DiagnosticoBucalIn,
    DiagnosticoHospitalarioIn,
)
from app.schemas.common import ErrorResponse, Page
from app.services import atencion_service, auditoria_service, diagnostico_service
from app.services.almacenamiento import Almacenamiento, get_almacenamiento
from app.services.errors import DatosInvalidosError, NotFoundError

router = APIRouter(
    prefix="/atenciones",
    tags=["Atenciones"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


@router.get("", response_model=Page[AtencionListItem], summary="Listar y buscar atenciones")
def listar_atenciones(
    q: str | None = Query(None, description="Nombre o documento del paciente", max_length=100),
    cod_4: str | None = Query(
        None, description="Atenciones con este código CIE-10 (hospitalario o bucal)", max_length=10
    ),
    id_paciente: UUID | None = Query(None, description="Solo las atenciones de este paciente"),
    id_aseguradora: int | None = Query(None),
    fecha_desde: date | None = Query(None),
    fecha_hasta: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    resultado = atencion_service.listar(
        db,
        page=page,
        page_size=page_size,
        q=q,
        cod_4=cod_4,
        id_paciente=id_paciente,
        id_aseguradora=id_aseguradora,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    # Regla 6: un evento por paciente expuesto, antes de devolver.
    auditor.registrar(
        "consultar_atenciones",
        "atencion",
        ids_pacientes=[i.paciente.id_paciente for i in resultado.items] or None,
        detalle=auditoria_service.filtros_usados(
            q=q,
            cod_4=cod_4,
            id_paciente=id_paciente,
            id_aseguradora=id_aseguradora,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        ),
    )
    return resultado


@router.post(
    "",
    response_model=AtencionDetalle,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una atención con sus diagnósticos y tratamientos",
    responses={
        404: {"model": ErrorResponse, "description": "El paciente no existe"},
        422: {"model": ErrorResponse, "description": "Catálogo inexistente/inactivo o código CIE-10 no odontológico"},
    },
)
def crear_atencion(
    datos: AtencionCreate,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    user: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar("crear_atencion", "atencion", id_paciente=datos.id_paciente)
    try:
        return atencion_service.crear(db, almacen, datos, auth_sub=user.sub)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get(
    "/{id_atencion}",
    response_model=AtencionDetalle,
    summary="Detalle de una atención",
    responses={404: {"model": ErrorResponse}},
)
def detalle_atencion(
    id_atencion: UUID,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    try:
        detalle = atencion_service.obtener(db, almacen, id_atencion)
    except NotFoundError as exc:
        auditor.registrar("consultar_atencion", "atencion", detalle={"id_atencion": str(id_atencion)})
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    auditor.registrar(
        "consultar_atencion",
        "atencion",
        id_paciente=detalle.paciente.id_paciente,
        detalle={"id_atencion": str(id_atencion)},
    )
    return detalle


@router.patch(
    "/{id_atencion}",
    response_model=AtencionDetalle,
    summary="Modificar una atención (plan de tratamiento, tratamientos, observaciones, aseguradora...)",
    description=(
        "Solo se modifican los campos enviados; `null` borra un dato opcional. `ids_tratamientos` reemplaza la lista "
        "completa (envía `[]` para quitarla). El paciente y los diagnósticos no se editan por aquí."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "La atención no existe"},
        422: {"model": ErrorResponse, "description": "Catálogo inexistente/inactivo o fecha inválida"},
    },
)
def modificar_atencion(
    id_atencion: UUID,
    datos: AtencionUpdate,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    # Regla 6: se audita antes de modificar, con los NOMBRES de los campos (nunca los valores clínicos).
    auditor.registrar(
        "editar_atencion",
        "atencion",
        id_paciente=atencion_service.paciente_de(db, id_atencion),
        detalle={"id_atencion": str(id_atencion), "campos": sorted(datos.model_fields_set)},
    )
    try:
        return atencion_service.actualizar(db, almacen, id_atencion, datos)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


_DX = {
    404: {"model": ErrorResponse, "description": "La atención no existe"},
    422: {"model": ErrorResponse, "description": "Código CIE-10 inexistente o (en bucales) no odontológico"},
}


def _traducir(exc: Exception) -> HTTPException:
    codigo = status.HTTP_404_NOT_FOUND if isinstance(exc, NotFoundError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(codigo, str(exc))


@router.post(
    "/{id_atencion}/diagnosticos-bucales",
    response_model=AtencionDetalle,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un diagnóstico bucal a una atención ya registrada; devuelve la atención completa",
    responses=_DX,
)
def agregar_diagnostico_bucal(
    id_atencion: UUID,
    datos: DiagnosticoBucalIn,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "agregar_diagnostico_bucal",
        "diagnostico_bucal",
        id_paciente=diagnostico_service.paciente_de_atencion(db, id_atencion),
        detalle={"id_atencion": str(id_atencion)},
    )
    try:
        return diagnostico_service.agregar_bucal(db, almacen, id_atencion, datos)
    except (NotFoundError, DatosInvalidosError) as exc:
        raise _traducir(exc) from exc


@router.put(
    "/{id_atencion}/diagnostico-hospitalario",
    response_model=AtencionDetalle,
    summary="Crear o reemplazar el diagnóstico de hospitalización (uno por atención)",
    responses=_DX,
)
def guardar_diagnostico_hospitalario(
    id_atencion: UUID,
    datos: DiagnosticoHospitalarioIn,
    db: Session = Depends(get_db),
    almacen: Almacenamiento = Depends(get_almacenamiento),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "guardar_diagnostico_hospitalario",
        "diagnostico_hospitalario",
        id_paciente=diagnostico_service.paciente_de_atencion(db, id_atencion),
        detalle={"id_atencion": str(id_atencion)},
    )
    try:
        return diagnostico_service.guardar_hospitalario(db, almacen, id_atencion, datos)
    except (NotFoundError, DatosInvalidosError) as exc:
        raise _traducir(exc) from exc


@router.delete(
    "/{id_atencion}/diagnostico-hospitalario",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja el diagnóstico de hospitalización (borrado lógico)",
    responses={404: {"model": ErrorResponse, "description": "La atención no existe o no tiene diagnóstico"}},
)
def inactivar_diagnostico_hospitalario(
    id_atencion: UUID,
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "inactivar_diagnostico_hospitalario",
        "diagnostico_hospitalario",
        id_paciente=diagnostico_service.paciente_de_atencion(db, id_atencion),
        detalle={"id_atencion": str(id_atencion)},
    )
    try:
        diagnostico_service.inactivar_hospitalario(db, id_atencion)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
