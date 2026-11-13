"""Recursos /reportes e /inicio. Carpeta: app/routers — Sprint 9 (pantallas 'Reportes', 'Reporte' e 'Inicio').

Rol: odontólogo o administrador (matriz de roles final por validar con la Dra. Alvarez). Los reportes son agregados, sin
datos individuales; aun así cada generación queda en auditoría (regla 6, trazabilidad). 'Inicio' incluye las últimas
atenciones (con nombres de pacientes): se audita por paciente expuesto, como el listado de atenciones.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_clinical_staff
from app.db.session import get_db
from app.middleware.auditoria import Auditor, get_auditor
from app.schemas.common import ErrorResponse
from app.schemas.reporte import Reporte, ResumenInicio, TipoReporte
from app.services import auditoria_service, reporte_service
from app.services.errors import DatosInvalidosError, NotFoundError

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ERR = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}

router = APIRouter(prefix="/reportes", tags=["Reportes"], responses=_ERR)
inicio = APIRouter(prefix="/inicio", tags=["Inicio"], responses=_ERR)


def _filtros(
    fecha_desde: date | None = Query(None, description="Fecha inicial (incluida)"),
    fecha_hasta: date | None = Query(None, description="Fecha final (incluida)"),
    id_aseguradora: int | None = Query(None),
    cod_4: str | None = Query(None, description="Código CIE-10 (hospitalario o bucal)", max_length=10),
    id_profesional: int | None = Query(None),
) -> dict:
    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "id_aseguradora": id_aseguradora,
        "cod_4": cod_4,
        "id_profesional": id_profesional,
    }


def _generar(db: Session, tipo: str, filtros: dict) -> Reporte:
    try:
        return reporte_service.generar(db, tipo, **filtros)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosInvalidosError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/tipos", response_model=list[TipoReporte], summary="Los 8 tipos de reporte")
def listar_tipos(auditor: Auditor = Depends(get_auditor), _: CurrentUser = Depends(require_clinical_staff)):
    auditor.registrar("consultar_tipos_reporte", "reporte")
    return reporte_service.tipos()


@router.get(
    "/{tipo}",
    response_model=Reporte,
    summary="Generar un reporte (vista previa)",
    responses={404: {"model": ErrorResponse, "description": "Tipo de reporte inexistente"}},
)
def generar_reporte(
    tipo: str,
    filtros: dict = Depends(_filtros),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "generar_reporte", "reporte", detalle={"tipo": tipo, **auditoria_service.filtros_usados(**filtros)}
    )
    return _generar(db, tipo, filtros)


@router.get(
    "/{tipo}/excel",
    summary="Exportar el reporte a Excel (.xlsx)",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}, 404: {"model": ErrorResponse}},
)
def exportar_excel(
    tipo: str,
    filtros: dict = Depends(_filtros),
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    auditor.registrar(
        "exportar_reporte", "reporte", detalle={"tipo": tipo, **auditoria_service.filtros_usados(**filtros)}
    )
    r = _generar(db, tipo, filtros)
    return Response(
        reporte_service.a_excel(r),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{reporte_service.nombre_archivo(r)}"'},
    )


@inicio.get(
    "/resumen", response_model=ResumenInicio, summary="KPIs, gráficos y últimas atenciones de la pantalla Inicio"
)
def resumen_inicio(
    db: Session = Depends(get_db),
    auditor: Auditor = Depends(get_auditor),
    _: CurrentUser = Depends(require_clinical_staff),
):
    resumen = reporte_service.resumen_inicio(db)
    auditor.registrar(
        "consultar_inicio",
        "atencion",
        ids_pacientes=list(dict.fromkeys(a.paciente.id_paciente for a in resumen.ultimas_atenciones)) or None,
    )
    return resumen
