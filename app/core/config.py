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
    role_odontologo: str = "odontologo"
    role_administrador: str = "administrador"

    cors_origins: str = ""  # lista separada por comas

    @property
    def sqlalchemy_url(self) -> str:
        """Render/Supabase entregan 'postgresql://'; se fuerza el driver psycopg (v3)."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
