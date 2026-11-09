"""Pruebas de imágenes clínicas y archivos firmados (Sprint 3: reglas 4, 5 y 7)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.main import app
from app.models import Atencion, Cie10, DiagnosticoBucal
from app.repositories.imagen_repo import COLOMBIA
from app.services.almacenamiento import AlmacenamientoLocal, AlmacenamientoS3, get_almacenamiento

SECRETO = "t" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBP" + b"2" * 64


@pytest.fixture
def almacen(tmp_path):
    a = AlmacenamientoLocal(tmp_path, SECRETO, "http://testserver")
    app.dependency_overrides[get_almacenamiento] = lambda: a  # lo limpian los fixtures client / anon_client
    return a


def _subir(client, id_paciente, contenido=JPEG, nombre="foto.jpg", **extra):
    return client.post(
        "/api/v1/imagenes",
        data={"id_paciente": str(id_paciente), **{k: str(v) for k, v in extra.items()}},
        files={"archivo": (nombre, contenido, "application/octet-stream")},
    )


def _atencion(db, paciente):
    return db.query(Atencion).filter_by(id_paciente=paciente.id_paciente).order_by(Atencion.fecha_atencion).first()


def _dx_con_codigo(db, atencion, cod_4="K021"):
    dx = DiagnosticoBucal(id_atencion=atencion.id_atencion, descripcion="Caries")
    dx.codigos = [db.get(Cie10, cod_4)]
    db.add(dx)
    db.flush()
    return dx


def test_subir_imagen_devuelve_enlace_firmado_y_el_archivo_se_descarga(client, seed, almacen):
    r = _subir(client, seed["maria"].public_id, nombre="C:\\fotos\\radiografía.jpg")
    assert r.status_code == 201
    body = r.json()
    assert body["nombre_archivo"] == "radiografía.jpg"  # solo el nombre, nunca carpetas del equipo del usuario
    assert body["paciente_nombre"] == "María Rodríguez" and body["id_atencion"] is None
    assert body["url"].startswith("http://testserver/api/v1/archivos/") and body["url_expira_en_segundos"] == 300
    assert "pacientes/" not in body["url"]  # regla 7: la clave del almacenamiento no se expone
    descarga = client.get(body["url"].removeprefix("http://testserver"))
    assert descarga.status_code == 200 and descarga.content == JPEG
    assert descarga.headers["content-type"] == "image/jpeg" and descarga.headers["cache-control"] == "private, no-store"


def test_formatos_png_y_webp_se_aceptan(client, seed, almacen):
    assert _subir(client, seed["maria"].public_id, PNG, "a.png").status_code == 201
    assert _subir(client, seed["maria"].public_id, WEBP, "a.webp").status_code == 201


def test_solo_imagenes_se_valida_el_contenido_no_el_nombre(client, seed, almacen):
    pid = seed["maria"].public_id
    assert _subir(client, pid, b"%PDF-1.7 contenido", "foto.jpg").status_code == 415  # disfrazado de imagen
    assert _subir(client, pid, b"texto cualquiera", "nota.txt").status_code == 415
    assert _subir(client, pid, b"", "vacia.jpg").status_code == 422


def test_archivo_demasiado_grande_es_413(client, seed, almacen, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert _subir(client, seed["maria"].public_id).status_code == 413


def test_regla_4_el_paciente_es_obligatorio_y_debe_existir(client, seed, almacen):
    assert _subir(client, "00000000-0000-4000-8000-000000000000").status_code == 404
    sin_paciente = client.post("/api/v1/imagenes", files={"archivo": ("a.jpg", JPEG, "image/jpeg")})
    assert sin_paciente.status_code == 422


def test_la_atencion_y_el_diagnostico_deben_ser_del_paciente(client, seed, db, almacen):
    maria, carlos = seed["maria"], seed["carlos"]
    atencion = _atencion(db, maria)
    dx = _dx_con_codigo(db, atencion)
    assert _subir(client, carlos.public_id, id_atencion=atencion.public_id).status_code == 422
    assert _subir(client, carlos.public_id, id_diagnostico_bucal=dx.public_id).status_code == 422
    assert (
        _subir(client, maria.public_id, id_diagnostico_bucal="00000000-0000-4000-8000-000000000000").status_code == 422
    )
    otra = db.query(Atencion).filter(Atencion.id_atencion != atencion.id_atencion).first()
    mezcla = _subir(client, maria.public_id, id_atencion=otra.public_id, id_diagnostico_bucal=dx.public_id)
    assert mezcla.status_code == 422  # el diagnóstico es de otra atención


def test_un_diagnostico_implica_su_atencion(client, seed, db, almacen):
    maria = seed["maria"]
    atencion = _atencion(db, maria)
    dx = _dx_con_codigo(db, atencion)
    r = _subir(client, maria.public_id, id_diagnostico_bucal=dx.public_id)
    assert r.status_code == 201
    body = r.json()
    assert body["id_atencion"] == str(atencion.public_id) and body["diagnostico"] == "Caries"
    assert body["fecha_atencion"] == atencion.fecha_atencion.isoformat()


def test_misma_imagen_dos_veces_para_el_mismo_paciente_es_409_pero_otro_paciente_si_puede(client, seed, almacen):
    assert _subir(client, seed["maria"].public_id).status_code == 201
    assert _subir(client, seed["maria"].public_id, nombre="otra_vez.jpg").status_code == 409
    assert _subir(client, seed["carlos"].public_id).status_code == 201


def test_listar_filtra_por_paciente_texto_diagnostico_y_fecha(client, seed, db, almacen):
    maria, carlos = seed["maria"], seed["carlos"]
    dx = _dx_con_codigo(db, _atencion(db, maria))
    _subir(client, maria.public_id, JPEG, id_diagnostico_bucal=dx.public_id)
    _subir(client, maria.public_id, PNG, "b.png")
    _subir(client, carlos.public_id, WEBP, "c.webp")

    def total(**params):
        return client.get("/api/v1/imagenes", params=params).json()["total"]

    assert total() == 3
    assert total(id_paciente=maria.public_id) == 2
    assert total(q="gomez") == 1 and total(q="MARÍA") == 2 and total(q="79.421.880") == 1
    assert total(diagnostico="k021") == 1  # solo la imagen ligada al diagnóstico con ese código
    assert total(diagnostico="C187") == 0
    hoy = datetime.now(COLOMBIA).date()  # los filtros de fecha usan la hora de Colombia, no la del servidor
    assert total(fecha_desde=hoy.isoformat(), fecha_hasta=hoy.isoformat()) == 3
    assert total(fecha_desde=(hoy + timedelta(days=2)).isoformat()) == 0
    assert total(fecha_hasta=(hoy - timedelta(days=2)).isoformat()) == 0


def test_listar_pagina_y_ordena_lo_mas_reciente_primero(client, seed, almacen):
    pid = seed["maria"].public_id
    for contenido, nombre in ((JPEG, "1.jpg"), (PNG, "2.png"), (WEBP, "3.webp")):
        _subir(client, pid, contenido, nombre)
    pagina = client.get("/api/v1/imagenes", params={"page_size": 2, "page": 1}).json()
    assert pagina["total"] == 3 and [i["nombre_archivo"] for i in pagina["items"]] == ["3.webp", "2.png"]
    assert len(client.get("/api/v1/imagenes", params={"page_size": 2, "page": 2}).json()["items"]) == 1


def test_ver_imagen_y_404(client, seed, almacen):
    creada = _subir(client, seed["maria"].public_id).json()
    assert client.get(f"/api/v1/imagenes/{creada['id_imagen']}").json()["nombre_archivo"] == "foto.jpg"
    assert client.get("/api/v1/imagenes/00000000-0000-4000-8000-000000000000").status_code == 404


def test_regla_5_inactivar_oculta_la_imagen_pero_no_borra_nada(client, seed, db, almacen, tmp_path):
    creada = _subir(client, seed["maria"].public_id).json()
    id_imagen = creada["id_imagen"]
    assert client.delete(f"/api/v1/imagenes/{id_imagen}").status_code == 204
    assert client.get(f"/api/v1/imagenes/{id_imagen}").status_code == 404
    assert client.get("/api/v1/imagenes").json()["total"] == 0
    assert client.delete(f"/api/v1/imagenes/{id_imagen}").status_code == 404  # ya inactiva
    fila = db.execute(text("SELECT activo FROM imagen_clinica WHERE public_id = :i"), {"i": id_imagen}).one()
    assert fila.activo is False  # la fila sigue en la base
    assert len(list(tmp_path.rglob("*.jpg"))) == 1  # y el archivo sigue en el almacenamiento


def test_si_la_indexacion_registro_primero_la_clave_se_completan_los_vinculos(client, seed, db, almacen):
    from app.repositories import imagen_repo

    maria = seed["maria"]
    atencion = _atencion(db, maria)
    creada = _subir(client, maria.public_id, id_atencion=atencion.public_id).json()
    clave = db.execute(text("SELECT url_almacenamiento FROM imagen_clinica")).scalar_one()
    db.execute(text("UPDATE imagen_clinica SET id_atencion = NULL"))  # como si solo existiera el registro de la función
    nuevo = imagen_repo.registrar_o_enriquecer(
        db,
        {
            "id_paciente": maria.id_paciente,
            "id_atencion": atencion.id_atencion,
            "nombre_archivo": "foto.jpg",
            "url_almacenamiento": clave,
            "checksum": "x" * 64,
            "metadata": {},
        },
    )
    assert str(nuevo) == creada["id_imagen"]  # devuelve el identificador público
    assert db.execute(text("SELECT count(*) FROM imagen_clinica")).scalar_one() == 1
    assert db.execute(text("SELECT id_atencion FROM imagen_clinica")).scalar_one() == atencion.id_atencion


def test_sin_sesion_no_hay_acceso_a_imagenes(anon_client, seed, almacen):
    assert anon_client.get("/api/v1/imagenes").status_code == 401
    assert anon_client.get("/api/v1/imagenes/00000000-0000-4000-8000-000000000000").status_code == 401
    assert anon_client.delete("/api/v1/imagenes/00000000-0000-4000-8000-000000000000").status_code == 401
    assert anon_client.post("/api/v1/imagenes", data={"id_paciente": "1"}).status_code == 401


def test_enlaces_invalidos_o_de_otro_almacenamiento_dan_404(anon_client, almacen):
    assert anon_client.get("/api/v1/archivos/basura").status_code == 404
    almacen.guardar("pacientes/1/x.jpg", JPEG, "image/jpeg")
    token = almacen.url_firmada("pacientes/1/x.jpg", 60).rsplit("/", 1)[1]
    assert anon_client.get(f"/api/v1/archivos/{token}").status_code == 200  # el enlace firmado es la credencial
    assert anon_client.get(f"/api/v1/archivos/{token}x").status_code == 404  # alterado
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoS3("bucket", object())
    assert anon_client.get(f"/api/v1/archivos/{token}").status_code == 404  # con S3 esta ruta no sirve archivos
