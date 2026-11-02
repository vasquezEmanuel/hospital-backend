"""Reglas de negocio de imágenes clínicas. Carpeta: app/services — Sprint 3.

Regla 4: toda imagen queda asociada, como mínimo, al paciente; la atención y el diagnóstico bucal son opcionales, pero
si se indican deben pertenecer a ese paciente. Regla 5: las imágenes se inactivan, nunca se borran. Regla 7: la API
nunca entrega la clave del almacenamiento, solo un enlace temporal firmado.
"""

import hashlib
import re
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Atencion, DiagnosticoBucal
from app.repositories import imagen_repo, paciente_repo
from app.repositories.imagen_repo import FilaImagen
from app.schemas.common import Page
from app.schemas.imagen import ImagenOut
from app.services.almacenamiento import Almacenamiento
from app.services.errors import (
    ArchivoMuyGrandeError,
    ArchivoNoPermitidoError,
    ConflictError,
    DatosInvalidosError,
    NotFoundError,
)

_CARACTERES_DE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def detectar_formato(contenido: bytes) -> tuple[str, str] | None:
    """(extensión, tipo de contenido) según los primeros bytes del archivo, no según su nombre."""
    if contenido[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def _nombre_seguro(nombre: str | None, extension: str) -> str:
    """Solo el nombre del archivo (sin carpetas ni caracteres de control), máximo 255 caracteres."""
    limpio = _CARACTERES_DE_CONTROL.sub("", (nombre or "").replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return limpio[-255:] if limpio else f"imagen{extension}"


def a_salida(almacen: Almacenamiento, fila: FilaImagen) -> ImagenOut:
    """Fila de la base -> respuesta de la API con enlace firmado vigente por signed_url_ttl_seconds."""
    imagen, paciente_nombre, fecha_atencion, diagnostico = fila
    ttl = get_settings().signed_url_ttl_seconds
    return ImagenOut(
        id_imagen=imagen.id_imagen,
        id_paciente=imagen.id_paciente,
        paciente_nombre=paciente_nombre,
        id_atencion=imagen.id_atencion,
        fecha_atencion=fecha_atencion,
        id_diagnostico_bucal=imagen.id_diagnostico_bucal,
        diagnostico=diagnostico,
        nombre_archivo=imagen.nombre_archivo,
        fecha_carga=imagen.fecha_carga,
        url=almacen.url_firmada(imagen.url_almacenamiento, ttl),
        url_expira_en_segundos=ttl,
        activo=imagen.activo,
    )


def _validar_vinculos(
    db: Session, id_paciente: int, id_atencion: int | None, id_diagnostico_bucal: int | None
) -> tuple[int | None, int | None]:
    """La atención y el diagnóstico bucal deben ser del paciente. Un diagnóstico implica su atención."""
    if id_diagnostico_bucal is not None:
        dx = db.get(DiagnosticoBucal, id_diagnostico_bucal)
        if dx is None or not dx.activo:
            raise DatosInvalidosError("El diagnóstico bucal indicado no existe")
        if id_atencion is not None and dx.id_atencion != id_atencion:
            raise DatosInvalidosError("El diagnóstico bucal no pertenece a la atención indicada")
        id_atencion = dx.id_atencion
    if id_atencion is not None:
        atencion = db.get(Atencion, id_atencion)
        if atencion is None or atencion.id_paciente != id_paciente:
            raise DatosInvalidosError("La atención no existe o pertenece a otro paciente")
    return id_atencion, id_diagnostico_bucal


def subir(
    db: Session,
    almacen: Almacenamiento,
    *,
    id_paciente: int,
    id_atencion: int | None,
    id_diagnostico_bucal: int | None,
    nombre_original: str | None,
    contenido: bytes,
) -> ImagenOut:
    maximo_mb = get_settings().max_upload_mb
    if not contenido:
        raise DatosInvalidosError("El archivo está vacío")
    if len(contenido) > maximo_mb * 1024 * 1024:
        raise ArchivoMuyGrandeError(f"El archivo supera el máximo permitido de {maximo_mb} MB")
    formato = detectar_formato(contenido)
    if formato is None:
        raise ArchivoNoPermitidoError("Solo se aceptan imágenes JPEG, PNG o WebP")
    extension, tipo = formato
    if paciente_repo.obtener(db, id_paciente) is None:
        raise NotFoundError("Paciente no encontrado")
    id_atencion, id_diagnostico_bucal = _validar_vinculos(db, id_paciente, id_atencion, id_diagnostico_bucal)

    checksum = hashlib.sha256(contenido).hexdigest()
    if imagen_repo.existe_checksum(db, id_paciente, checksum):
        raise ConflictError("Esta imagen ya está cargada para el paciente")

    clave = f"pacientes/{id_paciente}/{uuid.uuid4().hex}{extension}"
    almacen.guardar(clave, contenido, tipo)
    id_imagen = imagen_repo.registrar_o_enriquecer(
        db,
        {
            "id_paciente": id_paciente,
            "id_atencion": id_atencion,
            "id_diagnostico_bucal": id_diagnostico_bucal,
            "nombre_archivo": _nombre_seguro(nombre_original, extension),
            "url_almacenamiento": clave,
            "checksum": checksum,
            "metadata": {"content_type": tipo, "bytes": len(contenido), "origen": "api"},
        },
    )
    db.commit()
    return a_salida(almacen, imagen_repo.obtener_fila(db, id_imagen))


def listar(db: Session, almacen: Almacenamiento, *, page: int, page_size: int, **filtros) -> Page[ImagenOut]:
    filas, total = imagen_repo.listar(db, page=page, page_size=page_size, **filtros)
    return Page(items=[a_salida(almacen, f) for f in filas], total=total, page=page, page_size=page_size)


def obtener(db: Session, almacen: Almacenamiento, id_imagen: int) -> ImagenOut:
    fila = imagen_repo.obtener_fila(db, id_imagen)
    if fila is None:
        raise NotFoundError("Imagen no encontrada")
    return a_salida(almacen, fila)


def inactivar(db: Session, id_imagen: int) -> None:
    """Regla 5: borrado lógico. El archivo y la fila se conservan; solo deja de mostrarse."""
    imagen = imagen_repo.obtener_activa(db, id_imagen)
    if imagen is None:
        raise NotFoundError("Imagen no encontrada")
    imagen.activo = False
    db.commit()
