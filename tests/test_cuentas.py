"""Gestión de cuentas de profesionales: alta con cuenta, bloqueo, contraseña, rol y corte inmediato."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Profesional
from app.services.identidad_service import (
    IdentidadError,
    SupabaseIdentidad,
    UsuarioIdentidad,
    UsuarioYaExisteError,
    get_identidad,
    get_identidad_opcional,
)

C = "/api/v1/profesionales"
CLAVE = "ClaveSegura123"


class IdentidadFalsa:
    """Proveedor de identidad en memoria: las pruebas nunca llaman a Supabase."""

    def __init__(self):
        self.usuarios: dict[str, UsuarioIdentidad] = {}
        self.passwords: dict[str, str] = {}
        self.borrados: list[str] = []
        self.falla_borrar = False

    def agregar(self, uid, email, rol, bloqueado=False):
        self.usuarios[uid] = UsuarioIdentidad(uid, email, (rol,), bloqueado)

    def crear_usuario(self, email, password, rol):
        if any(u.email == email for u in self.usuarios.values()):
            raise UsuarioYaExisteError("Ya existe una cuenta con ese correo")
        uid = f"uid-{len(self.usuarios) + 1}"
        self.agregar(uid, email, rol)
        self.passwords[uid] = password
        return uid

    def listar_usuarios(self):
        return list(self.usuarios.values())

    def cambiar_password(self, uid, password):
        self.passwords[uid] = password

    def cambiar_rol(self, uid, rol):
        u = self.usuarios[uid]
        self.usuarios[uid] = UsuarioIdentidad(uid, u.email, (rol,), u.bloqueado)

    def bloquear(self, uid, bloqueado):
        u = self.usuarios[uid]
        self.usuarios[uid] = UsuarioIdentidad(uid, u.email, u.roles, bloqueado)

    def borrar_usuario(self, uid):
        if self.falla_borrar:
            raise IdentidadError("falló")
        self.borrados.append(uid)
        self.usuarios.pop(uid, None)


@pytest.fixture
def idp():
    return IdentidadFalsa()


@pytest.fixture
def admin(db, idp):
    """Administrador 'auth|admin' (sin profesional enlazado, como la cuenta inicial)."""
    idp.agregar("auth|admin", "admin@h.co", "administrador")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_identidad] = lambda: idp
    app.dependency_overrides[get_identidad_opcional] = lambda: idp
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="auth|admin", email="admin@h.co", roles=frozenset({"administrador"})
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _datos(**extra):
    base = {"nombre": "Dra. Ana Pérez", "identificacion": "5551", "correo": "ANA@H.co", "password": CLAVE}
    base.update(extra)
    return base


def test_crear_profesional_con_cuenta(admin, idp, db):
    r = admin.post(f"{C}/cuenta", json=_datos(especializacion="Endodoncia"))
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["tiene_cuenta"], d["rol"], d["activo"], d["correo"]) == (True, "odontologo", True, "ana@h.co")
    assert "password" not in d and CLAVE not in r.text
    assert d["auth_id"] in idp.passwords and idp.passwords[d["auth_id"]] == CLAVE
    assert db.query(Profesional).filter_by(auth_id=d["auth_id"]).one().nombre == "Dra. Ana Pérez"


def test_crear_administrador(admin):
    r = admin.post(f"{C}/cuenta", json=_datos(rol="administrador"))
    assert r.status_code == 201 and r.json()["rol"] == "administrador"
    assert admin.post(f"{C}/cuenta", json=_datos(identificacion="9", correo="x@h.co", rol="otro")).status_code == 422


@pytest.mark.parametrize("password", ["corta1", "SoloLetrasLargas", "12345678901234", " ConEspacios123 ", "A1" * 40])
def test_contrasena_debil_o_invalida(admin, password):
    r = admin.post(f"{C}/cuenta", json=_datos(password=password))
    assert r.status_code == 422
    assert password not in r.text  # el 422 no repite la contraseña enviada


def test_duplicados_409_y_no_deja_cuentas_huerfanas(admin, idp):
    admin.post(f"{C}/cuenta", json=_datos())
    antes = len(idp.usuarios)
    assert admin.post(f"{C}/cuenta", json=_datos(correo="otro@h.co")).status_code == 409  # mismo documento
    assert admin.post(f"{C}/cuenta", json=_datos(identificacion="7777")).status_code == 409  # mismo correo
    assert len(idp.usuarios) == antes


def test_correo_ya_existente_en_el_proveedor_409(admin, idp):
    idp.agregar("u-x", "libre@h.co", "odontologo")  # existe en el IdP pero no como profesional
    assert admin.post(f"{C}/cuenta", json=_datos(correo="libre@h.co")).status_code == 409


def test_si_falla_el_alta_se_deshace_la_cuenta(admin, idp, db, monkeypatch):
    from app.repositories import catalogo_repo

    def explota(*a, **k):
        raise RuntimeError("fallo de base de datos")

    monkeypatch.setattr(catalogo_repo, "agregar", explota)
    with pytest.raises(RuntimeError):
        admin.post(f"{C}/cuenta", json=_datos())
    assert idp.borrados == ["uid-2"]


def test_lista_de_gestion_trae_rol_y_estado(admin, idp, db):
    admin.post(f"{C}/cuenta", json=_datos())
    db.add(Profesional(nombre="Sin cuenta", identificacion="123456", correo="s@h.co"))
    db.flush()
    filas = {f["nombre"]: f for f in admin.get(f"{C}/gestion").json()}
    assert filas["Dra. Ana Pérez"]["rol"] == "odontologo" and filas["Dra. Ana Pérez"]["tiene_cuenta"]
    assert filas["Sin cuenta"]["tiene_cuenta"] is False and filas["Sin cuenta"]["rol"] is None


def test_desactivar_bloquea_la_cuenta_y_reactivar_la_libera(admin, idp):
    d = admin.post(f"{C}/cuenta", json=_datos()).json()
    r = admin.patch(f"{C}/{d['id_profesional']}", json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    assert idp.usuarios[d["auth_id"]].bloqueado is True
    assert admin.get(f"{C}/gestion").json()[-1]["cuenta_bloqueada"] is True
    admin.patch(f"{C}/{d['id_profesional']}", json={"activo": True})
    assert idp.usuarios[d["auth_id"]].bloqueado is False


def test_profesional_inactivo_pierde_acceso_de_inmediato(db, idp):
    """Punto 4: aunque su token siga vigente, un profesional inactivo recibe 403."""
    db.add(Profesional(nombre="Dr Fuera", identificacion="8888", correo="f@h.co", auth_id="auth|fuera", activo=False))
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="auth|fuera", email=None, roles=frozenset({"odontologo"})
    )
    try:
        r = TestClient(app).get("/api/v1/pacientes")
        assert r.status_code == 403 and r.json()["detail"] == "Cuenta desactivada"
    finally:
        app.dependency_overrides.clear()


def test_cuenta_sin_profesional_enlazado_no_se_bloquea(client):
    assert client.get("/api/v1/pacientes").status_code == 200


def test_no_puede_desactivarse_a_si_mismo_ni_quedar_sin_admins(db, admin, idp):
    db.add(Profesional(nombre="Yo Admin", identificacion="4444", correo="yo@h.co", auth_id="auth|admin"))
    db.flush()
    yo = db.query(Profesional).filter_by(auth_id="auth|admin").one()
    assert admin.patch(f"{C}/{yo.id_profesional}", json={"activo": False}).status_code == 409
    assert admin.put(f"{C}/{yo.id_profesional}/rol", json={"rol": "odontologo"}).status_code == 409
    otro = admin.post(f"{C}/cuenta", json=_datos(rol="administrador")).json()
    idp.bloquear("auth|admin", True)  # el único otro administrador queda bloqueado
    assert admin.put(f"{C}/{otro['id_profesional']}/rol", json={"rol": "odontologo"}).status_code == 409
    assert admin.patch(f"{C}/{otro['id_profesional']}", json={"activo": False}).status_code == 409
    idp.bloquear("auth|admin", False)
    ok = admin.put(f"{C}/{otro['id_profesional']}/rol", json={"rol": "odontologo"})
    assert ok.status_code == 200 and ok.json()["rol"] == "odontologo"


def test_cambiar_password_y_rol(admin, idp):
    d = admin.post(f"{C}/cuenta", json=_datos()).json()
    nueva = "OtraClave987654"
    assert admin.put(f"{C}/{d['id_profesional']}/password", json={"password": nueva}).status_code == 204
    assert idp.passwords[d["auth_id"]] == nueva
    assert admin.put(f"{C}/{d['id_profesional']}/password", json={"password": "corta"}).status_code == 422
    assert admin.put(f"{C}/{d['id_profesional']}/rol", json={"rol": "administrador"}).json()["rol"] == "administrador"
    assert admin.put(f"{C}/999999/password", json={"password": nueva}).status_code == 404
    assert admin.put(f"{C}/999999/rol", json={"rol": "odontologo"}).status_code == 404


def test_cuenta_para_profesional_existente(admin, db, idp):
    db.add(Profesional(nombre="Dr Existente", identificacion="3333", correo="Ex@h.co"))
    db.flush()
    p = db.query(Profesional).filter_by(identificacion="3333").one()
    r = admin.post(f"{C}/{p.id_profesional}/cuenta", json={"password": CLAVE})
    assert r.status_code == 201 and r.json()["tiene_cuenta"] and idp.usuarios[r.json()["auth_id"]].email == "ex@h.co"
    assert admin.post(f"{C}/{p.id_profesional}/cuenta", json={"password": CLAVE}).status_code == 409  # ya tiene
    assert admin.post(f"{C}/999999/cuenta", json={"password": CLAVE}).status_code == 404
    sin = admin.put(f"{C}/{p.id_profesional}/rol", json={"rol": "odontologo"})
    assert sin.status_code == 200
    db.add(Profesional(nombre="Dr Sin", identificacion="2222", correo="sin@h.co"))
    db.flush()
    s = db.query(Profesional).filter_by(identificacion="2222").one()
    assert admin.put(f"{C}/{s.id_profesional}/password", json={"password": CLAVE}).status_code == 422
    assert admin.put(f"{C}/{s.id_profesional}/rol", json={"rol": "odontologo"}).status_code == 422


def test_solo_administrador_y_auditoria_sin_secretos(client, admin, db):
    admin.post(f"{C}/cuenta", json=_datos())
    filas = db.execute(text("SELECT accion, detalle::text FROM auditoria ORDER BY id_evento")).all()
    assert filas[0][0] == "crear_cuenta_profesional" and filas[0][1] == '{"rol": "odontologo"}'
    assert CLAVE not in json.dumps([list(f) for f in filas]) and "ana@h.co" not in json.dumps([list(f) for f in filas])


def test_odontologo_no_gestiona_cuentas(db, idp):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_identidad] = lambda: idp
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="u", email=None, roles=frozenset({"odontologo"})
    )
    try:
        c = TestClient(app)
        assert c.get(f"{C}/gestion").status_code == 403
        assert c.post(f"{C}/cuenta", json=_datos()).status_code == 403
        assert c.put(f"{C}/1/rol", json={"rol": "administrador"}).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_sin_llave_de_servicio_la_gestion_responde_503(db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        sub="a", email=None, roles=frozenset({"administrador"})
    )
    try:
        assert TestClient(app).get(f"{C}/gestion").status_code == 503
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_proveedor_caido_502(admin, idp):
    def cae(*a, **k):
        raise IdentidadError("No se pudo comunicar con el proveedor de identidad", sin_conexion=True)

    idp.listar_usuarios = cae
    assert admin.get(f"{C}/gestion").status_code == 502


def test_proveedor_rechaza_la_clave_422(admin, idp):
    def debil(*a, **k):
        raise IdentidadError("La contraseña es demasiado débil para la política del proveedor de identidad")

    idp.crear_usuario = debil
    assert admin.post(f"{C}/cuenta", json=_datos()).status_code == 422


# --- cliente HTTP de Supabase (con transporte simulado) -------------------------------------------------------


def _cliente(manejador):
    return SupabaseIdentidad("https://x.supabase.co", "LLAVE", transport=httpx.MockTransport(manejador))


def test_cliente_supabase_crea_y_lista_y_actualiza():
    visto = []

    def manejador(req: httpx.Request):
        visto.append((req.method, req.url.path, json.loads(req.content) if req.content else None, req.headers))
        if req.method == "POST":
            return httpx.Response(200, json={"id": "abc"})
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "users": [
                        {
                            "id": "1",
                            "email": "a@h.co",
                            "app_metadata": {"roles": ["administrador"]},
                            "banned_until": None,
                        },
                        {"id": "2", "email": "b@h.co", "app_metadata": {}, "banned_until": "2999-01-01T00:00:00Z"},
                    ]
                },
            )
        return httpx.Response(200, json={})

    c = _cliente(manejador)
    assert c.crear_usuario("a@h.co", CLAVE, "odontologo") == "abc"
    metodo, ruta, cuerpo, cab = visto[0]
    assert ruta == "/auth/v1/admin/users" and cab["authorization"] == "Bearer LLAVE" and cab["apikey"] == "LLAVE"
    assert cuerpo == {
        "email": "a@h.co",
        "password": CLAVE,
        "email_confirm": True,
        "app_metadata": {"roles": ["odontologo"]},
    }
    u = c.listar_usuarios()
    assert u[0].roles == ("administrador",) and not u[0].bloqueado and u[1].bloqueado and u[1].roles == ()
    c.cambiar_password("1", CLAVE)
    c.cambiar_rol("1", "odontologo")
    c.bloquear("1", True)
    c.bloquear("1", False)
    c.borrar_usuario("1")
    cuerpos = [v[2] for v in visto[2:]]
    assert cuerpos[0] == {"password": CLAVE} and cuerpos[1] == {"app_metadata": {"roles": ["odontologo"]}}
    assert cuerpos[2] == {"ban_duration": "876000h"} and cuerpos[3] == {"ban_duration": "none"}
    assert visto[-1][0] == "DELETE"


@pytest.mark.parametrize(
    ("estado", "cuerpo", "clase", "mensaje"),
    [
        (422, {"error_code": "email_exists"}, UsuarioYaExisteError, "correo"),
        (422, {"error_code": "weak_password"}, IdentidadError, "débil"),
        (401, {}, IdentidadError, "no está autorizado"),
        (404, {}, IdentidadError, "no existe"),
        (500, {}, IdentidadError, "rechazó"),
    ],
)
def test_cliente_supabase_traduce_errores_sin_filtrar_detalles(estado, cuerpo, clase, mensaje):
    c = _cliente(lambda req: httpx.Response(estado, json=cuerpo))
    with pytest.raises(clase) as exc:
        c.cambiar_password("1", CLAVE)
    assert mensaje in str(exc.value) and "LLAVE" not in str(exc.value)


def test_cliente_supabase_sin_conexion_y_respuesta_no_json():
    def cae(req):
        raise httpx.ConnectError("sin red")

    with pytest.raises(IdentidadError) as exc:
        _cliente(cae).listar_usuarios()
    assert exc.value.sin_conexion
    with pytest.raises(IdentidadError):
        _cliente(lambda req: httpx.Response(400, text="<html>")).bloquear("1", True)
