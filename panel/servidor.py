"""Servidor local del panel de JeVentas (solo stdlib, solo en esta computadora).

    python scripts/abrir_panel.py            # abre http://127.0.0.1:8765

Escucha solo en 127.0.0.1. No envía mensajes a clientes ni toca HubSpot/Atom.
Las operaciones están en panel/acciones.py (las comparten los botones y el chat).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sys
import time
from http.cookies import SimpleCookie
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from jeventas import ajustes, asistente  # noqa: E402
from jeventas.importar import COLUMNAS_MENSAJES, desde_csv, desde_whatsapp_txt  # noqa: E402
from jeventas.modelo import leer_jsonl  # noqa: E402
from jeventas.proveedores import ErrorProveedor  # noqa: E402
from panel import acciones  # noqa: E402
from panel.acciones import ErrorPanel, cargar_lote, carpeta, escribir_json, leer_json  # noqa: E402

OUT = acciones.OUT
ESTATICOS = Path(__file__).resolve().parent / "static"
NOMBRE_OK = acciones.NOMBRE_OK

# compatibilidad con el nombre anterior
cargar_corrida = cargar_lote
listar_corridas = acciones.listar_lotes


def guardar_revision(datos: dict) -> dict:
    d = carpeta(datos.get("corrida", ""))
    k = datos.get("clave")
    if not k or not isinstance(k, str):
        raise ErrorPanel("Falta la recomendación a revisar.")
    with acciones._candado:
        rev = leer_json(d / "revisiones.json", {})
        if datos.get("revision") is None:
            rev.pop(k, None)
        else:
            r = datos["revision"]
            rev[k] = {
                "segmento_ok": r.get("segmento_ok") if r.get("segmento_ok") in ("si", "no") else None,
                "segmento_correcto": r.get("segmento_correcto") or None,
                "sugerencia_nota": r.get("sugerencia_nota") if r.get("sugerencia_nota") in (1, 2, 3, 4, 5) else None,
                "comentario": (r.get("comentario") or "")[:2000],
                "fecha": datetime.now().isoformat(timespec="seconds"),
            }
        escribir_json(d / "revisiones.json", rev)
    return {"ok": True, "revisadas": len(rev)}


def revisiones_csv(nombre: str) -> str:
    c = cargar_lote(nombre)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id_consulta", "momento", "evaluado_en", "categoria_sistema", "clasificacion_ok", "categoria_correcta",
                "accion", "nota_sugerencia", "comentario", "fecha_revision"])
    for r in c["recomendaciones"]:
        v = c["revisiones"].get(r["clave"])
        if not v:
            continue
        cat = (r["clasificacion"].get("categoria") or {}).get("nombre") or r["clasificacion"].get("segmento")
        w.writerow([r["id_consulta"], r["punto"], r["evaluado_en"], cat, v["segmento_ok"], v["segmento_correcto"] or "",
                    r["accion"]["tipo"], v["sugerencia_nota"] or "", v["comentario"], v["fecha"]])
    return "﻿" + buf.getvalue()


def _es_csv_de_mensajes(texto: str) -> bool:
    cab = [c.strip().lower() for c in next(csv.reader(io.StringIO(texto)), [])]
    return any(a in cab for a in COLUMNAS_MENSAJES["texto"])


def _aplicar_resultados(chats: dict, ruta_csv: Path) -> None:
    """CSV de resultados para chats de WhatsApp: columna 'archivo' (nombre del .txt) + 'resultado'
    (alquiló / no alquiló / desconocido) y, opcionalmente, zona_formulario, campania, etc."""
    sensibles = {"nombre", "telefono", "email", "dni", "cuit", "archivo", "resultado"}
    with open(ruta_csv, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    if filas and "archivo" not in filas[0]:
        raise ErrorPanel("El CSV de resultados necesita una columna 'archivo' con el nombre de cada chat .txt.")
    for fila in filas:
        c = chats.get(Path(fila.get("archivo", "")).stem)
        if not c:
            continue
        res = (fila.get("resultado") or "").strip().lower().replace(" ", "_").replace("ó", "o")
        c.resultado = {"estado": res if res in ("alquilo", "no_alquilo") else "desconocido"}
        if fila.get("campania"):
            c.origen["campania"] = fila["campania"]
        c.propiedades.update({k: v for k, v in fila.items() if k not in sensibles and k != "campania" and v})


def importar(datos: dict) -> dict:
    """Archivos exportados (.txt de WhatsApp, CSV de mensajes, CSV de resultados, .jsonl)."""
    archivos = datos.get("archivos") or []
    if not archivos:
        raise ErrorPanel("Elegí al menos un archivo exportado.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_export = RAIZ / "export" / f"panel_{ts}"
    dir_export.mkdir(parents=True, exist_ok=True)
    nombres_ventas = [n.strip() for n in (datos.get("nombres_ventas") or "").split(",") if n.strip()]

    consultas, csv_mensajes, csv_consultas = [], None, None
    chats: dict = {}
    for a in archivos:
        nombre = re.sub(r"[^\w.-]", "_", Path(a.get("nombre", "archivo")).name)
        ruta = dir_export / nombre
        ruta.write_text(a.get("contenido", ""), encoding="utf-8")
        ext = ruta.suffix.lower()
        if ext == ".txt":
            if not nombres_ventas:
                raise ErrorPanel("Para chats de WhatsApp, escribí cómo aparece Don Box en el chat (por ejemplo: Don Box).")
            c = desde_whatsapp_txt(ruta, nombres_ventas)
            chats[ruta.stem] = c
            consultas.append(c)
        elif ext == ".jsonl":
            consultas.extend(leer_jsonl(ruta))
        elif ext == ".csv":
            if _es_csv_de_mensajes(a.get("contenido", "")):
                csv_mensajes = ruta
            else:
                csv_consultas = ruta
        else:
            raise ErrorPanel(f"No sé leer '{nombre}'. Formatos aceptados: .csv, .txt (chat de WhatsApp) y .jsonl.")
    if csv_consultas and not csv_mensajes:
        if not chats:
            raise ErrorPanel("Falta el CSV de mensajes (una fila por mensaje, con columna de texto).")
        _aplicar_resultados(chats, csv_consultas)
    elif csv_mensajes:
        consultas.extend(desde_csv(csv_mensajes, csv_consultas))
    if not consultas:
        raise ErrorPanel("No se encontraron conversaciones en los archivos.")
    usar_api = datos.get("jev") == "api"
    r = acciones._correr_lote(consultas, datos.get("etiqueta") or "importado", usar_api, bool(datos.get("simular_plantillas")), tipo=datos.get("tipo") or "actual",
                              entrada=str(dir_export.relative_to(RAIZ)))
    return {"corrida": r["lote"], **r}


def chat(datos: dict) -> dict:
    historial = [h for h in (datos.get("historial") or []) if h.get("rol") in ("user", "assistant") and h.get("texto")][-20:]
    if not historial or historial[-1]["rol"] != "user":
        raise ErrorPanel("Escribí un pedido.")
    prov = datos.get("proveedor") or ajustes.proveedor_chat()
    if not prov:
        raise ErrorPanel("Para usar el chat, cargá la clave de algún modelo de IA en Ajustes.")
    try:
        return asistente.conversar(prov, historial, datos.get("lote"), acciones)
    except ErrorProveedor as e:
        raise ErrorPanel(str(e)) from e


GET = {
    "/api/corridas": lambda q: acciones.listar_lotes(),
    "/api/corrida": lambda q: cargar_lote(q.get("nombre", "")),
    "/api/categorias": lambda q: acciones.ver_categorias(),
    "/api/ajustes": lambda q: ajustes.publico(),
    "/api/historial": lambda q: acciones.historial(),
}
POST = {
    "/api/revision": guardar_revision,
    "/api/importar": importar,
    "/api/lote/agregar": lambda d: acciones.agregar_lote(d.get("contactos") or [], d.get("etiqueta") or "",
                                                         bool(d.get("jev_real", True)), bool(d.get("simular_plantillas", True)),
                                                         d.get("tipo") or "actual"),
    "/api/categorias/crear": lambda d: acciones.crear_categoria(d.get("categoria") or {}),
    "/api/categorias/editar": lambda d: acciones.editar_categoria(d.get("id", ""), d.get("cambios") or {}),
    "/api/categorias/eliminar": lambda d: acciones.eliminar_categoria(d.get("id", "")),
    "/api/mover": lambda d: acciones.mover(d.get("lote", ""), d.get("clave", ""), d.get("categoria", "")),
    "/api/deshacer": lambda d: acciones.deshacer_movimiento(d.get("lote", ""), d.get("clave", "")),
    "/api/reasignacion": lambda d: acciones.resolver_reasignacion(d.get("lote", ""), d.get("clave", ""), bool(d.get("aceptar")), d.get("categoria")),
    "/api/reclasificar": lambda d: acciones.reclasificar_lote(d.get("lote", "")),
    "/api/ajustes": lambda d: ajustes.actualizar(d.get("cambios") or {}),
    "/api/chat": chat,
}


class Acceso:
    """Login con contraseña (opcional). Se activa con --clave o JEVENTAS_CLAVE.
    Obligatorio cuando el panel se publica con un túnel."""

    RUTA = RAIZ / "config" / "acceso.local.json"  # no se versiona

    def __init__(self) -> None:
        self.usuario: str | None = None
        self.hash: bytes | None = None
        self.sal = secrets.token_bytes(16)
        self.sesiones: dict[str, float] = {}
        self.fallos: list[float] = []

    def activar(self, usuario: str | None, clave: str | None, guardar: bool = False) -> None:
        """Con usuario y clave: activa el login (y lo guarda cifrado si guardar=True).
        Sin datos: usa lo guardado en config/acceso.local.json, si existe."""
        self.sesiones.clear()
        if clave:
            self.sal = secrets.token_bytes(16)
            self.usuario, self.hash = (usuario or "").strip().lower() or None, self._h(clave)
            if guardar:
                self.RUTA.write_text(json.dumps({"usuario": self.usuario, "sal": self.sal.hex(), "hash": self.hash.hex()}), encoding="utf-8")
        elif self.RUTA.exists():
            d = json.loads(self.RUTA.read_text(encoding="utf-8"))
            self.usuario, self.sal, self.hash = d.get("usuario"), bytes.fromhex(d["sal"]), bytes.fromhex(d["hash"])
        else:
            self.usuario = self.hash = None

    def _h(self, clave: str) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), self.sal, 200_000)

    @property
    def activo(self) -> bool:
        return self.hash is not None

    def entrar(self, usuario: str, clave: str) -> str | None:
        ahora = time.time()
        self.fallos = [t for t in self.fallos if ahora - t < 600]
        if len(self.fallos) >= 20:
            return None  # demasiados intentos: 10 minutos de espera
        usuario_ok = self.usuario is None or (usuario or "").strip().lower() == self.usuario
        if self.hash and hmac.compare_digest(self._h(clave or ""), self.hash) and usuario_ok:
            token = secrets.token_urlsafe(32)
            self.sesiones[token] = ahora + 12 * 3600
            return token
        self.fallos.append(ahora)
        time.sleep(1)
        return None

    def _token(self, cookie_header: str | None) -> str | None:
        c = SimpleCookie()
        try:
            c.load(cookie_header or "")
        except Exception:  # noqa: BLE001
            return None
        m = c.get("jv_sesion")
        return m.value if m else None

    def valida(self, cookie_header: str | None) -> bool:
        if not self.activo:
            return True
        tok = self._token(cookie_header)
        return bool(tok and self.sesiones.get(tok, 0) > time.time())

    def salir(self, cookie_header: str | None) -> None:
        tok = self._token(cookie_header)
        if tok:
            self.sesiones.pop(tok, None)


ACCESO = Acceso()

PAGINA_LOGIN = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JeVentas</title><link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,300..800&display=swap" rel="stylesheet">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#EEF0EE;font-family:Archivo,system-ui,sans-serif;color:#1B2420}
form{background:#fff;padding:32px;border-radius:14px;width:min(360px,calc(100vw - 32px));box-shadow:0 30px 80px -30px rgba(27,36,32,.4);display:grid;gap:14px}
h1{margin:0;font-size:24px;font-stretch:118%;display:flex;gap:10px;align-items:center}h1 span{display:grid;grid-template-columns:repeat(3,7px);gap:2px}
h1 i{height:20px;background:#F2B33D;border-radius:1px}h1 i:nth-child(2){background:#1B2420}h1 i:nth-child(3){background:#8FA39C}
p{margin:0;color:#6B7570;font-size:14px}input{font:inherit;border:1px solid #D5DAD6;border-radius:6px;padding:10px 12px}
button{font:inherit;background:#1F5E57;color:#fff;border:0;border-radius:6px;padding:10px;font-weight:600;cursor:pointer}
.e{color:#B4532A;font-size:13.5px}</style></head><body><form method="post" action="/login">
<h1><span><i></i><i></i><i></i></span>JeVentas</h1><p>Panel interno de Ventas de Don Box.</p>
<input type="text" name="usuario" placeholder="Usuario" autocomplete="username" autofocus required>
<input type="password" name="clave" placeholder="Contraseña" autocomplete="current-password" required>__ERROR__<button>Entrar</button></form></body></html>"""


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ESTATICOS), **kw)

    def log_message(self, fmt, *args):  # silencioso salvo errores
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, estado=HTTPStatus.OK):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _manejar(self, fn):
        try:
            self._json(fn())
        except ErrorPanel as e:
            self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"Error interno: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _login(self, error: str = "", estado=HTTPStatus.OK):
        cuerpo = PAGINA_LOGIN.replace("__ERROR__", f'<p class="e">{error}</p>' if error else "").encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _redirigir(self, a: str, cookie: str | None = None):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", a)
        self.send_header("Content-Length", "0")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _autorizado(self) -> bool:
        return ACCESO.valida(self.headers.get("Cookie"))

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/login":
            return self._redirigir("/") if self._autorizado() else self._login()
        if u.path == "/salir":
            ACCESO.salir(self.headers.get("Cookie"))
            return self._redirigir("/login", "jv_sesion=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        if not self._autorizado():
            if u.path.startswith("/api/"):
                return self._json({"error": "Sesión vencida: volvé a entrar."}, HTTPStatus.UNAUTHORIZED)
            return self._redirigir("/login")
        if u.path == "/api/sesion":
            return self._json({"login": ACCESO.activo})
        if u.path in GET:
            return self._manejar(lambda: GET[u.path](q))
        if u.path == "/api/revisiones.csv":
            try:
                cuerpo = revisiones_csv(q.get("nombre", "")).encode("utf-8")
            except ErrorPanel as e:
                return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="revisiones_{q.get("nombre", "")}.csv"')
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return None
        if u.path.startswith("/api/"):
            return self._json({"error": "No existe"}, HTTPStatus.NOT_FOUND)
        if u.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path).path
        largo = int(self.headers.get("Content-Length", 0))
        if u == "/login":
            datos = parse_qs(self.rfile.read(min(largo, 4096)).decode("utf-8", "replace"))
            token = ACCESO.entrar((datos.get("usuario") or [""])[0], (datos.get("clave") or [""])[0])
            if not token:
                return self._login("Usuario o contraseña incorrectos.", HTTPStatus.UNAUTHORIZED)
            seguro = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            return self._redirigir("/", f"jv_sesion={token}; Path=/; Max-Age=43200; HttpOnly; SameSite=Lax{seguro}")
        if not self._autorizado():
            return self._json({"error": "Sesión vencida: volvé a entrar."}, HTTPStatus.UNAUTHORIZED)
        # Sin login, solo se aceptan pedidos de la propia página local (otro sitio abierto en el navegador
        # no puede usar la API). Con login, la cookie SameSite=Lax ya impide pedidos desde otros sitios.
        origen = self.headers.get("Origin")
        if not ACCESO.activo and origen and not re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origen):
            return self._json({"error": "Origen no permitido."}, HTTPStatus.FORBIDDEN)
        if largo > 50 * 1024 * 1024:
            return self._json({"error": "Los archivos superan 50 MB."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Pedido inválido."}, HTTPStatus.BAD_REQUEST)
        if u in POST:
            return self._manejar(lambda: POST[u](datos))
        return self._json({"error": "No existe"}, HTTPStatus.NOT_FOUND)


def servir(puerto: int = 8765, usuario: str | None = None, clave: str | None = None, guardar: bool = False) -> ThreadingHTTPServer:
    OUT.mkdir(exist_ok=True)
    ACCESO.activar(usuario or os.environ.get("JEVENTAS_USUARIO"), clave or os.environ.get("JEVENTAS_CLAVE"), guardar)
    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args()
    s = servir(a.puerto)
    print(f"Panel de JeVentas en http://127.0.0.1:{a.puerto}  (Ctrl+C para cerrar)")
    s.serve_forever()
