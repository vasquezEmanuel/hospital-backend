"""Autenticación: valida el JWT emitido por el IdP y extrae roles de los claims.

Carpeta: app/core — regla de negocio 6.5 (autenticación en cada solicitud; roles viven en el IdP,
nunca en la base de datos). Sprint 1: autenticación + rol mínimo. Sprint 4: permisos finos y auditoría.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    sub: str  # profesional.auth_id
    email: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)


def _resolve_path(payload: dict, path: str):
    node = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def _unauthorized(detail: str = "Credenciales inválidas o ausentes") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def decode_token(token: str, settings: Settings) -> dict:
    algorithms = [a.strip() for a in settings.auth_algorithms.split(",") if a.strip()]
    options = {"require": ["exp", "sub"]}
    kwargs: dict = {"algorithms": algorithms, "options": options}
    if settings.auth_audience:
        kwargs["audience"] = settings.auth_audience
    else:
        options["verify_aud"] = False
    if settings.auth_issuer:
        kwargs["issuer"] = settings.auth_issuer
    try:
        if settings.auth_jwks_url:
            key = _jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        elif settings.auth_jwt_secret:
            key = settings.auth_jwt_secret
        else:
            raise _unauthorized("Autenticación no configurada en el servidor")
        return jwt.decode(token, key, **kwargs)
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if creds is None:
        raise _unauthorized()
    payload = decode_token(creds.credentials, settings)
    raw_roles = _resolve_path(payload, settings.auth_roles_claim) or []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    return CurrentUser(sub=payload["sub"], email=payload.get("email"), roles=frozenset(raw_roles))


def require_roles(*roles: str):
    """Dependencia: exige al menos uno de los roles indicados (nombres configurables)."""

    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.roles.intersection(roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol insuficiente para esta operación")
        return user

    return _checker


def require_clinical_staff(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Odontólogo o administrador. Se usa en todos los endpoints clínicos."""
    if not user.roles.intersection({settings.role_odontologo, settings.role_administrador}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol insuficiente para esta operación")
    return user
