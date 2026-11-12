import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

import pytest

from jeventas import ejemplos

HIST = [
    {"texto": "Cliente: Hola, me mudo la semana que viene, busco baulera en Palermo\nVentas: ¡Hola! Te paso opciones para Palermo. ¿Qué vas a guardar?\nCliente: Un 2 ambientes. Dale, lo quiero",
     "resultado": "alquilo", "ultimo_hace_horas": 100},
    {"texto": "Cliente: Hola, me mudo la semana que viene, busco baulera en Palermo\nVentas: Hola. Precios en la web.",
     "resultado": "no_alquilo", "ultimo_hace_horas": 100},
]


def test_historial_da_ejemplos_al_redactor(panel_tmp):
    _, acc = panel_tmp
    r = acc.agregar_lote(HIST, "hist", usar_jev_real=False, tipo="historial")
    assert acc.cargar_lote(r["lote"])["meta"]["tipo"] == "historial"
    casos = ejemplos.casos(acc.OUT)
    assert {c["resultado"] for c in casos} == {"alquilo", "no_alquilo"}
    cat = casos[0]["categoria"]
    ej = ejemplos.para_categoria(acc.OUT, cat)
    assert ej["buenos"] and "Te paso opciones" in ej["buenos"][0]["respuesta_ventas"]
    assert ej["malos"] and "Precios en la web" in ej["malos"][0]["respuesta_ventas"]
    bloque = ejemplos.bloque_prompt(ej)
    assert "FUNCIONÓ" in bloque and "NO FUNCIONÓ" in bloque
    est = acc.historial()["por_categoria"][cat]
    assert est["casos"] == 2 and est["alquilaron"] == 1
    # un lote actual no aporta ejemplos
    acc.agregar_lote(HIST, "actual", usar_jev_real=False)
    assert len(ejemplos.casos(acc.OUT)) == len(casos)


def test_redactor_ia_recibe_ejemplos(panel_tmp, monkeypatch):
    _, acc = panel_tmp
    acc.agregar_lote(HIST, "hist", usar_jev_real=False, tipo="historial")
    from jeventas import proveedores, redactor

    recibido = {}

    class IA:
        modelo = "falso"

        def generar(self, sistema, usuario):
            recibido["u"] = usuario
            return "¡Hola! ¿Qué vas a guardar?"

    monkeypatch.setattr(proveedores, "crear", lambda p, a=None: IA())
    cat = ejemplos.casos(acc.OUT)[0]["categoria"]
    red = redactor.RedactorIA({"sedes": {}}, "openai", True, dir_historial=acc.OUT)
    out = red.redactar([{"de": "Prospecto", "texto": "hola"}], {"categoria": {"id": cat}, "datos_faltantes": [], "alertas": []})
    assert "<ejemplos_historial>" in recibido["u"] and out["ejemplos_historial"]["buenos"] >= 1


@pytest.fixture
def servidor(panel_tmp, monkeypatch):
    srv, _ = panel_tmp
    monkeypatch.setattr(srv.Acceso, "RUTA", srv.RAIZ / "config" / "acceso.local.json")
    s = srv.servir(0, "Alberto", "clave-de-prueba", guardar=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}", srv
    s.shutdown()
    srv.ACCESO.activar(None, None)


def _abrir(url, datos=None, jar=None):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar if jar is not None else CookieJar()))
    return op.open(url, data=datos)


def test_login_protege_todo(servidor):
    base, srv = servidor
    with pytest.raises(urllib.error.HTTPError) as e:
        _abrir(base + "/api/corridas")
    assert e.value.code == 401
    assert "/login" in _abrir(base + "/").geturl()  # redirige a la página de login
    with pytest.raises(urllib.error.HTTPError):
        _abrir(base + "/login", urllib.parse.urlencode({"usuario": "Alberto", "clave": "mal"}).encode())
    jar = CookieJar()
    _abrir(base + "/login", urllib.parse.urlencode({"usuario": "alberto", "clave": "clave-de-prueba"}).encode(), jar)
    assert json.loads(_abrir(base + "/api/corridas", jar=jar).read()) == []
    guardado = json.loads((srv.RAIZ / "config" / "acceso.local.json").read_text(encoding="utf-8"))
    assert "clave-de-prueba" not in json.dumps(guardado) and guardado["usuario"] == "alberto"
