"""Reglas de negocio de imágenes clínicas. Carpeta: app/services — Sprint 3.

Regla 4: toda imagen queda asociada, como mínimo, al paciente; la atención y el diagnóstico bucal son opcionales, pero
si se indican deben pertenecer a ese paciente. Regla 5: las imágenes se inactivan, nunca se borran. Regla 7: la API
nunca entrega la clave del almacenamiento, solo un enlace temporal firmado.
"""

import hashlib
import re
import uuid

from sqlalchemy import select
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
    imagen, paciente_nombre, fecha_atencion, diagnostico, paciente_pub, atencion_pub, dx_pub = fila
    ttl = get_settings().signed_url_ttl_seconds
    return ImagenOut(
        id_imagen=imagen.public_id,
        id_paciente=paciente_pub,
        paciente_nombre=paciente_nombre,
        id_atencion=atencion_pub,
        fecha_atencion=fecha_atencion,
        id_diagnostico_bucal=dx_pub,
        diagnostico=diagnostico,
        nombre_archivo=imagen.nombre_archivo,
        fecha_carga=imagen.fecha_carga,
        url=almacen.url_firmada(imagen.url_almacenamiento, ttl),
        url_expira_en_segundos=ttl,
        activo=imagen.activo,
    )


def _validar_vinculos(
    db: Session, id_paciente: int, atencion_publica: uuid.UUID | None, dx_publico: uuid.UUID | None
) -> tuple[int | None, int | None]:
    """La atención y el diagnóstico bucal (identificadores públicos) deben ser del paciente (clave interna).
    Un diagnóstico implica su atención. Devuelve las CLAVES INTERNAS para guardar en la base."""
    id_atencion = id_dx = None
    if atencion_publica is not None:
        atencion = db.scalar(select(Atencion).where(Atencion.public_id == atencion_publica))
        if atencion is None or atencion.id_paciente != id_paciente:
            raise DatosInvalidosError("La atención no existe o pertenece a otro paciente")
        id_atencion = atencion.id_atencion
    if dx_publico is not None:
        dx = db.scalar(select(DiagnosticoBucal).where(DiagnosticoBucal.public_id == dx_publico))
        if dx is None or not dx.activo:
            raise DatosInvalidosError("El diagnóstico bucal indicado no existe")
        if id_atencion is not None and dx.id_atencion != id_atencion:
            raise DatosInvalidosError("El diagnóstico bucal no pertenece a la atención indicada")
        if atencion_publica is None:
            propietaria = db.get(Atencion, dx.id_atencion)
            if propietaria is None or propietaria.id_paciente != id_paciente:
                raise DatosInvalidosError("La atención no existe o pertenece a otro paciente")
        id_atencion, id_dx = dx.id_atencion, dx.id_diagnostico_bucal
    return id_atencion, id_dx


def subir(
    db: Session,
    almacen: Almacenamiento,
    *,
    id_paciente: uuid.UUID,
    id_atencion: uuid.UUID | None,
    id_diagnostico_bucal: uuid.UUID | None,
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
    paciente = paciente_repo.obtener(db, id_paciente)
    if paciente is None:
        raise NotFoundError("Paciente no encontrado")
    id_atencion, id_diagnostico_bucal = _validar_vinculos(db, paciente.id_paciente, id_atencion, id_diagnostico_bucal)

    checksum = hashlib.sha256(contenido).hexdigest()
    if imagen_repo.existe_checksum(db, paciente.id_paciente, checksum):
        raise ConflictError("Esta imagen ya está cargada para el paciente")

    # La URL firmada contiene la clave: por eso la carpeta lleva el UUID del paciente y no su número interno.
    clave = f"pacientes/{paciente.public_id}/{uuid.uuid4().hex}{extension}"
    almacen.guardar(clave, contenido, tipo)
    public_id = imagen_repo.registrar_o_enriquecer(
        db,
        {
            "id_paciente": paciente.id_paciente,
            "id_atencion": id_atencion,
            "id_diagnostico_bucal": id_diagnostico_bucal,
            "nombre_archivo": _nombre_seguro(nombre_original, extension),
            "url_almacenamiento": clave,
            "checksum": checksum,
            "metadata": {"content_type": tipo, "bytes": len(contenido), "origen": "api"},
        },
    )
    db.commit()
    return a_salida(almacen, imagen_repo.obtener_fila(db, public_id))


def listar(db: Session, almacen: Almacenamiento, *, page: int, page_size: int, **filtros) -> Page[ImagenOut]:
    filas, total = imagen_repo.listar(db, page=page, page_size=page_size, **filtros)
    return Page(items=[a_salida(almacen, f) for f in filas], total=total, page=page, page_size=page_size)


def obtener(db: Session, almacen: Almacenamiento, id_imagen: uuid.UUID) -> ImagenOut:
    fila = imagen_repo.obtener_fila(db, id_imagen)
    if fila is None:
        raise NotFoundError("Imagen no encontrada")
    return a_salida(almacen, fila)


def inactivar(db: Session, id_imagen: uuid.UUID) -> None:
    """Regla 5: borrado lógico. El archivo y la fila se conservan; solo deja de mostrarse."""
    imagen = imagen_repo.obtener_activa(db, id_imagen)
    if imagen is None:
        raise NotFoundError("Imagen no encontrada")
    imagen.activo = False
    db.commit()
