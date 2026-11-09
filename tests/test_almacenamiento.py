"""Pruebas del almacenamiento de imágenes (Sprint 3, regla 7: acceso solo por enlaces temporales firmados)."""

import sys
import types

import pytest

from app.core.config import get_settings
from app.schemas.expediente import ExpedienteOut
from app.schemas.imagen import ImagenOut
from app.services import almacenamiento as alm
from app.services.almacenamiento import AlmacenamientoLocal, AlmacenamientoS3, get_almacenamiento

SECRETO = "s" * 40


@pytest.fixture
def local(tmp_path):
    return AlmacenamientoLocal(tmp_path, SECRETO, "http://localhost:8000/")


def _token(url: str) -> str:
    return url.rsplit("/api/v1/archivos/", 1)[1]


def test_local_guarda_y_el_enlace_firmado_devuelve_el_archivo(local):
    local.guardar("pacientes/1/foto.jpg", b"contenido", "image/jpeg")
    url = local.url_firmada("pacientes/1/foto.jpg", 300)
    assert url.startswith("http://localhost:8000/api/v1/archivos/")  # sin doble barra
    ruta, tipo = local.resolver(_token(url))
    assert ruta.read_bytes() == b"contenido" and tipo == "image/jpeg"


def test_local_enlace_vencido_no_sirve(local, monkeypatch):
    local.guardar("a.png", b"x", "image/png")
    token = _token(local.url_firmada("a.png", 60))
    ahora = alm.time.time()
    monkeypatch.setattr(alm.time, "time", lambda: ahora + 61)
    assert local.resolver(token) is None


def test_local_enlace_alterado_o_malformado_no_sirve(local):
    local.guardar("a.png", b"x", "image/png")
    carga, _, firma = _token(local.url_firmada("a.png", 60)).partition(".")
    assert local.resolver(f"{carga}.{'0' * len(firma)}") is None  # firma falsa
    assert local.resolver(f"{carga}x.{firma}") is None  # carga alterada: la firma ya no coincide
    assert local.resolver("basura") is None
    assert local.resolver("") is None


def test_local_enlace_de_un_archivo_inexistente_no_sirve(local):
    assert local.resolver(_token(local.url_firmada("no_existe.png", 60))) is None


def test_local_no_permite_salirse_de_la_carpeta(local):
    with pytest.raises(ValueError):
        local.guardar("../fuera.txt", b"x", "text/plain")


def test_local_exige_secreto_largo(tmp_path):
    with pytest.raises(RuntimeError, match="32 caracteres"):
        AlmacenamientoLocal(tmp_path, "corto")


def test_s3_guarda_y_firma_con_el_cliente_del_proveedor():
    llamadas = []

    class ClienteFalso:
        def put_object(self, **kwargs):
            llamadas.append(("put", kwargs))

        def generate_presigned_url(self, operacion, Params, ExpiresIn):  # noqa: N803 (firma de boto3)
            llamadas.append((operacion, Params, ExpiresIn))
            return "https://bucket.example/firmado"

    s3 = AlmacenamientoS3("mi-bucket", ClienteFalso())
    s3.guardar("k/1.jpg", b"datos", "image/jpeg")
    assert s3.url_firmada("k/1.jpg", 120) == "https://bucket.example/firmado"
    assert llamadas[0] == (
        "put",
        {"Bucket": "mi-bucket", "Key": "k/1.jpg", "Body": b"datos", "ContentType": "image/jpeg"},
    )
    assert llamadas[1] == ("get_object", {"Bucket": "mi-bucket", "Key": "k/1.jpg"}, 120)


