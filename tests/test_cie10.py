def test_buscar_por_prefijo_de_codigo_y_por_texto(client, seed):
    assert [i["cod_4"] for i in client.get("/api/v1/cie10", params={"q": "k02"}).json()["items"]] == ["K021"]
    assert [i["cod_4"] for i in client.get("/api/v1/cie10", params={"q": "colon"}).json()["items"]] == ["C187"]


def test_filtro_odontologico(client, seed):
    r = client.get("/api/v1/cie10", params={"odontologico": True}).json()
    assert r["total"] == 1 and r["items"][0]["cod_4"] == "K021"


def test_detalle_y_404(client, seed):
    assert client.get("/api/v1/cie10/k021").json()["descripcion_4"] == "Caries de la dentina"
    assert client.get("/api/v1/cie10/ZZZZ").status_code == 404

def test_busqueda_de_descripcion_ignora_tildes(client, seed, db):
    db.add(Cie10(cod_4="K051", cod_3="K05", descripcion_4="Gingivitis crónica", es_odontologico=True))
    db.flush()
    r = client.get("/api/v1/cie10", params={"q": "CRONICA"}).json()
    assert [i["cod_4"] for i in r["items"]] == ["K051"]