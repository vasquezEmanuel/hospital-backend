"""Genera un JWT de DESARROLLO para probar la API en Swagger o Postman. Carpeta: scripts/.

SOLO PARA DEMOS LOCALES: en producción los tokens los emite el proveedor de identidad (OIDC), no este script.
Uso (desde la raíz del repo, con el entorno virtual activo):
    python -m scripts.generar_token                      # rol odontologo, 8 horas
    python -m scripts.generar_token --rol administrador --horas 2
Requiere AUTH_JWT_SECRET en .env (mínimo 32 caracteres). Respeta AUTH_ROLES_CLAIM, AUTH_AUDIENCE y AUTH_ISSUER.
"""

import argparse
import time

import jwt

from app.core.config import Settings, get_settings


def crear_token(settings: Settings, rol: str = "odontologo", sub: str = "demo-usuario", horas: float = 8) -> str:
    if settings.environment == "production":  # un token de desarrollo nunca debe poder emitirse contra producción
        raise SystemExit("Este script es solo para desarrollo: con ENVIRONMENT=production no emite tokens.")
    if len(settings.auth_jwt_secret) < 32:
        raise SystemExit("Defina AUTH_JWT_SECRET en el archivo .env con al menos 32 caracteres.")
    claims: dict = {"sub": sub, "email": f"{sub}@demo.local", "exp": int(time.time() + horas * 3600)}
    nodo = claims
    *camino, ultimo = settings.auth_roles_claim.split(".")  # p. ej. "groups" o "app_metadata.roles"
    for parte in camino:
        nodo = nodo.setdefault(parte, {})
    nodo[ultimo] = [rol]
    if settings.auth_audience:
        claims["aud"] = settings.auth_audience
    if settings.auth_issuer:
        claims["iss"] = settings.auth_issuer
    return jwt.encode(claims, settings.auth_jwt_secret, algorithm="HS256")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera un token JWT de desarrollo.")
    parser.add_argument("--rol", default="odontologo", choices=("odontologo", "administrador"))
    parser.add_argument("--sub", default="demo-usuario")
    parser.add_argument("--horas", type=float, default=8)
    args = parser.parse_args()
    print(crear_token(get_settings(), args.rol, args.sub, args.horas))


if __name__ == "__main__":
    main()
