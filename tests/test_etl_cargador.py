"""Pruebas del cargador del ETL contra PostgreSQL real (cada prueba se revierte al terminar)."""

import pytest
from sqlalchemy import text

from etl.cargador import cargar_atenciones, cargar_catalogo
from etl.cli import ejecutar
from etl.comunes import ErrorFormato
from scripts.generar_datos_demo import crear_atenciones_demo, crear_catalogo_demo


def _uno(db, sql: str):
    return db.execute(text(sql)).scalar_one()


@pytest.fixture
def catalogo(db, tmp_path):
    return cargar_catalogo(db, crear_catalogo_demo(tmp_path / "catalogo.xlsx"))


@pytest.fixture
def atenciones_xlsx(tmp_path):
    return crear_atenciones_demo(tmp_path / "atenciones.xlsx")


def test_catalogo_inserta_marca_odontologicos_y_registra_la_importacion(db, catalogo):
    assert (catalogo.insertados, catalogo.actualizados, catalogo.omitidos, catalogo.rechazados) == (9, 0, 0, 0)
    assert _uno(db, "SELECT count(*) FROM cie10 WHERE es_odontologico") == 5
    fila = db.execute(text("SELECT tipo, estado, total_registros FROM importacion")).one()
    assert tuple(fila) == ("cie10", "completado", 9)


def test_catalogo_repetido_no_duplica_y_actualiza_solo_lo_que_cambio(db, catalogo, tmp_path):
    db.execute(text("UPDATE cie10 SET descripcion_4 = 'texto viejo' WHERE cod_4 = 'K021'"))
    otra = cargar_catalogo(db, crear_catalogo_demo(tmp_path / "otra.xlsx"))
    assert (otra.insertados, otra.actualizados, otra.omitidos) == (0, 1, 8)
    assert _uno(db, "SELECT descripcion_4 FROM cie10 WHERE cod_4 = 'K021'") == "Caries de la dentina"


def test_atenciones_sin_catalogo_pide_cargarlo_primero(db, atenciones_xlsx):
    with pytest.raises(ErrorFormato, match="catálogo"):
        cargar_atenciones(db, atenciones_xlsx)


def test_atenciones_carga_lo_valido_y_manda_el_resto_a_revision(db, catalogo, atenciones_xlsx):
    r = cargar_atenciones(db, atenciones_xlsx)
    assert (r.total, r.insertados, r.omitidos, r.rechazados) == (12, 7, 1, 4)
    assert (r.pacientes_nuevos, r.aseguradoras_nuevas, r.bucales_sin_codigo) == (6, 4, 1)
    assert _uno(db, "SELECT count(*) FROM atencion") == 7
    assert _uno(db, "SELECT count(*) FROM diagnostico_hospitalario") == 4
    assert _uno(db, "SELECT count(*) FROM diagnostico_bucal") == 8
    assert (
        _uno(db, "SELECT count(*) FROM cie10_x_diagnostico_bucal") == 8
    )  # "K021, K051" son 2 códigos de 1 diagnóstico


def test_la_cola_de_revision_conserva_la_fila_original_y_no_deja_datos_a_medias(db, catalogo, atenciones_xlsx):
    r = cargar_atenciones(db, atenciones_xlsx)
    filas = db.execute(
        text("SELECT numero_fila, estado, motivo FROM importacion_fila WHERE id_importacion = :i ORDER BY numero_fila"),
        {"i": r.id_importacion},
    ).all()
    assert [f.numero_fila for f in filas] == [9, 10, 12, 13] and {f.estado for f in filas} == {"revision"}
    motivos = {f.numero_fila: f.motivo for f in filas}
    assert "Documento de identidad inválido" in motivos[9]
    assert "Fecha de la atención no reconocida" in motivos[10]
    assert "C187 no está marcado como odontológico" in motivos[12]  # regla 2
    assert "ZZZ9" in motivos[13]
    original = _uno(db, "SELECT datos->>'4:NOMBRE' FROM importacion_fila WHERE numero_fila = 12")
    assert original == "Sofía Ruiz"
    # una fila en revisión no crea nada: ni siquiera el paciente
    assert (
        _uno(
            db,
            "SELECT count(*) FROM paciente WHERE documento_identidad IN ('12', '55667788', '1020304050', '71234567')",
        )
        == 0
    )


