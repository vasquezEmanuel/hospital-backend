"""Recorrido de demostración de la API contra un servidor en ejecución. Carpeta: scripts/.

Solo usa la biblioteca estándar. Imprime cada petición con su resultado para mostrar el backend funcionando:
salud, seguridad (401/403), búsqueda de pacientes, catálogo CIE-10, subida de imagen con enlace firmado,
expediente, búsqueda enfermedad -> pacientes y registro de auditoría.

    python -m scripts.demo_api --url https://TU-SERVICIO.onrender.com --token TOKEN_ODONTOLOGO --admin-token TOKEN_ADMIN
(también lee DEMO_URL, DEMO_TOKEN y DEMO_ADMIN_TOKEN). Úsalo solo con datos sintéticos.
"""

import argparse
import json
import os
import struct
import sys
import urllib.error
import urllib.request
import uuid
import zlib

_fallos: list[str] = []


def _png_unico() -> bytes:
    """PNG válido de 2x2 píxeles con color aleatorio (distinta en cada corrida: no choca con duplicados)."""

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    color = os.urandom(3)
    filas = b"".join(b"\x00" + color * 2 for _ in range(2))
    cabecera = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", cabecera) + trozo(b"IDAT", zlib.compress(filas)) + trozo(b"IEND", b"")


def _pedir(metodo, url, token=None, cuerpo=None, cabeceras=None):
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"URL no válida: {url}")
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cabeceras or {})  # noqa: S310
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def _json(datos: bytes):
    try:
        return json.loads(datos)
    except ValueError:
        return None


def _paso(titulo, esperado, estado, detalle=""):
    ok = estado == esperado
    print(f"{'OK  ' if ok else 'FALLA'} [{estado}] {titulo}" + (f"  ->  {detalle}" if detalle else ""))
    if not ok:
        _fallos.append(titulo)
    return ok


def _multipart(campos: dict, archivo: tuple[str, str, bytes, str]):
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    campo, nombre, contenido, tipo = archivo
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"; filename="{nombre}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n".encode()
        + contenido
        + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), {"Content-Type": f"multipart/form-data; boundary={limite}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Recorrido de demostración de la API.")
    ap.add_argument("--url", default=os.environ.get("DEMO_URL", "http://localhost:8000"))
    ap.add_argument("--token", default=os.environ.get("DEMO_TOKEN"), help="token con rol odontologo")
    ap.add_argument("--admin-token", default=os.environ.get("DEMO_ADMIN_TOKEN"), help="token con rol administrador")
    a = ap.parse_args()
    if not a.token:
        print("Falta --token (genéralo con: python -m scripts.generar_token)")
        return 2
    base = a.url.rstrip("/")
    api = base + "/api/v1"

    print(f"\n=== Demostración contra {base} ===\n")
    print("-- 1. Salud (si el servicio estaba dormido, la primera respuesta puede tardar ~1 minuto)")
    estado, cuerpo, _ = _pedir("GET", base + "/health")
    _paso("Servicio vivo", 200, estado, str(_json(cuerpo)))
    estado, cuerpo, _ = _pedir("GET", base + "/health/ready")
    _paso("Base de datos conectada", 200, estado, str(_json(cuerpo)))

    print("\n-- 2. Seguridad")
    estado, _, _ = _pedir("GET", api + "/pacientes")
    _paso("Sin token se rechaza", 401, estado)

    print("\n-- 3. Pacientes y catálogo CIE-10")
    estado, cuerpo, _ = _pedir("GET", api + "/pacientes?q=maria", a.token)
    pacientes = _json(cuerpo) or {}
    nombres = [p["nombre"] for p in pacientes.get("items", [])]
    _paso("Buscar 'maria' (sin tildes)", 200, estado, str(nombres))
    estado, cuerpo, _ = _pedir("GET", api + "/cie10?odontologico=true", a.token)
    cie = _json(cuerpo) or {}
    _paso("Códigos CIE-10 odontológicos", 200, estado, str([c["cod_4"] for c in cie.get("items", [])]))
    if not pacientes.get("items"):
        print("\nNo hay pacientes de demostración: carga los datos (ver docs/DESPLIEGUE.md, paso 5).")
        return 1
    id_pac = pacientes["items"][0]["id_paciente"]
    estado, cuerpo, _ = _pedir("GET", f"{api}/pacientes/{id_pac}", a.token)
    _paso("Ficha del paciente", 200, estado, (_json(cuerpo) or {}).get("nombre", ""))

    print("\n-- 4. Imágenes con enlace firmado (reglas 4 y 7)")
    datos, cab = _multipart({"id_paciente": id_pac}, ("archivo", "radiografia_demo.png", _png_unico(), "image/png"))
    estado, cuerpo, _ = _pedir("POST", api + "/imagenes", a.token, datos, cab)
    img = _json(cuerpo) or {}
    _paso("Subir imagen al paciente", 201, estado, img.get("nombre_archivo", str(img)))
    if estado == 201:
        estado, _, tipo = _pedir("GET", img["url"])
        _paso(f"Abrir el enlace firmado (caduca en {img['url_expira_en_segundos']} s)", 200, estado, tipo)
        estado, _, _ = _pedir("GET", img["url"][:-4] + "xxxx")
        _paso("Un enlace alterado se rechaza", 404, estado)

    print("\n-- 5. Expediente y búsqueda bidireccional")
    estado, cuerpo, _ = _pedir("GET", f"{api}/pacientes/{id_pac}/expediente", a.token)
    exp = _json(cuerpo) or {}
    _paso("Expediente: paciente -> atenciones, enfermedades e imágenes", 200, estado, f"claves: {sorted(exp)[:6]}")
    for cod, en in (("C187", "hospitalizacion"), ("K021", "bucal")):
        estado, cuerpo, _ = _pedir("GET", f"{api}/enfermedades/{cod}/pacientes?en={en}", a.token)
        r = _json(cuerpo) or {}
        quienes = [f"{i['nombre']} ({i['fecha_atencion']})" for i in r.get("items", [])]
        _paso(f"Enfermedad {cod} ({en}) -> pacientes", 200, estado, f"{r.get('total')} atenciones: {quienes}")

    print("\n-- 6. Auditoría y roles (regla 6)")
    estado, _, _ = _pedir("GET", api + "/auditoria", a.token)
    _paso("El odontólogo NO puede ver la auditoría", 403, estado)
    if a.admin_token:
        estado, cuerpo, _ = _pedir("GET", api + "/auditoria?page_size=5", a.admin_token)
        r = _json(cuerpo) or {}
        resumen = [f"{e['accion']} por {e['auth_sub']}" for e in r.get("items", [])]
        _paso(
            "El administrador ve el registro de auditoría", 200, estado, f"{r.get('total')} eventos; últimos: {resumen}"
        )
    else:
        print("(omitido: falta --admin-token)")

    print()
    if _fallos:
        print(f"{len(_fallos)} paso(s) con falla: {_fallos}")
        return 1
    print("Todo el recorrido salió bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
