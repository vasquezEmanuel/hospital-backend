"""Recursos /departamentos y /municipios (catálogos de solo lectura). Carpeta: app/routers.

Alimentan los selectores de ubicación del formulario de paciente: primero el departamento, luego sus municipios.
Los códigos son los oficiales del DANE (DIVIPOLA). Datos de catálogo, no de pacientes: no se auditan.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_clinical_staff
from app.db.session import get_db
from app.repositories import ubicacion_repo
from app.schemas.common import ErrorResponse
from app.schemas.ubicacion import DepartamentoOut, MunicipioOut

_RESPUESTAS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}
_DEPARTAMENTO = Annotated[str, Path(pattern=r"^\d{2}$", description="Código DANE de 2 dígitos", examples=["76"])]

departamentos = APIRouter(
    prefix="/departamentos",
    tags=["Ubicación"],
    dependencies=[Depends(require_clinical_staff)],
    responses=_RESPUESTAS,
)
municipios = APIRouter(
    prefix="/municipios",
    tags=["Ubicación"],
    dependencies=[Depends(require_clinical_staff)],
    responses=_RESPUESTAS,
)


def _salida(filas) -> list[MunicipioOut]:
    return [
        MunicipioOut(codigo=m.codigo, nombre=m.nombre, codigo_departamento=m.codigo_departamento, departamento=d)
        for m, d in filas
    ]


@departamentos.get("", response_model=list[DepartamentoOut], summary="Departamentos de Colombia (33, orden alfabético)")
def listar_departamentos(db: Session = Depends(get_db)):
    return [DepartamentoOut(codigo=d.codigo, nombre=d.nombre) for d in ubicacion_repo.departamentos(db)]


@departamentos.get(
    "/{codigo_departamento}/municipios",
    response_model=list[MunicipioOut],
    summary="Municipios de un departamento (orden alfabético)",
    responses={404: {"model": ErrorResponse, "description": "El departamento no existe"}},
)
def municipios_del_departamento(codigo_departamento: _DEPARTAMENTO, db: Session = Depends(get_db)):
    if ubicacion_repo.departamento(db, codigo_departamento) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Departamento no encontrado")
    return _salida(ubicacion_repo.municipios(db, codigo_departamento=codigo_departamento))


@municipios.get(
    "",
    response_model=list[MunicipioOut],
    summary="Buscar municipios por nombre (sin tildes ni mayúsculas), opcionalmente dentro de un departamento",
)
def buscar_municipios(
    q: str | None = Query(None, min_length=2, max_length=100, description="Parte del nombre: «medell», «bogota»"),
    codigo_departamento: str | None = Query(None, pattern=r"^\d{2}$"),
    limite: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return _salida(ubicacion_repo.municipios(db, codigo_departamento=codigo_departamento, q=q, limite=limite))