def test_cargar_dos_veces_la_misma_hoja_no_duplica_atenciones(db, catalogo, atenciones_xlsx):
    cargar_atenciones(db, atenciones_xlsx)
    otra = cargar_atenciones(db, atenciones_xlsx)
    assert (otra.insertados, otra.omitidos, otra.rechazados) == (0, 8, 4)
    assert _uno(db, "SELECT count(*) FROM atencion") == 7
    assert _uno(db, "SELECT count(*) FROM paciente") == 6


def test_diagnostico_bucal_en_texto_libre_se_guarda_sin_codigo(db, catalogo, atenciones_xlsx):
    cargar_atenciones(db, atenciones_xlsx)  # "caries??" no es un código ni una descripción del catálogo
    sin_codigo = db.execute(
        text(
            "SELECT b.descripcion FROM diagnostico_bucal b "
            "LEFT JOIN cie10_x_diagnostico_bucal x USING (id_diagnostico_bucal) WHERE x.cod_4 IS NULL"
        )
    ).scalars()
    assert list(sin_codigo) == ["caries??"]  # nunca se pierde el texto original; queda pendiente de codificar


def test_aseguradora_se_empareja_sin_importar_mayusculas_ni_espacios(db, catalogo, atenciones_xlsx):
    cargar_atenciones(db, atenciones_xlsx)  # una fila trae "  sura "
    assert _uno(db, "SELECT count(*) FROM aseguradora") == 4
    carlos = _uno(
        db,
        "SELECT a.nombre FROM atencion t JOIN aseguradora a USING (id_aseguradora) "
        "WHERE t.plan_tratamiento = 'Profilaxis'",
    )
    assert carlos == "SURA"


def test_profesional_registrado_se_enlaza_y_el_resto_conserva_el_texto(db, catalogo, atenciones_xlsx):
    db.execute(
        text(
            "INSERT INTO profesional (nombre, identificacion, correo) "
            "VALUES ('Dra. Laura Castaño', '123', 'laura@hospital.test')"
        )
    )
    cargar_atenciones(db, atenciones_xlsx)
    enlazadas = _uno(db, "SELECT count(*) FROM atencion WHERE id_profesional IS NOT NULL AND profesional_texto IS NULL")
    texto = _uno(
        db, "SELECT count(*) FROM atencion WHERE id_profesional IS NULL AND profesional_texto = 'Dr. Andrés Mejía'"
    )
    assert (enlazadas, texto) == (3, 3)  # nunca se descarta el nombre del profesional


def test_diagnosticos_se_resuelven_por_codigo_con_punto_por_descripcion_y_por_varios_codigos(
    db, catalogo, atenciones_xlsx
):
    cargar_atenciones(db, atenciones_xlsx)

    def codigos(documento: str) -> list[str]:
        filas = db.execute(
            text(
                "SELECT x.cod_4 FROM cie10_x_diagnostico_bucal x "
                "JOIN diagnostico_bucal b USING (id_diagnostico_bucal) JOIN atencion a USING (id_atencion) "
                "JOIN paciente p USING (id_paciente) WHERE p.documento_identidad = :d"
            ),
            {"d": documento},
        )
        return sorted(c for (c,) in filas)

    assert codigos("1025847210") == ["K021", "K050"]  # "K021" y la descripción "Gingivitis aguda"
    assert codigos("79421880") == ["K051"] * 2  # "K05.1" y "Gingivitis crónica" (dos atenciones)
    assert codigos("43701882") == ["K021", "K051"]  # un solo diagnóstico con dos códigos
    assert codigos("52880143") == ["K123"]  # "K123 Mucositis oral (ulcerativa)"


def test_ejecutar_enruta_los_comandos_de_la_linea_de_comandos(db, tmp_path):
    r = ejecutar("catalogo", str(crear_catalogo_demo(tmp_path / "c.xlsx")), db)
    assert r.tipo == "cie10" and r.insertados == 9
    with pytest.raises(ValueError):
        ejecutar("otro", "x", db)
