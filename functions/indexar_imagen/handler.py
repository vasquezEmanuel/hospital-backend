"""Adaptador del evento de almacenamiento. Carpeta: functions/indexar_imagen — Sprint 3, Fase 4.

Entiende el formato de notificación de S3 ({"Records": [{"eventName": "ObjectCreated:Put", "s3": {"object": {...}}}]}),
que usan también Cloudflare R2 y MinIO. Para otro proveedor (Google Cloud Storage, Azure Blob) solo hay que escribir un
adaptador equivalente que extraiga (clave, tamaño) y llame a nucleo.indexar_claves: la lógica no cambia.

Despliegue: la función usa el mismo código y la misma imagen que la API (necesita `app/` y la variable DATABASE_URL);
solo cambia el punto de entrada: functions.indexar_imagen.handler.handler. Configure reintentos y una cola de mensajes
fallidos en la plataforma: este handler falla a propósito cuando un archivo no se pudo asociar a un paciente.
"""

import logging
from urllib.parse import unquote_plus

from sqlalchemy.orm import Session

from app.db.session import get_engine
from functions.indexar_imagen.nucleo import Resultado, indexar_claves

log = logging.getLogger(__name__)


class IndexacionIncompleta(Exception):
    """Algún archivo no quedó registrado (sin paciente identificable o error). La plataforma lo reintenta / encola."""


def claves_del_evento(evento: dict) -> list[tuple[str, int | None]]:
    """(clave, tamaño) de cada objeto CREADO. Las claves llegan codificadas en URL ("a+b" es "a b")."""
    claves = []
    for registro in evento.get("Records", []):
        if not str(registro.get("eventName", "")).startswith("ObjectCreated"):
            continue  # borrados y otros eventos no se indexan
        objeto = registro.get("s3", {}).get("object", {})
        if objeto.get("key"):
            claves.append((unquote_plus(objeto["key"]), objeto.get("size")))
    return claves


def procesar_evento(db: Session, evento: dict) -> list[Resultado]:
    resultados = indexar_claves(db, claves_del_evento(evento))
    pendientes = [r for r in resultados if r.estado in ("sin_paciente", "error")]
    if pendientes:
        detalle = "; ".join(f"{r.clave}: {r.detalle}" for r in pendientes)
        raise IndexacionIncompleta(f"{len(pendientes)} archivo(s) sin indexar. {detalle}")
    return resultados


def handler(evento: dict, contexto=None) -> dict:
    """Punto de entrada de la función serverless."""
    with Session(get_engine(), expire_on_commit=False) as db:
        resultados = procesar_evento(db, evento)
    resumen: dict[str, int] = {}
    for r in resultados:
        resumen[r.estado] = resumen.get(r.estado, 0) + 1
    log.info("indexar_imagen resumen %s", resumen)
    return resumen
