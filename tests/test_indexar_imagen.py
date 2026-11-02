"""Pruebas de la función de indexación de imágenes (Sprint 3, Fase 4: reglas 4 y 5)."""

import pytest
from sqlalchemy import text

from functions.indexar_imagen import reindexar
from functions.indexar_imagen.handler import IndexacionIncompleta, claves_del_evento, procesar_evento
from functions.indexar_imagen.nucleo import indexar_clave, indexar_claves


def _evento(*claves, nombre="ObjectCreated:Put"):
    return {"Records": [{"eventName": nombre, "s3": {"object": {"key": c, "size": 10}}} for c in claves]}


def _filas(db):
    return db.execute(
        text("SELECT id_paciente, nombre_archivo, url_almacenamiento, metadata FROM imagen_clinica ORDER BY 1, 3")
    ).all()


def test_carpeta_de_la_api_se_asocia_por_identificador(db, seed):
    pid = seed["maria"].id_paciente
    r = indexar_clave(db, f"pacientes/{pid}/abc123.jpg", 2048)
    assert r.estado == "registrada" and r.id_imagen is not None
    (fila,) = _filas(db)
    assert fila.id_paciente == pid and fila.nombre_archivo == "abc123.jpg"
    assert fila.metadata == {"content_type": "image/jpeg", "bytes": 2048, "origen": "indexador"}


def test_carpeta_historica_documento_nombre_se_asocia_por_documento(db, seed):
    r = indexar_clave(db, "migracion/1025847210_Maria Rodriguez/radiografia 1.PNG")
    assert r.estado == "registrada"
    assert _filas(db)[0].id_paciente == seed["maria"].id_paciente
    # con puntos en el documento y sin prefijo
    assert indexar_clave(db, "79.421.880_Carlos Gomez/foto.jpeg").estado == "registrada"
    assert {f.id_paciente for f in _filas(db)} == {seed["maria"].id_paciente, seed["carlos"].id_paciente}


def test_es_idempotente_el_mismo_evento_dos_veces_no_duplica(db, seed):
    clave = f"pacientes/{seed['maria'].id_paciente}/x.jpg"
    assert indexar_clave(db, clave).estado == "registrada"
    assert indexar_clave(db, clave).estado == "ya_existia"
    assert len(_filas(db)) == 1


def test_no_pisa_lo_que_la_api_ya_registro(db, seed):
    maria = seed["maria"]
    clave = f"pacientes/{maria.id_paciente}/y.jpg"
    db.execute(
        text(
            "INSERT INTO imagen_clinica (id_paciente, nombre_archivo, url_almacenamiento, checksum) "
            "VALUES (:p, 'original.jpg', :k, 'abc')"
        ),
        {"p": maria.id_paciente, "k": clave},
    )
    assert indexar_clave(db, clave).estado == "ya_existia"
    (fila,) = db.execute(text("SELECT nombre_archivo, checksum FROM imagen_clinica")).all()
    assert tuple(fila) == ("original.jpg", "abc")


def test_regla_4_sin_paciente_no_se_inventa_ni_se_registra(db, seed):
    casos = {
        "pacientes/999999/a.jpg": "no existe el paciente",
        "55555555_Nadie Conocido/a.jpg": "no hay un paciente con el documento 55555555",
        "radiografias/a.jpg": "no indica a qué paciente",
        "CARPETA_extra/a.jpg": "no hay un paciente con el documento CARPETA",
        "suelta.jpg": "no indica a qué paciente",
    }
    for clave, motivo in casos.items():
        r = indexar_clave(db, clave)
        assert r.estado == "sin_paciente" and motivo in r.detalle, clave
    assert _filas(db) == []  # nada quedó registrado y no se creó ningún paciente nuevo
    assert db.execute(text("SELECT count(*) FROM paciente")).scalar_one() == 2


def test_lo_que_no_es_imagen_se_ignora(db, seed):
    pid = seed["maria"].id_paciente
    for clave in (f"pacientes/{pid}/notas.pdf", f"pacientes/{pid}/sin_extension", f"pacientes/{pid}/", ""):
        assert indexar_clave(db, clave).estado == "ignorada", clave
    assert _filas(db) == []


def test_evento_s3_decodifica_la_clave_y_solo_toma_altas():
    evento = _evento("migracion/1025847210_Mar%C3%ADa+Rodr%C3%ADguez/foto+1.jpg")
    assert claves_del_evento(evento) == [("migracion/1025847210_María Rodríguez/foto 1.jpg", 10)]
    assert claves_del_evento(_evento("a.jpg", nombre="ObjectRemoved:Delete")) == []
    assert claves_del_evento({}) == []


def test_procesar_evento_registra_y_falla_si_algun_archivo_quedo_sin_paciente(db, seed):
    pid = seed["maria"].id_paciente
    ok = procesar_evento(db, _evento(f"pacientes/{pid}/uno.jpg"))
    assert [r.estado for r in ok] == ["registrada"]
    with pytest.raises(IndexacionIncompleta, match="1 archivo"):
        procesar_evento(db, _evento(f"pacientes/{pid}/dos.jpg", "pacientes/999999/tres.jpg"))
    assert [f.nombre_archivo for f in _filas(db)] == ["dos.jpg", "uno.jpg"]  # el bueno se registró igual


def test_un_error_en_una_clave_no_impide_indexar_las_demas(db, seed, monkeypatch):
    from functions.indexar_imagen import nucleo

    original = nucleo.indexar_clave

    def a_veces_falla(db, clave, tamano=None):
        if "malo" in clave:
            raise RuntimeError("base de datos no disponible")
        return original(db, clave, tamano)

    monkeypatch.setattr(nucleo, "indexar_clave", a_veces_falla)
    monkeypatch.setattr(
        db, "rollback", lambda: None
    )  # en la prueba todo vive en una transacción que no debe deshacerse
    pid = seed["maria"].id_paciente
    resultados = indexar_claves(db, [(f"pacientes/{pid}/malo.jpg", None), (f"pacientes/{pid}/bueno.jpg", None)])
    assert [r.estado for r in resultados] == ["error", "registrada"]


def test_reindexar_lista_de_claves_resume_y_reporta_pendientes(db, seed, tmp_path, monkeypatch, capsys):
    pid = seed["maria"].id_paciente
    lista = tmp_path / "claves.txt"
    lista.write_text(f"pacientes/{pid}/a.jpg\n\n1025847210_Maria/b.png\n77777777_Fantasma/c.jpg\nleeme.txt\n")
    monkeypatch.setattr(reindexar, "get_engine", lambda: db.get_bind())
    assert reindexar.main([str(lista)]) == 1  # hay un archivo sin paciente
    salida = capsys.readouterr().out
    assert "registrada" in salida and "PENDIENTE 77777777_Fantasma/c.jpg" in salida
    assert reindexar.main([str(tmp_path / "no_existe.txt")]) == 2