@pytest.fixture
def entorno_limpio(monkeypatch):
    """Cada prueba parte sin cachés y deja todo como estaba."""
    for var in (
        "STORAGE_BACKEND",
        "STORAGE_LOCAL_DIR",
        "STORAGE_BUCKET",
        "STORAGE_ENDPOINT_URL",
        "STORAGE_REGION",
        "STORAGE_ACCESS_KEY_ID",
        "STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    get_almacenamiento.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()
    get_almacenamiento.cache_clear()


def test_fabrica_usa_el_almacenamiento_local_por_defecto(entorno_limpio, tmp_path):
    entorno_limpio.setenv("STORAGE_LOCAL_DIR", str(tmp_path))
    entorno_limpio.setenv("AUTH_JWT_SECRET", SECRETO)
    almacen = get_almacenamiento()
    assert isinstance(almacen, AlmacenamientoLocal) and almacen.carpeta == tmp_path.resolve()


def test_fabrica_crea_el_cliente_s3_con_el_endpoint_configurado(entorno_limpio):
    recibido = {}

    def client(servicio, **kwargs):
        recibido.update(servicio=servicio, **kwargs)
        return object()

    entorno_limpio.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    entorno_limpio.setenv("STORAGE_BACKEND", "s3")
    entorno_limpio.setenv("STORAGE_BUCKET", "imagenes-hospital")
    entorno_limpio.setenv("STORAGE_ENDPOINT_URL", "https://r2.example.com")
    entorno_limpio.setenv("STORAGE_REGION", "us-east-1")
    entorno_limpio.setenv("STORAGE_ACCESS_KEY_ID", "clave-id")
    entorno_limpio.setenv("STORAGE_SECRET_ACCESS_KEY", "clave-secreta")
    almacen = get_almacenamiento()
    assert isinstance(almacen, AlmacenamientoS3) and almacen.bucket == "imagenes-hospital"
    config = recibido.pop("config")
    assert config.signature_version == "s3v4" and config.s3 == {"addressing_style": "path"}
    assert recibido == {
        "servicio": "s3",
        "endpoint_url": "https://r2.example.com",
        "region_name": "us-east-1",
        "aws_access_key_id": "clave-id",
        "aws_secret_access_key": "clave-secreta",
    }


def test_s3_sin_bucket_falla_con_un_mensaje_claro(entorno_limpio):
    entorno_limpio.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(RuntimeError, match="STORAGE_BUCKET"):
        get_almacenamiento()


def test_s3_con_cliente_real_firma_en_estilo_de_ruta_y_vence(entorno_limpio):
    """Sin red: boto3 firma localmente. Así se comprueba la forma del enlace que recibirá el navegador."""
    entorno_limpio.setenv("STORAGE_BACKEND", "s3")
    entorno_limpio.setenv("STORAGE_BUCKET", "imagenes")
    entorno_limpio.setenv("STORAGE_ENDPOINT_URL", "https://abc.storage.supabase.co/storage/v1/s3")
    entorno_limpio.setenv("STORAGE_REGION", "us-east-1")
    entorno_limpio.setenv("STORAGE_ACCESS_KEY_ID", "id-de-prueba")
    entorno_limpio.setenv("STORAGE_SECRET_ACCESS_KEY", "secreto-de-prueba")
    url = get_almacenamiento().url_firmada("pacientes/1/foto.png", 300)
    assert url.startswith("https://abc.storage.supabase.co/storage/v1/s3/imagenes/pacientes/1/foto.png?")
    assert "X-Amz-Expires=300" in url and "X-Amz-Signature=" in url and "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url


def test_esquemas_de_imagen_y_expediente_validan_una_respuesta_minima():
    imagen = {
        "id_imagen": "1b4e28ba-2fa1-4d3b-a3b4-0c9e8a6c1d11",
        "id_paciente": "9f1c3d52-7a64-4e0b-8f2d-5c3a1b7e6d22",
        "paciente_nombre": "Ana Pérez",
        "nombre_archivo": "foto.jpg",
        "fecha_carga": "2026-09-12T09:30:00-05:00",
        "url": "http://localhost:8000/api/v1/archivos/x.y",
        "url_expira_en_segundos": 300,
        "activo": True,
    }
    assert ImagenOut(**imagen).id_atencion is None  # la atención es opcional (regla 4: como mínimo, el paciente)
    paciente = {
        "id_paciente": "9f1c3d52-7a64-4e0b-8f2d-5c3a1b7e6d22",
        "codigo": "P-0002",
        "tipo_documento": "CC",
        "documento_identidad": "1025847210",
        "nombre": "Ana Pérez",
        "fecha_nacimiento": None,
        "edad": None,
        "sexo": None,
        "telefono": None,
        "correo": None,
        "ciudad": None,
        "aseguradora_actual": None,
        "total_atenciones": 0,
        "ultima_atencion": None,
        "creado_en": "2026-09-12T09:30:00-05:00",
    }
    expediente = ExpedienteOut.model_validate(
        {"paciente": paciente, "atenciones": [], "imagenes_sin_atencion": [imagen], "total_imagenes": 1}
    )
    assert expediente.total_imagenes == 1 and expediente.imagenes_sin_atencion[0].paciente_nombre == "Ana Pérez"
