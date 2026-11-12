"""Configuración central (12-factor: todo por variables de entorno).

Carpeta: app/core — soporta Fase 4 / sección 6.5 del documento técnico (secretos fuera del código).
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Hospital Alma Mater — Odontología API"
    environment: str = "local"  # local | staging | production
    # Swagger/ReDoc exponen la forma de la API: se apagan en producción (datos de salud).
    docs_enabled: bool = True
    # Render inyecta RENDER_GIT_COMMIT; el pipeline de CD lo compara con el SHA desplegado.
    git_sha: str = Field(default="dev", validation_alias=AliasChoices("GIT_SHA", "RENDER_GIT_COMMIT"))

    database_url: str = "postgresql://postgres:postgres@localhost:5432/hospital"
    db_pool_size: int = 5

    # --- Validación de tokens del proveedor de identidad (OIDC) ---
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""  # RS256/ES256 (Cognito, Auth0, Supabase con claves asimétricas)
    auth_jwt_secret: str = ""  # HS256 (Supabase con secreto compartido) — alternativa a JWKS
    auth_algorithms: str = "RS256,ES256,HS256"
    auth_roles_claim: str = "groups"  # ruta con puntos, p. ej. "app_metadata.roles"
    # Opcional y APAGADO por decisión del equipo: con True solo entran tokens con segundo factor (claim "aal" = "aal2")
    auth_require_mfa: bool = False
    role_odontologo: str = "odontologo"
    role_administrador: str = "administrador"

    cors_origins: str = ""  # lista separada por comas

    # --- Almacenamiento de imágenes clínicas (Sprint 3) ---
    storage_backend: str = "local"  # local (desarrollo) | s3 (producción: cualquier almacenamiento compatible con S3)
    storage_local_dir: str = "almacen_local"
    storage_bucket: str = ""
    storage_endpoint_url: str = ""  # vacío = AWS; con valor = otro proveedor compatible con S3
    storage_region: str = ""
    storage_access_key_id: str = ""  # claves del almacenamiento S3 (Supabase: Storage > S3 > New access key)
    storage_secret_access_key: str = ""
    storage_signing_secret: str = ""  # firma los enlaces del almacenamiento local; si falta, se usa auth_jwt_secret
    signed_url_ttl_seconds: int = 300  # regla 7: el acceso a imágenes es solo por enlaces temporales firmados
    max_upload_mb: int = 15
    max_import_mb: int = 25  # Sprint 8: archivos Excel/CSV de importación
    max_import_images: int = 50  # Sprint 8: imágenes por solicitud de importación en lote
    public_base_url: str = "http://localhost:8000"  # prefijo de los enlaces del almacenamiento local

    @property
    def sqlalchemy_url(self) -> str:
        """Render/Supabase entregan 'postgresql://'; se fuerza el driver psycopg (v3)."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    def problemas_produccion(self) -> list[str]:
        """Lo que impide arrancar con ENVIRONMENT=production (datos de salud: no se arranca inseguro)."""
        problemas = []
        if self.docs_enabled:
            problemas.append("DOCS_ENABLED debe ser false")
        if not self.auth_jwks_url:
            problemas.append(
                "falta AUTH_JWKS_URL (producción exige claves públicas; no se acepta un secreto compartido)"
            )
        if not self.auth_issuer:
            problemas.append("falta AUTH_ISSUER")
        if not self.auth_audience:
            problemas.append("falta AUTH_AUDIENCE")
        if self.storage_backend != "s3":
            problemas.append("STORAGE_BACKEND debe ser s3")
        if not self.cors_origin_list or "*" in self.cors_origin_list:
            problemas.append("CORS_ORIGINS debe listar los dominios del front (sin *)")
        elif any(not o.startswith("https://") for o in self.cors_origin_list):
            problemas.append("CORS_ORIGINS en producción solo admite dominios https:// (sin http://localhost)")
        return problemas

    @property
    def cors_origin_list(self) -> list[str]:
        """Dominios del front. Se quita la barra final: el navegador envía el origen sin ella y no coincidiría."""
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
