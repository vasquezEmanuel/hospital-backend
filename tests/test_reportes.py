"""Sprint 9: reportes (8 tipos, filtros, Excel) y resumen de Inicio."""

import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.main import app
from app.models import Aseguradora, Profesional
from app.services.almacenamiento import AlmacenamientoLocal, get_almacenamiento
from app.services.reporte_service import TIPOS

R = "/api/v1/reportes"


@pytest.fixture(autouse=True)
def _almacen(tmp_path):
    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoLocal(tmp_path, "t" * 40, "http://testserver")


@pytest.fixture
def datos(client, db, seed):
    """Seed (2 atenciones de María en SURA) + una atención completa de Carlos con Nueva EPS y profesional."""
    nueva = Aseguradora(nombre="Nueva EPS")
    prof = Profesional(nombre="Dra. Gloria Alvarez", identificacion="555", correo="g@h.co")
    db.add_all([nueva, prof])
    db.flush()
    r = client.post(
        "/api/v1/atenciones",
        json={
            "id_paciente": str(seed["carlos"].public_id),
            "fecha_atencion": "2026-09-20",
            "id_aseguradora": nueva.id_aseguradora,
            "id_profesional": prof.id_profesional,
            "diagnostico_hospitalario": {"descripcion_original": "Tumor", "cod_4": "C187"},
            "diagnosticos_bucales": [{"descripcion": "Caries", "codigos": ["K021"]}],
        },
    )
    assert r.status_code == 201, r.text
    return {**seed, "nueva": nueva, "prof": prof}


def test_tipos_son_los_ocho_de_la_pantalla(client):
    tipos = client.get(f"{R}/tipos").json()
    assert len(tipos) == 8 and {t["tipo"] for t in tipos} == set(TIPOS)


@pytest.mark.parametrize("tipo", list(TIPOS))
def test_cada_reporte_responde_y_se_exporta_a_excel(client, datos, tipo):
    r = client.get(f"{R}/{tipo}")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["titulo"] == TIPOS[tipo][0] and (cuerpo["filas"] or tipo == "tratamientos_registrados")
    assert cuerpo["totales"] == {"pacientes": 2, "atenciones": 3, "imagenes": 0}
    x = client.get(f"{R}/{tipo}/excel")
    assert x.status_code == 200 and "attachment" in x.headers["content-disposition"]
    hoja = load_workbook(io.BytesIO(x.content)).active
    assert hoja["A1"].value == TIPOS[tipo][0]


def test_atenciones_por_aseguradora_con_porcentajes_y_hallazgo(client, datos):
    d = client.get(f"{R}/atenciones_por_aseguradora").json()
    assert [(f["etiqueta"], f["cantidad"], f["porcentaje"]) for f in d["filas"]] == [
        ("SURA", 2, 66.7),
        ("Nueva EPS", 1, 33.3),
    ]
    assert d["hallazgo"] == "SURA concentra el 66,7 % de los registros del periodo."


def test_filtros(client, datos):
    base = f"{R}/atenciones_por_aseguradora"
    assert client.get(base, params={"fecha_desde": "2026-09-01"}).json()["totales"]["atenciones"] == 2
    assert client.get(base, params={"fecha_hasta": "2026-08-31"}).json()["totales"]["atenciones"] == 1
    assert (
        client.get(base, params={"id_aseguradora": datos["nueva"].id_aseguradora}).json()["totales"]["atenciones"] == 1
    )
    assert (
        client.get(base, params={"id_profesional": datos["prof"].id_profesional}).json()["totales"]["atenciones"] == 1
    )
    assert client.get(base, params={"cod_4": "K02.1"}).json()["totales"]["atenciones"] == 1  # bucal
    assert client.get(base, params={"cod_4": "C187"}).json()["totales"]["atenciones"] == 1  # hospitalario
    vacio = client.get(base, params={"cod_4": "Z999"}).json()
    assert vacio["filas"] == [] and vacio["hallazgo"] is None and vacio["totales"]["atenciones"] == 0


def test_dx_hospitalario_bucales_y_relacion(client, datos):
    hosp = client.get(f"{R}/atenciones_por_diagnostico_hospitalario").json()["filas"]
    assert {f["etiqueta"] for f in hosp} == {"Sin diagnóstico hospitalario", "C187 · Tumor maligno del colon sigmoide"}
    bucales = client.get(f"{R}/distribucion_diagnosticos_bucales").json()["filas"]
    assert [(f["etiqueta"], f["cantidad"]) for f in bucales] == [("Caries", 1)]
    rel = client.get(f"{R}/relacion_hospitalario_bucal").json()
    assert rel["columna_secundaria"] == "Diagnóstico bucal"
    assert rel["filas"][0]["etiqueta_secundaria"] == "Caries"


