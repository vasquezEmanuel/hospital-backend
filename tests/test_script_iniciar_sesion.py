"""Prueba de scripts/iniciar_sesion.py contra un Supabase Auth simulado en un servidor HTTP local (sin red externa)."""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts.iniciar_sesion import ErrorSupabase, iniciar_sesion, main


class _Estado:
    factores: list[dict] = []
    borrados: list[str] = []


def _handler(estado: _Estado):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _enviar(self, codigo, obj):
            b = json.dumps(obj).encode()
            self.send_response(codigo)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _cuerpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            self._enviar(200, {"factors": estado.factores})

        def do_DELETE(self):
            estado.borrados.append(self.path.rsplit("/", 1)[1])
            self._enviar(200, {})

        def do_POST(self):
            b = self._cuerpo()
            if self.path.startswith("/auth/v1/token"):
                if b.get("password") != "bien":
                    return self._enviar(400, {"msg": "Invalid login credentials"})
                return self._enviar(200, {"access_token": "tok-aal1"})
            if self.path.endswith("/factors"):
                return self._enviar(200, {"id": "f-nuevo", "totp": {"secret": "SECRETO123"}})
            if self.path.endswith("/challenge"):
                return self._enviar(200, {"id": str(uuid.uuid4())})
            if self.path.endswith("/verify"):
                if b.get("code") != "123456" or not b.get("challenge_id"):
                    return self._enviar(400, {"msg": "Invalid TOTP code entered"})
                return self._enviar(200, {"access_token": "tok-aal2"})
            self._enviar(404, {})

    return H


@pytest.fixture
def supabase():
    estado = _Estado()
    estado.factores, estado.borrados = [], []
    srv = HTTPServer(("127.0.0.1", 0), _handler(estado))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", estado
    srv.shutdown()


def test_primera_vez_inscribe_el_totp_y_devuelve_aal2(supabase):
    url, estado = supabase
    estado.factores = [{"id": "viejo", "factor_type": "totp", "status": "unverified"}]
    avisos: list[str] = []
    r = iniciar_sesion(url, "k", "a@x.test", "bien", lambda: "123456", avisos.append)
    assert r == {"token": "tok-aal2", "aal": "aal2"}
    assert estado.borrados == ["viejo"]  # la inscripción a medias se limpia
    assert "SECRETO123" in avisos[0]


def test_usuario_con_factor_verificado_no_reinscribe(supabase):
    url, estado = supabase
    estado.factores = [{"id": "f1", "factor_type": "totp", "status": "verified"}]
    avisos: list[str] = []
    r = iniciar_sesion(url, "k", "a@x.test", "bien", lambda: "123456", avisos.append)
    assert r["aal"] == "aal2" and avisos == [] and estado.borrados == []


def test_codigo_incorrecto_lanza_error_legible(supabase):
    url, estado = supabase
    estado.factores = [{"id": "f1", "factor_type": "totp", "status": "verified"}]
    with pytest.raises(ErrorSupabase, match="Invalid TOTP"):
        iniciar_sesion(url, "k", "a@x.test", "bien", lambda: "000000")


def test_sin_mfa_devuelve_aal1(supabase):
    url, _ = supabase
    assert iniciar_sesion(url, "k", "a@x.test", "bien", lambda: "", segundo_factor=False) == {
        "token": "tok-aal1",
        "aal": "aal1",
    }


def test_main_contrasena_incorrecta_sale_con_1(supabase, monkeypatch, capsys):
    url, _ = supabase
    monkeypatch.setattr("getpass.getpass", lambda _: "mal")
    assert main(["--url", url, "--key", "k", "--email", "a@x.test"]) == 1
    assert "Invalid login credentials" in capsys.readouterr().out


def test_main_exitoso_muestra_el_token(supabase, monkeypatch, capsys):
    url, estado = supabase
    estado.factores = [{"id": "f1", "factor_type": "totp", "status": "verified"}]
    monkeypatch.setattr("getpass.getpass", lambda _: "bien")
    monkeypatch.setattr("builtins.input", lambda _: "123456")
    monkeypatch.setattr("scripts.iniciar_sesion._copiar", lambda t: False)
    assert main(["--url", url, "--key", "k", "--email", "a@x.test"]) == 0
    assert "tok-aal2" in capsys.readouterr().out


def test_servidor_inalcanzable_da_error_legible():
    with pytest.raises(ErrorSupabase, match="No se pudo conectar"):
        iniciar_sesion("http://127.0.0.1:1", "k", "a@x.test", "x", lambda: "")
