"""Cliente de la API de administración del proveedor de identidad (Supabase Auth). Carpeta: app/services.

Los roles y las cuentas viven en el proveedor de identidad (sección 4 del prompt); esta capa solo las gestiona en nombre
del administrador. La llave de servicio llega por variable de entorno y no se registra ni se devuelve jamás.
`ProveedorIdentidad` es la interfaz: las pruebas usan un proveedor simulado y nunca llaman a Supabase.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx
from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings

BLOQUEO_PERMANENTE = "876000h"  # ~100 años: Supabase no tiene "bloqueado" sin duración
ROL_CLAIM = "roles"  # app_metadata.roles = ["odontologo"] (coincide con AUTH_ROLES_CLAIM=app_metadata.roles)


class IdentidadError(Exception):
    """El proveedor rechazó la operación (mensaje apto para mostrar) o no respondió."""

    def __init__(self, mensaje: str, *, sin_conexion: bool = False):
        super().__init__(mensaje)
        self.sin_conexion = sin_conexion


class UsuarioYaExisteError(IdentidadError):
    pass


@dataclass(frozen=True)
class UsuarioIdentidad:
    id: str
    email: str
    roles: tuple[str, ...]
    bloqueado: bool


class ProveedorIdentidad(Protocol):
    def crear_usuario(self, email: str, password: str, rol: str) -> str: ...
    def listar_usuarios(self) -> list[UsuarioIdentidad]: ...
    def cambiar_password(self, uid: str, password: str) -> None: ...
    def cambiar_rol(self, uid: str, rol: str) -> None: ...
    def bloquear(self, uid: str, bloqueado: bool) -> None: ...
    def borrar_usuario(self, uid: str) -> None: ...


class SupabaseIdentidad:
    def __init__(self, base_url: str, service_key: str, *, transport: httpx.BaseTransport | None = None):
        self._cliente = httpx.Client(
            base_url=f"{base_url}/auth/v1/admin",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=10.0,
            transport=transport,
        )

    def _llamar(self, metodo: str, ruta: str, **kw) -> httpx.Response:
        try:
            r = self._cliente.request(metodo, ruta, **kw)
        except httpx.HTTPError as exc:  # sin conexión, tiempo agotado...
            raise IdentidadError("No se pudo comunicar con el proveedor de identidad", sin_conexion=True) from exc
        if r.status_code >= 400:
            raise self._error(r)
        return r

    @staticmethod
    def _error(r: httpx.Response) -> IdentidadError:
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = {}
        codigo = str(cuerpo.get("error_code") or cuerpo.get("code") or "")
        if codigo in ("email_exists", "user_already_exists"):
            return UsuarioYaExisteError("Ya existe una cuenta con ese correo")
        if codigo == "weak_password":
            return IdentidadError("La contraseña es demasiado débil para la política del proveedor de identidad")
        if r.status_code in (401, 403):  # llave de servicio inválida: no se detalla al cliente
            return IdentidadError(
                "El servicio de cuentas no está autorizado (revise la configuración)", sin_conexion=True
            )
        if r.status_code == 404:
            return IdentidadError("La cuenta no existe en el proveedor de identidad")
        return IdentidadError("El proveedor de identidad rechazó la operación", sin_conexion=r.status_code >= 500)

    def crear_usuario(self, email: str, password: str, rol: str) -> str:
        r = self._llamar(
            "POST",
            "/users",
            json={"email": email, "password": password, "email_confirm": True, "app_metadata": {ROL_CLAIM: [rol]}},
        )
        return r.json()["id"]

    def listar_usuarios(self) -> list[UsuarioIdentidad]:
        r = self._llamar("GET", "/users", params={"page": 1, "per_page": 1000})
        usuarios = r.json().get("users", [])
        return [
            UsuarioIdentidad(
                id=u["id"],
                email=u.get("email") or "",
                roles=tuple((u.get("app_metadata") or {}).get(ROL_CLAIM) or ()),
                bloqueado=bool(u.get("banned_until")),
            )
            for u in usuarios
        ]

    def cambiar_password(self, uid: str, password: str) -> None:
        self._llamar("PUT", f"/users/{uid}", json={"password": password})

    def cambiar_rol(self, uid: str, rol: str) -> None:
        self._llamar("PUT", f"/users/{uid}", json={"app_metadata": {ROL_CLAIM: [rol]}})

    def bloquear(self, uid: str, bloqueado: bool) -> None:
        self._llamar("PUT", f"/users/{uid}", json={"ban_duration": BLOQUEO_PERMANENTE if bloqueado else "none"})

    def borrar_usuario(self, uid: str) -> None:
        """Solo para deshacer una cuenta recién creada cuando falla el alta del profesional (nunca para bajas)."""
        self._llamar("DELETE", f"/users/{uid}")


def _construir(settings: Settings) -> SupabaseIdentidad | None:
    if not settings.supabase_service_role_key or not settings.identidad_url:
        return None
    return SupabaseIdentidad(settings.identidad_url, settings.supabase_service_role_key)


def get_identidad(settings: Settings = Depends(get_settings)) -> ProveedorIdentidad:
    """Dependencia de las rutas de cuentas: sin llave configurada, la gestión de cuentas responde 503."""
    proveedor = _construir(settings)
    if proveedor is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "La gestión de cuentas no está configurada (falta SUPABASE_SERVICE_ROLE_KEY)",
        )
    return proveedor


def get_identidad_opcional(settings: Settings = Depends(get_settings)) -> ProveedorIdentidad | None:
    """Para rutas que funcionan sin proveedor (p. ej. inactivar un profesional): None si no está configurado."""
    return _construir(settings)
