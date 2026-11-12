"""Importación de datos por API. Carpeta: app/services — Sprint 8 (Fase 3 del documento técnico).

Reutiliza el ETL del Sprint 2 (etl/cargador.py): lo que no coincide NO se descarta; va a la cola de revisión.
- Catálogo CIE-10: solo se carga una vez (con el catálogo vacío). Cambiarlo después altera qué códigos aceptan los
  diagnósticos bucales (regla 2), por eso las actualizaciones se hacen por consola con el usuario propietario.
- Atenciones: crea pacientes (regla 1: documento único), atenciones y diagnósticos; repetir el archivo no duplica nada.
"""

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories import auditoria_repo, importacion_repo
from app.schemas.common import Page
from app.schemas.importacion import FilaRevisionOut, ImportacionOut, ResultadoImportacion
from app.services.errors import (
    ArchivoMuyGrandeError,
    ArchivoNoPermitidoError,
    ConflictError,
    DatosInvalidosError,
    NotFoundError,
)
from etl.cargador import cargar_atenciones, cargar_catalogo
from etl.comunes import ErrorFormato

EXTENSIONES = {".xls", ".xlsx", ".csv"}
_FIRMAS = {".xls": b"\xd0\xcf\x11\xe0", ".xlsx": b"PK\x03\x04"}


class _Temporal:
    """Guarda la subida en un archivo temporal (los lectores trabajan con rutas) y lo borra siempre al terminar."""

    def __init__(self, archivo: UploadFile, maximo_mb: int):
        nombre = archivo.filename or "archivo"
        self.nombre = os.path.basename(nombre)[:200]
        self.extension = Path(self.nombre).suffix.lower()
        if self.extension not in EXTENSIONES:
            raise ArchivoNoPermitidoError("Solo se aceptan archivos Excel (.xls, .xlsx) o CSV")
        contenido = archivo.file.read(maximo_mb * 1024 * 1024 + 1)
        if len(contenido) > maximo_mb * 1024 * 1024:
            raise ArchivoMuyGrandeError(f"El archivo supera el máximo permitido de {maximo_mb} MB")
        if not contenido:
            raise DatosInvalidosError("El archivo está vacío")
        firma = _FIRMAS.get(self.extension)
        if firma and not contenido.startswith(firma):
            raise ArchivoNoPermitidoError(f"El contenido no corresponde a un archivo {self.extension}")
        fd, self.ruta = tempfile.mkstemp(suffix=self.extension)
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        Path(self.ruta).unlink(missing_ok=True)


def _id_profesional(db: Session, auth_sub: str) -> int | None:
    return auditoria_repo.profesional_por_auth_id(db, auth_sub)


def importar_catalogo(
    db: Session, archivo: UploadFile, *, auth_sub: str, maximo_mb: int, solo_filas_marcadas: bool
) -> ResultadoImportacion:
    with _Temporal(archivo, maximo_mb) as tmp:
        if not importacion_repo.catalogo_vacio(db):
            raise ConflictError(
                "El catálogo CIE-10 ya está cargado. Se carga una sola vez; para actualizarlo se usa la consola."
            )
        try:
            r = cargar_catalogo(
                db, tmp.ruta, not solo_filas_marcadas, id_profesional=_id_profesional(db, auth_sub), nombre=tmp.nombre
            )
        except ErrorFormato as exc:
            raise DatosInvalidosError(str(exc)) from exc
        except IntegrityError as exc:  # dos cargas simultáneas
            db.rollback()
            raise ConflictError("El catálogo se está cargando en otra solicitud") from exc
    return ResultadoImportacion(**asdict(r))


def importar_atenciones(db: Session, archivo: UploadFile, *, auth_sub: str, maximo_mb: int) -> ResultadoImportacion:
    with _Temporal(archivo, maximo_mb) as tmp:
        try:
            r = cargar_atenciones(db, tmp.ruta, id_profesional=_id_profesional(db, auth_sub), nombre=tmp.nombre)
        except ErrorFormato as exc:
            raise DatosInvalidosError(str(exc)) from exc
    return ResultadoImportacion(**asdict(r))


def listar(db: Session, *, page: int, page_size: int) -> Page[ImportacionOut]:
    filas, total = importacion_repo.listar(db, page=page, page_size=page_size)
    return Page(items=[ImportacionOut(**f) for f in filas], total=total, page=page, page_size=page_size)


def obtener(db: Session, id_importacion: int) -> ImportacionOut:
    fila = importacion_repo.obtener(db, id_importacion)
    if fila is None:
        raise NotFoundError("Importación no encontrada")
    return ImportacionOut(**fila)


def filas_en_revision(
    db: Session, id_importacion: int, estado: str | None, *, page: int, page_size: int
) -> Page[FilaRevisionOut]:
    obtener(db, id_importacion)
    filas, total = importacion_repo.filas(db, id_importacion, estado, page=page, page_size=page_size)
    return Page(items=[FilaRevisionOut(**f) for f in filas], total=total, page=page, page_size=page_size)


def resolver_fila(db: Session, id_importacion: int, id_fila: int, *, auth_sub: str) -> FilaRevisionOut:
    fila = importacion_repo.resolver_fila(db, id_importacion, id_fila, _id_profesional(db, auth_sub))
    if fila is None:
        raise NotFoundError("Fila no encontrada")
    db.commit()
    return FilaRevisionOut(**fila)
