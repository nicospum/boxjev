"""Servidor local del panel de JeVentas (solo stdlib, solo en esta computadora).

    python scripts/abrir_panel.py            # abre http://127.0.0.1:8765

API:
  GET  /api/corridas                    lista de corridas en out/
  GET  /api/corrida?nombre=X            consultas + recomendaciones + revisiones de una corrida
  GET  /api/revisiones.csv?nombre=X     revisiones de Ventas en CSV (para compartir)
  POST /api/revision                    guarda la revisión de una recomendación
  POST /api/importar                    convierte archivos exportados y corre el análisis

No envía mensajes ni toca HubSpot/Atom. Escucha solo en 127.0.0.1.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from jeventas.corrida import correr, herramientas  # noqa: E402
from jeventas.importar import COLUMNAS_MENSAJES, desde_csv, desde_whatsapp_txt  # noqa: E402
from jeventas.jev import JevError  # noqa: E402
from jeventas.modelo import leer_jsonl  # noqa: E402

OUT = RAIZ / "out"
ESTATICOS = Path(__file__).resolve().parent / "static"
NOMBRE_OK = re.compile(r"^[\w.-]+$")
_candado = threading.Lock()


class ErrorPanel(Exception):
    pass


def _carpeta(nombre: str) -> Path:
    if not nombre or not NOMBRE_OK.match(nombre) or not (OUT / nombre / "recomendaciones.jsonl").exists():
        raise ErrorPanel(f"No existe la corrida '{nombre}'.")
    return OUT / nombre


def _leer_json(p: Path, defecto):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def clave(r: dict) -> str:
    return f"{r['id_consulta']}|{r['punto']}|{r['evaluado_en']}"


def listar_corridas() -> list[dict]:
    res = []
    for d in sorted(OUT.glob("*/recomendaciones.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = _leer_json(d.parent / "meta.json", {})
        rev = _leer_json(d.parent / "revisiones.json", {})
        res.append({"nombre": d.parent.name, "meta": meta, "revisadas": len(rev)})
    return res


def cargar_corrida(nombre: str) -> dict:
    d = _carpeta(nombre)
    recs = [json.loads(l) for l in open(d / "recomendaciones.jsonl", encoding="utf-8") if l.strip()]
    consultas = [c.a_dict() for c in leer_jsonl(d / "consultas.jsonl")] if (d / "consultas.jsonl").exists() else []
    for r in recs:
        r["clave"] = clave(r)
    return {
        "nombre": nombre,
        "meta": _leer_json(d / "meta.json", {}),
        "metricas": _leer_json(d / "metricas.json", {}),
        "consultas": consultas,
        "recomendaciones": recs,
        "revisiones": _leer_json(d / "revisiones.json", {}),
    }


def guardar_revision(datos: dict) -> dict:
    d = _carpeta(datos.get("corrida", ""))
    k = datos.get("clave")
    if not k or not isinstance(k, str):
        raise ErrorPanel("Falta la recomendación a revisar.")
    with _candado:
        ruta = d / "revisiones.json"
        rev = _leer_json(ruta, {})
        if datos.get("revision") is None:
            rev.pop(k, None)
        else:
            r = datos["revision"]
            limpio = {
                "segmento_ok": r.get("segmento_ok") if r.get("segmento_ok") in ("si", "no") else None,
                "segmento_correcto": r.get("segmento_correcto") or None,
                "sugerencia_nota": r.get("sugerencia_nota") if r.get("sugerencia_nota") in (1, 2, 3, 4, 5) else None,
                "comentario": (r.get("comentario") or "")[:2000],
                "fecha": datetime.now().isoformat(timespec="seconds"),
            }
            rev[k] = limpio
        ruta.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "revisadas": len(rev)}


def revisiones_csv(nombre: str) -> str:
    c = cargar_corrida(nombre)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id_consulta", "momento", "evaluado_en", "segmento_sistema", "segmento_ok", "segmento_correcto",
                "accion", "nota_sugerencia", "comentario", "fecha_revision"])
    for r in c["recomendaciones"]:
        v = c["revisiones"].get(r["clave"])
        if not v:
            continue
        w.writerow([r["id_consulta"], r["punto"], r["evaluado_en"], r["clasificacion"]["segmento"], v["segmento_ok"],
                    v["segmento_correcto"] or "", r["accion"]["tipo"], v["sugerencia_nota"] or "", v["comentario"], v["fecha"]])
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
    archivos = datos.get("archivos") or []
    if not archivos:
        raise ErrorPanel("Elegí al menos un archivo exportado.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = RAIZ / "export" / f"panel_{ts}"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombres_ventas = [n.strip() for n in (datos.get("nombres_ventas") or "").split(",") if n.strip()]

    consultas, csv_mensajes, csv_consultas = [], None, None
    chats: dict[str, object] = {}  # nombre del archivo .txt (sin extensión) -> consulta
    for a in archivos:
        nombre = Path(a.get("nombre", "archivo")).name
        if not NOMBRE_OK.match(nombre.replace(" ", "_")):
            nombre = re.sub(r"[^\w.-]", "_", nombre)
        ruta = carpeta / nombre
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
        csv_consultas = None
    if csv_mensajes:
        consultas.extend(desde_csv(csv_mensajes, csv_consultas))
    if not consultas:
        raise ErrorPanel("No se encontraron conversaciones en los archivos.")

    usar_api = datos.get("jev") == "api"
    if usar_api and not datos.get("aprobado"):
        raise ErrorPanel("Para usar Jev real, confirmá que Don Box aprobó compartir estas conversaciones.")
    try:
        jev, redactor, catalogo = herramientas("api" if usar_api else "simulado", "offline", bool(datos.get("aprobado")),
                                               bool(datos.get("simular_plantillas")))
    except JevError as e:
        raise ErrorPanel(str(e)) from e
    etiqueta = re.sub(r"[^\w-]", "_", (datos.get("etiqueta") or "importado").strip())[:40] or "importado"
    nombre_corrida = f"{ts}_{etiqueta}"
    res = correr(consultas, OUT / nombre_corrida, jev, redactor, catalogo, entrada=str(carpeta.relative_to(RAIZ)))
    return {"corrida": nombre_corrida, "consultas": res["meta"]["consultas"], "errores": res["errores"][:5]}


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ESTATICOS), **kw)

    def log_message(self, fmt, *args):  # silencioso salvo errores
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _json(self, obj, estado=HTTPStatus.OK):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _manejar(self, fn):
        try:
            fn()
        except ErrorPanel as e:
            self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"Error interno: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/corridas":
            return self._manejar(lambda: self._json(listar_corridas()))
        if u.path == "/api/corrida":
            return self._manejar(lambda: self._json(cargar_corrida(q.get("nombre", ""))))
        if u.path == "/api/revisiones.csv":
            def enviar():
                cuerpo = revisiones_csv(q.get("nombre", "")).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="revisiones_{q.get("nombre", "")}.csv"')
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
            return self._manejar(enviar)
        if u.path.startswith("/api/"):
            return self._json({"error": "No existe"}, HTTPStatus.NOT_FOUND)
        if u.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length", 0))
        if largo > 50 * 1024 * 1024:
            return self._json({"error": "Los archivos superan 50 MB."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Pedido inválido."}, HTTPStatus.BAD_REQUEST)
        u = urlparse(self.path).path
        if u == "/api/revision":
            return self._manejar(lambda: self._json(guardar_revision(datos)))
        if u == "/api/importar":
            return self._manejar(lambda: self._json(importar(datos)))
        return self._json({"error": "No existe"}, HTTPStatus.NOT_FOUND)


def servir(puerto: int = 8765) -> ThreadingHTTPServer:
    OUT.mkdir(exist_ok=True)
    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8765)
    a = ap.parse_args()
    s = servir(a.puerto)
    print(f"Panel de JeVentas en http://127.0.0.1:{a.puerto}  (Ctrl+C para cerrar)")
    s.serve_forever()
