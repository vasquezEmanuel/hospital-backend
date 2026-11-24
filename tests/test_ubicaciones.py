"""Departamento y municipio (schema v1.6): catálogos DANE, selección en el paciente y reglas de coherencia."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

P = "/api/v1/pacientes"


def _nuevo(**extra):
    return {"tipo_documento": "CC", "documento_identidad": "52.000.111", "nombre": "Paciente Ubicación", **extra}


def test_el_catalogo_dane_esta_completo_y_es_coherente(db):
    assert db.execute(text("SELECT count(*) FROM departamento")).scalar_one() == 33
    assert db.execute(text("SELECT count(*) FROM municipio")).scalar_one() == 1122
    assert db.execute(text("SELECT nombre FROM municipio WHERE codigo = '76001'")).scalar_one() == "Santiago de Cali"
    # cada municipio pertenece al departamento que dicen sus dos primeros dígitos
    assert (
        db.execute(text("SELECT count(*) FROM municipio WHERE substr(codigo,1,2) <> codigo_departamento")).scalar_one()
        == 0
    )


def test_la_base_rechaza_un_municipio_con_departamento_incoherente(db):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("INSERT INTO municipio (codigo, nombre, codigo_departamento) VALUES ('76999', 'X', '05')"))


def test_listar_departamentos(client):
    r = client.get("/api/v1/departamentos")
    assert r.status_code == 200
    deptos = r.json()
    assert len(deptos) == 33
    assert {"codigo": "76", "nombre": "Valle del Cauca"} in deptos
    assert {"codigo": "11", "nombre": "Bogotá, D.C."} in deptos
    nombres = [d["nombre"] for d in deptos]
    assert nombres[0] == "Amazonas" and nombres[-1] == "Vichada"


def test_municipios_de_un_departamento(client):
    r = client.get("/api/v1/departamentos/76/municipios")
    assert r.status_code == 200
    munis = r.json()
    assert len(munis) == 42
    assert all(m["codigo_departamento"] == "76" and m["departamento"] == "Valle del Cauca" for m in munis)
    assert {
        "codigo": "76001",
        "nombre": "Santiago de Cali",
        "codigo_departamento": "76",
        "departamento": "Valle del Cauca",
    } in munis
    assert client.get("/api/v1/departamentos/00/municipios").status_code == 404
    assert client.get("/api/v1/departamentos/abc/municipios").status_code == 422


def test_buscar_municipios_sin_tildes_ni_mayusculas(client):
    r = client.get("/api/v1/municipios", params={"q": "MEDELL"}).json()
    assert [m["codigo"] for m in r] == ["05001"]
    r = client.get("/api/v1/municipios", params={"q": "bogota"}).json()
    assert r[0]["codigo"] == "11001" and r[0]["departamento"] == "Bogotá, D.C."
    # el mismo nombre en distintos departamentos se distingue por el filtro
    todos = client.get("/api/v1/municipios", params={"q": "san jose"}).json()
    assert len({m["codigo_departamento"] for m in todos}) > 1
    solo = client.get("/api/v1/municipios", params={"q": "san jose", "codigo_departamento": "95"}).json()
    assert solo and all(m["codigo_departamento"] == "95" for m in solo)
    assert len(client.get("/api/v1/municipios", params={"q": "san", "limite": 5}).json()) == 5
    assert "76001" in [
        m["codigo"] for m in client.get("/api/v1/municipios", params={"q": "cali"}).json()
    ]  # el nombre oficial es «Santiago de Cali»
    assert client.get("/api/v1/municipios", params={"q": "a"}).status_code == 422  # muy corto
    assert client.get("/api/v1/municipios", params={"q": "zzzzzz"}).json() == []


def test_catalogos_de_ubicacion_exigen_personal_clinico(anon_client):
    assert anon_client.get("/api/v1/departamentos").status_code in (401, 403)
    assert anon_client.get("/api/v1/municipios", params={"q": "cali"}).status_code in (401, 403)


def test_crear_paciente_con_municipio_deduce_departamento_y_ciudad(client):
    r = client.post(P, json=_nuevo(codigo_municipio="76001"))
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["codigo_municipio"], p["municipio"], p["ciudad"]) == ("76001", "Santiago de Cali", "Santiago de Cali")
    assert (p["codigo_departamento"], p["departamento"]) == ("76", "Valle del Cauca")
    ficha = client.get(f"{P}/{p['id_paciente']}").json()
    assert ficha["departamento"] == "Valle del Cauca" and ficha["municipio"] == "Santiago de Cali"


def test_el_municipio_manda_sobre_el_texto_de_ciudad(client):
    p = client.post(P, json=_nuevo(codigo_municipio="05001", ciudad="otra cosa")).json()
    assert p["ciudad"] == "Medellín" and p["departamento"] == "Antioquia"


def test_ciudad_como_texto_libre_cuando_no_hay_municipio(client):
    p = client.post(P, json=_nuevo(ciudad="Quito, Ecuador")).json()
    assert p["ciudad"] == "Quito, Ecuador"
    assert p["codigo_municipio"] is None and p["departamento"] is None and p["municipio"] is None


def test_municipio_invalido_se_rechaza(client):
    assert client.post(P, json=_nuevo(codigo_municipio="99999")).status_code == 422  # formato válido, no existe
    assert client.post(P, json=_nuevo(codigo_municipio="760")).status_code == 422
    assert client.post(P, json=_nuevo(codigo_municipio="Cali")).status_code == 422
    assert client.get(P, params={"documento": "52000111"}).json()["total"] == 0  # no quedó registrado


def test_editar_la_ubicacion_del_paciente(client):
    pid = client.post(P, json=_nuevo(codigo_municipio="76001")).json()["id_paciente"]
    r = client.patch(f"{P}/{pid}", json={"codigo_municipio": "08001"}).json()
    assert (r["municipio"], r["departamento"], r["ciudad"]) == ("Barranquilla", "Atlántico", "Barranquilla")
    r = client.patch(f"{P}/{pid}", json={"telefono": "3001234567"}).json()  # otro campo no toca la ubicación
    assert r["municipio"] == "Barranquilla"
    r = client.patch(f"{P}/{pid}", json={"codigo_municipio": None}).json()  # quitar la ubicación
    assert r["codigo_municipio"] is None and r["departamento"] is None and r["ciudad"] is None
    r = client.patch(f"{P}/{pid}", json={"codigo_municipio": None, "ciudad": "Madrid, España"}).json()
    assert r["ciudad"] == "Madrid, España" and r["departamento"] is None
    assert client.patch(f"{P}/{pid}", json={"codigo_municipio": "99999"}).status_code == 422
    assert client.get(f"{P}/{pid}").json()["ciudad"] == "Madrid, España"


def test_la_edicion_de_ubicacion_se_audita_sin_valores(client, db):
    pid = client.post(P, json=_nuevo()).json()["id_paciente"]
    client.patch(f"{P}/{pid}", json={"codigo_municipio": "76001", "documento_identidad": "52.000.222"})
    detalle = str(db.execute(text("SELECT detalle FROM auditoria WHERE accion = 'editar_paciente'")).all())
    assert "codigo_municipio" in detalle and "documento_identidad" in detalle
    assert "76001" not in detalle and "52000222" not in detalle  # nombres de campos, nunca valores
