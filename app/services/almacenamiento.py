"""Almacenamiento de imágenes clínicas. Carpeta: app/services — Sprint 3 (Object Storage S3-compatible).

Regla 7: el acceso a imágenes es SIEMPRE por enlaces temporales firmados.
- AlmacenamientoS3: producción. Cualquier proveedor compatible con S3 (AWS S3, Cloudflare R2, Supabase Storage...);
  el enlace lo firma el propio proveedor (URL prefirmada).
- AlmacenamientoLocal: desarrollo y demos, sin servicios externos. Guarda en una carpeta y firma enlaces propios con
  HMAC-SHA256 que sirve la ruta /api/v1/archivos/{token}.
"""

import base64
import hashlib
import hmac
import mimetypes
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Almacenamiento(Protocol):
    def guardar(self, clave: str, contenido: bytes, content_type: str) -> None: ...

    def url_firmada(self, clave: str, segundos: int) -> str: ...


class AlmacenamientoLocal:
    def __init__(self, carpeta: str | Path, secreto: str, base_url: str = ""):
        if len(secreto) < 32:
            raise RuntimeError("Defina STORAGE_SIGNING_SECRET (o AUTH_JWT_SECRET) con al menos 32 caracteres.")
        self.carpeta = Path(carpeta).resolve()
        self._secreto = secreto.encode()
        self.base_url = base_url.rstrip("/")

    def _ruta(self, clave: str) -> Path:
        ruta = (self.carpeta / clave).resolve()
        if not ruta.is_relative_to(self.carpeta):  # evita salirse de la carpeta con ../
            raise ValueError("Clave de almacenamiento no válida")
        return ruta

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> None:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)

    def _firma(self, carga: str) -> str:
        return hmac.new(self._secreto, carga.encode(), hashlib.sha256).hexdigest()

    def url_firmada(self, clave: str, segundos: int) -> str:
        vence = int(time.time()) + segundos
        carga = base64.urlsafe_b64encode(f"{vence}|{clave}".encode()).decode().rstrip("=")
        return f"{self.base_url}/api/v1/archivos/{carga}.{self._firma(carga)}"

    def resolver(self, token: str) -> tuple[Path, str] | None:
        """Token válido y vigente -> (ruta del archivo, tipo de contenido). Cualquier otro caso -> None."""
        carga, _, firma = token.partition(".")
        if not carga or not hmac.compare_digest(firma, self._firma(carga)):
            return None
        try:
            vence, clave = base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)).decode().split("|", 1)
            ruta = self._ruta(clave)
        except ValueError:
            return None
        if int(vence) < time.time() or not ruta.is_file():
            return None
        return ruta, mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"


class AlmacenamientoS3:
    def __init__(self, bucket: str, cliente):
        self.bucket = bucket
        self.cliente = cliente

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> None:
        self.cliente.put_object(Bucket=self.bucket, Key=clave, Body=contenido, ContentType=content_type)

    def url_firmada(self, clave: str, segundos: int) -> str:
        return self.cliente.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": clave}, ExpiresIn=segundos
        )


@lru_cache
def get_almacenamiento() -> Almacenamiento:
    s = get_settings()
    if s.storage_backend == "s3":
        import boto3  # solo se necesita en producción

        cliente = boto3.client(
            "s3", endpoint_url=s.storage_endpoint_url or None, region_name=s.storage_region or None
        )  # credenciales: variables AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY o rol de la plataforma
        return AlmacenamientoS3(s.storage_bucket, cliente)
    return AlmacenamientoLocal(s.storage_local_dir, s.storage_signing_secret or s.auth_jwt_secret, s.public_base_url)
