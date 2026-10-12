def test_listado_con_agregados(client, seed):
    r = client.get("/api/v1/pacientes").json()
    assert r["total"] == 2
    primero = r["items"][0]  # orden: última atención más reciente primero
    assert primero["nombre"] == "María Rodríguez"
    assert primero["total_atenciones"] == 2 and primero["ultima_atencion"] == "2026-09-12"
    assert primero["codigo"].startswith("P-")


def test_busqueda_por_nombre_documento_y_codigo(client, seed):
    assert client.get("/api/v1/pacientes", params={"q": "rodr"}).json()["total"] == 1
    assert client.get("/api/v1/pacientes", params={"q": "1.025.847"}).json()["total"] == 1
    cod = client.get("/api/v1/pacientes", params={"q": "carlos"}).json()["items"][0]["codigo"]
    assert client.get("/api/v1/pacientes", params={"q": cod}).json()["items"][0]["nombre"] == "Carlos Gómez"


def test_q_no_interpreta_comodines(client, seed):
    assert client.get("/api/v1/pacientes", params={"q": "%"}).json()["total"] == 0


def test_filtros_sexo_documento_y_fecha(client, seed):
    assert client.get("/api/v1/pacientes", params={"sexo": "M"}).json()["total"] == 1
    assert client.get("/api/v1/pacientes", params={"documento": "1.025.847.210"}).json()["total"] == 1
    r = client.get("/api/v1/pacientes", params={"fecha_desde": "2026-09-01", "fecha_hasta": "2026-09-30"})
    assert [i["nombre"] for i in r.json()["items"]] == ["María Rodríguez"]


def test_paginacion(client, seed):
    r = client.get("/api/v1/pacientes", params={"page_size": 1, "page": 2}).json()
    assert r["total"] == 2 and len(r["items"]) == 1


def test_crear_normaliza_documento_y_devuelve_201(client):
    r = client.post(
        "/api/v1/pacientes",
        json={
            "tipo_documento": "CC",
            "documento_identidad": "52.880.143",
            "nombre": "  Ana   Martínez ",
            "sexo": "F",
            "correo": "ana@correo.co",
            "fecha_nacimiento": "1990-05-10",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["documento_identidad"] == "52880143" and body["nombre"] == "Ana Martínez"
    assert body["total_atenciones"] == 0 and body["edad"] >= 35


def test_documento_duplicado_es_409_aunque_cambie_el_formato(client, seed):
    r = client.post(
        "/api/v1/pacientes",
        json={"tipo_documento": "CC", "documento_identidad": "1.025.847.210", "nombre": "Otra Persona"},
    )
    assert r.status_code == 409


def test_validaciones_de_entrada(client):
    base = {"tipo_documento": "CC", "documento_identidad": "123456", "nombre": "Pedro Pérez"}
    assert client.post("/api/v1/pacientes", json={**base, "documento_identidad": "12"}).status_code == 422
    assert client.post("/api/v1/pacientes", json={**base, "tipo_documento": "XX"}).status_code == 422
    assert client.post("/api/v1/pacientes", json={**base, "sexo": "Z"}).status_code == 422
    assert client.post("/api/v1/pacientes", json={**base, "fecha_nacimiento": "2999-01-01"}).status_code == 422
    assert client.post("/api/v1/pacientes", json={**base, "correo": "no-es-correo"}).status_code == 422


def test_ficha_y_aseguradora_actual(client, seed):
    r = client.get(f"/api/v1/pacientes/{seed['maria'].id_paciente}").json()
    assert r["aseguradora_actual"] == "SURA" and r["ciudad"] == "Bogotá D.C." and r["edad"] >= 41
    assert client.get("/api/v1/pacientes/999999").status_code == 404


def test_editar_no_cambia_el_documento(client, seed):
    pid = seed["carlos"].id_paciente
    r = client.patch(f"/api/v1/pacientes/{pid}", json={"telefono": "3001234567", "documento_identidad": "1"})
    assert r.status_code == 200 and r.json()["telefono"] == "3001234567"
    assert r.json()["documento_identidad"] == "79421880"