def test_profesional_fecha_y_total(client, datos):
    prof = {f["etiqueta"]: f["cantidad"] for f in client.get(f"{R}/atenciones_por_profesional").json()["filas"]}
    assert prof == {"Sin profesional": 2, "Dra. Gloria Alvarez": 1}
    fechas = client.get(f"{R}/registros_por_fecha").json()
    assert [f["etiqueta"] for f in fechas["filas"]] == ["2026-08-18", "2026-09-12", "2026-09-20"]
    assert "2026-" in fechas["hallazgo"]
    total = client.get(f"{R}/total_atenciones").json()
    assert total["filas"][0]["cantidad"] == 3 and total["hallazgo"] is None


def test_tratamientos_cuentan_los_del_catalogo(client, db, datos):
    db.execute(text("INSERT INTO tratamiento (nombre) VALUES ('RX')"))
    db.execute(
        text(
            "INSERT INTO atencion_x_tratamiento SELECT a.id_atencion, t.id_tratamiento FROM atencion a, tratamiento t "
            "WHERE t.nombre = 'RX'"
        )
    )
    filas = client.get(f"{R}/tratamientos_registrados").json()["filas"]
    assert [(f["etiqueta"], f["cantidad"]) for f in filas] == [("RX", 3)]


def test_errores(client, datos):
    assert client.get(f"{R}/inexistente").status_code == 404
    assert client.get(f"{R}/inexistente/excel").status_code == 404
    assert (
        client.get(
            f"{R}/total_atenciones", params={"fecha_desde": "2026-10-01", "fecha_hasta": "2026-09-01"}
        ).status_code
        == 422
    )
    assert client.get(f"{R}/total_atenciones", params={"fecha_desde": "ayer"}).status_code == 422


def test_excel_neutraliza_formulas_de_datos_importados(client, db, datos):
    db.execute(text("UPDATE diagnostico_bucal SET descripcion = '=HYPERLINK(\"http://x\")'"))
    x = client.get(f"{R}/distribucion_diagnosticos_bucales/excel")
    hoja = load_workbook(io.BytesIO(x.content)).active
    celdas = [c.value for fila in hoja.iter_rows() for c in fila if isinstance(c.value, str)]
    assert not any(v.startswith("=") for v in celdas) and any(v.startswith("'=") for v in celdas)


def test_resumen_inicio(client, datos):
    d = client.get("/api/v1/inicio/resumen").json()
    assert d["totales"] == {"pacientes": 2, "atenciones": 3, "imagenes": 0, "diagnosticos": 2}
    assert d["atenciones_por_aseguradora"][0] == {"etiqueta": "SURA", "cantidad": 2}
    assert d["diagnosticos_bucales_frecuentes"] == [{"etiqueta": "Caries", "cantidad": 1}]
    assert len(d["ultimas_atenciones"]) == 3 and d["ultimas_atenciones"][0]["fecha_atencion"] == "2026-09-20"


def test_acceso_y_auditoria(client, datos, db):
    client.get(f"{R}/total_atenciones", params={"fecha_desde": "2026-01-01"})
    client.get(f"{R}/total_atenciones/excel")
    client.get("/api/v1/inicio/resumen")
    filas = db.execute(text("SELECT accion, detalle FROM auditoria ORDER BY id_evento")).all()
    acciones = [a for a, _ in filas]
    assert "generar_reporte" in acciones and "exportar_reporte" in acciones and "consultar_inicio" in acciones
    detalle = next(d for a, d in filas if a == "generar_reporte")
    assert detalle == {"tipo": "total_atenciones", "filtros": ["fecha_desde"]}


def test_reportes_exigen_personal_clinico(db):
    from fastapi.testclient import TestClient

    from app.core.security import CurrentUser, get_current_user
    from app.db.session import get_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(sub="x", email=None, roles=frozenset({"otro"}))
    c = TestClient(app)
    assert c.get(f"{R}/tipos").status_code == 403 and c.get("/api/v1/inicio/resumen").status_code == 403
    app.dependency_overrides.clear()
