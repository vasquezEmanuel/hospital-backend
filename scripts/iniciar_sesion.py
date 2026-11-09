"""Inicia sesión en Supabase Auth (correo + contraseña + código MFA) y entrega el token. Carpeta: scripts/.

Alternativa a Postman: el token resultante se pega en Swagger (/docs -> Authorize). Solo usa la librería estándar.
Uso (desde la raíz del repo; no necesita .env ni entorno virtual):
    python -m scripts.iniciar_sesion --url https://REF.supabase.co --key CLAVE_PUBLICA --email medico@hospital.org
La clave es la pública (anon / publishable), nunca la service_role.
La contraseña se pide por teclado (no queda en el historial).
Variables opcionales: SUPABASE_URL, SUPABASE_KEY, SUPABASE_EMAIL.
Flujo: contraseña -> (si no tiene app autenticadora: la inscribe y muestra el secreto) -> reto -> código de 6 dígitos
-> token aal2.
Corresponde a la regla 6/7 de seguridad (Sprint 5): MFA aal2 exigido por la API con AUTH_REQUIRE_MFA=true.
"""

import argparse
import getpass
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable


class ErrorSupabase(Exception):
    """Respuesta de error de Supabase Auth, con el mensaje ya legible."""


def _llamar(base: str, key: str, metodo: str, ruta: str, cuerpo: dict | None = None, token: str | None = None) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{base}/auth/v1{ruta}", data=datos, method=metodo)  # noqa: S310 (URL del propio proyecto)
    req.add_header("apikey", key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token or key}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            texto = r.read().decode()
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read().decode())
            msg = detalle.get("msg") or detalle.get("message") or detalle.get("error_description") or str(detalle)
        except ValueError:
            msg = e.reason
        raise ErrorSupabase(f"Supabase respondió {e.code}: {msg}") from e
    except urllib.error.URLError as e:
        raise ErrorSupabase(f"No se pudo conectar con {base}: {e.reason}") from e
    return json.loads(texto) if texto else {}


def iniciar_sesion(
    base: str,
    key: str,
    email: str,
    password: str,
    pedir_codigo: Callable[[], str],
    avisar: Callable[[str], None] = print,
    segundo_factor: bool = True,
) -> dict:
    """Devuelve {"token": ..., "aal": "aal1"|"aal2"}. Inscribe el TOTP solo si aún no hay uno verificado."""
    base = base.rstrip("/")
    sesion = _llamar(base, key, "POST", "/token?grant_type=password", {"email": email, "password": password})
    token = sesion["access_token"]
    if not segundo_factor:
        return {"token": token, "aal": "aal1"}
    usuario = _llamar(base, key, "GET", "/user", token=token)
    factores = [f for f in usuario.get("factors") or [] if f.get("factor_type", f.get("type")) == "totp"]
    verificados = [f for f in factores if f.get("status") == "verified"]
    if verificados:
        factor_id = verificados[0]["id"]
    else:
        for f in factores:  # inscripciones a medias de un intento anterior estorban: se borran
            _llamar(base, key, "DELETE", f"/factors/{f['id']}", token=token)
        nuevo = _llamar(
            base, key, "POST", "/factors", {"factor_type": "totp", "friendly_name": "App autenticadora"}, token
        )
        factor_id = nuevo["id"]
        avisar(
            "\nPRIMERA VEZ: en Google/Microsoft Authenticator o Authy elija 'Añadir cuenta' >\n"
            "'Ingresar clave de configuración' y "
            f"pegue este secreto: {nuevo['totp']['secret']}\nLuego escriba el código de 6 dígitos que muestre la app."
        )
    reto = _llamar(base, key, "POST", f"/factors/{factor_id}/challenge", {}, token)
    verif = _llamar(
        base, key, "POST", f"/factors/{factor_id}/verify", {"challenge_id": reto["id"], "code": pedir_codigo()}, token
    )
    return {"token": verif["access_token"], "aal": "aal2"}


def _copiar(texto: str) -> bool:
    """Copia al portapapeles con la herramienta del sistema (clip / pbcopy / xclip); False si no hay ninguna."""
    sistema = platform.system()
    cmd = (
        ["clip"]
        if sistema == "Windows"
        else ["pbcopy"]
        if sistema == "Darwin"
        else ["xclip", "-selection", "clipboard"]
    )
    if not shutil.which(cmd[0]):
        return False
    try:
        subprocess.run(cmd, input=texto.encode(), check=True, timeout=10)  # noqa: S603
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inicia sesión en Supabase con MFA y entrega el token para Swagger.")
    p.add_argument("--url", default=os.getenv("SUPABASE_URL"), help="https://REF.supabase.co")
    p.add_argument("--key", default=os.getenv("SUPABASE_KEY"), help="clave pública (anon/publishable)")
    p.add_argument("--email", default=os.getenv("SUPABASE_EMAIL"))
    p.add_argument(
        "--sin-mfa", action="store_true", help="solo contraseña (token aal1; la API lo rechaza si exige MFA)"
    )
    p.add_argument("--mostrar", action="store_true", help="imprimir el token completo (por defecto solo se copia)")
    a = p.parse_args(argv)
    if not (a.url and a.key):
        p.error("Falta --url y --key (o las variables SUPABASE_URL y SUPABASE_KEY).")
    email = a.email or input("Correo: ").strip()
    password = getpass.getpass("Contraseña: ")
    try:
        r = iniciar_sesion(
            a.url,
            a.key,
            email,
            password,
            lambda: input("Código de 6 dígitos de la app: ").strip(),
            segundo_factor=not a.sin_mfa,
        )
    except ErrorSupabase as e:
        print(f"\nERROR: {e}")
        return 1
    print(
        f"\nSesión iniciada. Nivel: {r['aal']} ({'con' if r['aal'] == 'aal2' else 'SIN'} segundo factor). Dura 1 hora."
    )
    if _copiar(r["token"]) and not a.mostrar:
        print("El token quedó COPIADO en el portapapeles: en Swagger pulse Authorize y pegue (Ctrl+V).")
    else:
        print("\nToken (cópielo completo, en una sola línea):\n" + r["token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
