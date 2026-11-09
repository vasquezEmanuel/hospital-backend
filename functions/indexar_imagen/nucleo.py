"""Núcleo de la función de indexación. Carpeta: functions/indexar_imagen — Sprint 3, Fase 4.

Cuando aparece un archivo en el almacenamiento, lo registra en imagen_clinica asociado a su paciente (regla 4).
Es IDEMPOTENTE: el índice único sobre la clave (esquema v1.3) hace que recibir el mismo evento dos veces, o que la API
ya lo haya registrado, no duplique nada. Nunca crea pacientes ni adivina: si no puede determinar el paciente, lo dice.

Claves que reconoce (la primera carpeta que coincida):
  pacientes/{uuid_del_paciente}/archivo.jpg                imágenes subidas por la API (desde v1.5)
  pacientes/{id_numerico}/archivo.jpg                      imágenes subidas por la API antes de v1.5 (siguen válidas)
  [prefijo/]{documento}_{nombre}/archivo.jpg               carpetas históricas: numeroIdentificacion_nombrePaciente
"""

import logging
import mimetypes
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paciente
from app.repositories import imagen_repo, paciente_repo
from app.schemas.paciente import normalizar_documento

log = logging.getLogger(__name__)

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}
_CARPETA_API = re.compile(r"^pacientes$")
_CARPETA_HISTORICA = re.compile(r"^([A-Za-z0-9.\-]{4,25})_(.+)$")

Estado = Literal["registrada", "ya_existia", "ignorada", "sin_paciente", "error"]


@dataclass(frozen=True)
class Resultado:
    clave: str
    estado: Estado
    detalle: str = ""
    id_imagen: int | None = None


def _uuid_o_none(texto: str) -> UUID | None:
    try:
        return UUID(texto)
    except ValueError:
        return None


def _paciente_de(db: Session, carpetas: list[str]) -> tuple[int | None, str]:
    """(clave interna del paciente, motivo si no se encontró)."""
    for i, carpeta in enumerate(carpetas):
        if _CARPETA_API.match(carpeta) and i + 1 < len(carpetas):
            segmento = carpetas[i + 1]
            publico = _uuid_o_none(segmento)
            if publico is not None:  # claves nuevas: pacientes/{uuid}/...
                paciente = paciente_repo.obtener(db, publico)
                if paciente is None:
                    return None, f"no existe el paciente con identificador {publico}"
                return paciente.id_paciente, ""
            if segmento.isdigit():  # claves anteriores a v1.5: pacientes/{id numérico}/...
                paciente = paciente_repo.obtener_por_id_interno(db, int(segmento))
                if paciente is None:
                    return None, f"no existe el paciente con identificador {segmento}"
                return paciente.id_paciente, ""
    for carpeta in carpetas:
        m = _CARPETA_HISTORICA.match(carpeta)
        if not m:
            continue
        try:
            documento = normalizar_documento(m.group(1))
        except ValueError:
            continue
        paciente = db.scalars(select(Paciente).where(Paciente.documento_identidad == documento)).first()
        if paciente is None:
            return None, f"no hay un paciente con el documento {documento} (cargue primero las atenciones)"
        return paciente.id_paciente, ""
    return None, "la ruta no indica a qué paciente pertenece (se esperaba pacientes/{uuid}/ o {documento}_{nombre}/)"


def indexar_clave(db: Session, clave: str, tamano: int | None = None) -> Resultado:
    """Registra una clave del almacenamiento. Hace commit si registró algo."""
    partes = [p for p in clave.split("/") if p]
    if not partes:
        return Resultado(clave, "ignorada", "clave vacía")
    nombre = partes[-1]
    extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in EXTENSIONES:
        return Resultado(clave, "ignorada", "no es una imagen JPEG, PNG o WebP")

    id_paciente, motivo = _paciente_de(db, partes[:-1])
    if id_paciente is None:
        return Resultado(clave, "sin_paciente", motivo)

    id_imagen = imagen_repo.registrar_si_falta(
        db,
        {
            "id_paciente": id_paciente,
            "nombre_archivo": nombre[:255],
            "url_almacenamiento": clave,
            "metadata": {
                "content_type": mimetypes.guess_type(nombre)[0],
                "bytes": tamano,
                "origen": "indexador",
            },
        },
    )
    db.commit()
    if id_imagen is None:
        return Resultado(clave, "ya_existia")
    return Resultado(clave, "registrada", id_imagen=id_imagen)


def indexar_claves(db: Session, claves: list[tuple[str, int | None]]) -> list[Resultado]:
    """Procesa todas las claves aunque alguna falle (estado "error"), para no dejar sin indexar las demás."""
    resultados = []
    for clave, tamano in claves:
        try:
            resultado = indexar_clave(db, clave, tamano)
        except Exception as exc:  # p. ej. la base de datos no responde: se anota y se sigue con las demás
            db.rollback()
            log.exception("Error indexando %s", clave)
            resultado = Resultado(clave, "error", str(exc)[:200])
        log.info("indexar_imagen %s -> %s %s", clave, resultado.estado, resultado.detalle)
        resultados.append(resultado)
    return resultados
