"""Operaciones del panel. Las usan los botones (servidor.py) y el chat asistente (asistente.py).

Modelo de datos por lote (out/<lote>/):
  recomendaciones.jsonl   lo que sugirió el sistema (incluye la categoría que eligió Jev)
  asignaciones.json       cambios de categoría hechos por Alberto (mandan sobre Jev)
  reasignaciones.json     sugerencias pendientes tras eliminar una categoría
  revisiones.json         revisión de cada sugerencia
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from jeventas import ajustes
from jeventas.categorias import SIN_CATEGORIA, Categorias, ErrorCategorias
from jeventas.corrida import RAIZ, categorias, correr, herramientas
from jeventas.importar import desde_texto
from jeventas.jev import JevAPI, JevError, JevSimulado
from jeventas.modelo import leer_jsonl
from jeventas.pipeline import reclasificar
from jeventas.plantillas import CatalogoPlantillas
from jeventas.redactor import RedactorOffline, cargar_info

OUT = RAIZ / "out"
NOMBRE_OK = re.compile(r"^[\w.-]+$")
_candado = threading.RLock()


class ErrorPanel(Exception):
    pass


# ---------------------------------------------------------------- utilidades
def carpeta(nombre: str) -> Path:
    if not nombre or not NOMBRE_OK.match(nombre) or not (OUT / nombre / "recomendaciones.jsonl").exists():
        raise ErrorPanel(f"No existe el lote '{nombre}'.")
    return OUT / nombre


def leer_json(p: Path, defecto):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def escribir_json(p: Path, d) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def clave(r: dict) -> str:
    return f"{r['id_consulta']}|{r['punto']}|{r['evaluado_en']}"


def leer_recs(d: Path) -> list[dict]:
    recs = [json.loads(l) for l in open(d / "recomendaciones.jsonl", encoding="utf-8") if l.strip()]
    for r in recs:
        r["clave"] = clave(r)
    return recs


def escribir_recs(d: Path, recs: list[dict]) -> None:
    tmp = d / "recomendaciones.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps({k: v for k, v in r.items() if k != "clave"}, ensure_ascii=False) + "\n")
    tmp.replace(d / "recomendaciones.jsonl")


def ruta_payload(d: Path, r: dict) -> Path:
    ts = datetime.fromisoformat(r["evaluado_en"])
    return d / "payloads" / f"{r['id_consulta']}__{r['punto']}__{ts:%Y%m%dT%H%M}.json"


def categoria_actual(r: dict, asignaciones: dict, cats: Categorias) -> str:
    a = asignaciones.get(r["clave"])
    if a:
        return a["categoria"]
    cid = ((r.get("clasificacion") or {}).get("categoria") or {}).get("id")
    return cid if cid and cats.obtener(cid) else SIN_CATEGORIA


def jev_para_lote(meta: dict):
    if meta.get("jev") == "simulado":
        return JevSimulado()
    try:
        return JevAPI(ajustes.aprobado(), api_key=ajustes.clave("typesafe"))
    except JevError as e:
        raise ErrorPanel(f"Este lote se clasificó con Jev real y ahora Jev no se puede usar: {e} "
                         "Activá la aprobación y cargá la clave en Ajustes.") from e


class _MantenerBorrador:
    """Al reclasificar no se vuelven a pedir borradores: se conserva el anterior o se usa el texto base."""

    def __init__(self, previo: dict | None) -> None:
        self.previo = previo
        self.offline = RedactorOffline(cargar_info(RAIZ / "config" / "info_comercial.json"))

    def redactar(self, conversacion, clasif):
        return self.previo or self.offline.redactar(conversacion, clasif)


def _catalogo(meta: dict) -> CatalogoPlantillas:
    return CatalogoPlantillas(RAIZ / "config" / "plantillas.json", simular=bool(meta.get("plantillas_simuladas")))


# ---------------------------------------------------------------- lotes
def listar_lotes() -> list[dict]:
    res = []
    for p in sorted(OUT.glob("*/recomendaciones.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        res.append({"nombre": p.parent.name, "meta": leer_json(p.parent / "meta.json", {}),
                    "revisadas": len(leer_json(p.parent / "revisiones.json", {}))})
    return res


def cargar_lote(nombre: str) -> dict:
    d = carpeta(nombre)
    return {
        "nombre": nombre,
        "meta": leer_json(d / "meta.json", {}),
        "metricas": leer_json(d / "metricas.json", {}),
        "consultas": [c.a_dict() for c in leer_jsonl(d / "consultas.jsonl")] if (d / "consultas.jsonl").exists() else [],
        "recomendaciones": leer_recs(d),
        "revisiones": leer_json(d / "revisiones.json", {}),
        "asignaciones": leer_json(d / "asignaciones.json", {}),
        "reasignaciones": leer_json(d / "reasignaciones.json", []),
    }


def resumen_lote(nombre: str) -> dict:
    d = carpeta(nombre)
    cats = categorias()
    recs, asig = leer_recs(d), leer_json(d / "asignaciones.json", {})
    por_etapa: dict = {}
    for etapa in cats.datos["etapas"]:
        ultimos = _ultimos_por_contacto(recs, etapa)
        cuenta: dict = {}
        for r in ultimos.values():
            cid = categoria_actual(r, asig, cats)
            cuenta[cats.nombre(cid)] = cuenta.get(cats.nombre(cid), 0) + 1
        por_etapa[cats.datos["etapas"][etapa]] = cuenta
    pend = [x for x in leer_json(d / "reasignaciones.json", []) if x["estado"] == "pendiente"]
    return {"lote": nombre, "meta": leer_json(d / "meta.json", {}), "contactos_por_categoria": por_etapa,
            "reasignaciones_pendientes": len(pend), "revisadas": len(leer_json(d / "revisiones.json", {}))}


def _ultimos_por_contacto(recs: list[dict], etapa: str) -> dict:
    from jeventas.categorias import ETAPA_POR_PUNTO

    ult: dict = {}
    for r in sorted(recs, key=lambda x: x["evaluado_en"]):
        if ETAPA_POR_PUNTO[r["punto"]] == etapa:
            ult[r["id_consulta"]] = r
    return ult


def miembros(nombre: str, categoria: str, limite: int = 50) -> dict:
    d = carpeta(nombre)
    cats = categorias()
    c = cats.obtener(categoria)
    etapas = [c["etapa"]] if c else list(cats.datos["etapas"])
    recs, asig = leer_recs(d), leer_json(d / "asignaciones.json", {})
    consultas = {x.id_consulta: x for x in leer_jsonl(d / "consultas.jsonl")} if (d / "consultas.jsonl").exists() else {}
    res = []
    for etapa in etapas:
        for r in _ultimos_por_contacto(recs, etapa).values():
            if categoria_actual(r, asig, cats) == categoria:
                k = consultas.get(r["id_consulta"])
                primer = next((m.texto for m in k.mensajes if m.autor == "cliente"), "") if k else ""
                res.append({"id_consulta": r["id_consulta"], "clave": r["clave"], "momento": r["punto"],
                            "primer_mensaje": primer[:160], "accion": r["accion"]["tipo"]})
    return {"categoria": cats.nombre(categoria), "total": len(res), "contactos": res[:limite]}


def ver_consulta(nombre: str, id_consulta: str) -> dict:
    d = carpeta(nombre)
    cats = categorias()
    asig = leer_json(d / "asignaciones.json", {})
    k = next((x for x in leer_jsonl(d / "consultas.jsonl") if x.id_consulta == id_consulta), None)
    if not k:
        raise ErrorPanel(f"No existe la consulta {id_consulta} en el lote {nombre}.")
    recs = [r for r in leer_recs(d) if r["id_consulta"] == id_consulta]
    return {
        "id_consulta": id_consulta,
        "mensajes": [{"autor": m.autor, "texto": m.texto, "ts": m.ts.isoformat(timespec="minutes")} for m in k.mensajes],
        "resultado": k.resultado.get("estado"),
        "momentos": [{"clave": r["clave"], "momento": r["punto"], "categoria": cats.nombre(categoria_actual(r, asig, cats)),
                      "accion": r["accion"]["tipo"], "explicacion": r["clasificacion"].get("explicacion", [])} for r in recs],
    }


# ---------------------------------------------------------------- asignaciones
def mover(nombre: str, clave_rec: str, categoria: str, origen: str = "alberto") -> dict:
    cats = categorias()
    if categoria != SIN_CATEGORIA and not cats.obtener(categoria):
        raise ErrorPanel(f"No existe la categoría '{categoria}'.")
    with _candado:
        d = carpeta(nombre)
        recs = {r["clave"]: r for r in leer_recs(d)}
        r = recs.get(clave_rec)
        if not r:
            raise ErrorPanel("No existe ese momento de la consulta.")
        c = cats.obtener(categoria)
        from jeventas.categorias import ETAPA_POR_PUNTO

        if c and c["etapa"] != ETAPA_POR_PUNTO[r["punto"]]:
            raise ErrorPanel(f"'{c['nombre']}' es una categoría de otra etapa ({cats.datos['etapas'][c['etapa']]}).")
        asig = leer_json(d / "asignaciones.json", {})
        asig[clave_rec] = {"categoria": categoria, "origen": origen, "fecha": datetime.now().isoformat(timespec="seconds")}
        escribir_json(d / "asignaciones.json", asig)
    return {"ok": True, "clave": clave_rec, "categoria": cats.nombre(categoria)}


def deshacer_movimiento(nombre: str, clave_rec: str) -> dict:
    with _candado:
        d = carpeta(nombre)
        asig = leer_json(d / "asignaciones.json", {})
        asig.pop(clave_rec, None)
        escribir_json(d / "asignaciones.json", asig)
    return {"ok": True}


# ---------------------------------------------------------------- categorías
def ver_categorias() -> dict:
    d = categorias().a_dict()
    d["plantillas"] = [p["id"] for p in leer_json(RAIZ / "config" / "plantillas.json", {"plantillas": []})["plantillas"]]
    return d


def crear_categoria(datos: dict) -> dict:
    try:
        return categorias().crear(datos)
    except ErrorCategorias as e:
        raise ErrorPanel(str(e)) from e


def editar_categoria(cid: str, cambios: dict) -> dict:
    try:
        return categorias().editar(cid, cambios)
    except ErrorCategorias as e:
        raise ErrorPanel(str(e)) from e


def eliminar_categoria(cid: str) -> dict:
    """Elimina la categoría y, en cada lote, pide a Jev la mejor categoría restante para
    los contactos que quedaron sueltos. Las sugerencias quedan pendientes para Alberto."""
    with _candado:
        cats = categorias()
        try:
            eliminada = cats.eliminar(cid)
        except ErrorCategorias as e:
            raise ErrorPanel(str(e)) from e
        restantes = [c["id"] for c in cats.de_etapa(eliminada["etapa"])]
        total, errores = 0, []
        for lote in listar_lotes():
            d = OUT / lote["nombre"]
            recs, asig = leer_recs(d), leer_json(d / "asignaciones.json", {})
            sueltos = [r for r in recs if _asignada(r, asig) == cid]
            if not sueltos:
                continue
            try:
                jev = jev_para_lote(lote["meta"])
            except ErrorPanel as e:
                errores.append(str(e))
                jev = None
            pend = [x for x in leer_json(d / "reasignaciones.json", []) if x["clave"] not in {r["clave"] for r in sueltos}]
            for r in sueltos:
                base = {"clave": r["clave"], "id_consulta": r["id_consulta"], "momento": r["punto"], "de": cid,
                        "de_nombre": eliminada["nombre"], "sugerida": None, "sugerida_nombre": None, "confianza": None,
                        "alternativas": [], "estado": "pendiente"}
                p = ruta_payload(d, r)
                if jev is not None and p.exists():
                    try:
                        nuevo = reclasificar(r, leer_json(p, {})["state"], jev, cats, _MantenerBorrador(None),
                                             _catalogo(lote["meta"]), solo_entre=restantes)
                        cat = nuevo["clasificacion"]["categoria"]
                        sug = cat.get("sugerida") or cat["id"]
                        base.update({"sugerida": sug, "sugerida_nombre": cats.nombre(sug), "confianza": cat.get("confianza"),
                                     "alternativas": cat.get("alternativas")})
                    except JevError as e:  # sin sugerencia: Alberto elige a mano
                        errores.append(str(e))
                        jev = None
                pend.append(base)
                asig.pop(r["clave"], None)
                total += 1
            escribir_json(d / "reasignaciones.json", pend)
            escribir_json(d / "asignaciones.json", asig)
    return {"eliminada": eliminada["nombre"], "contactos_a_reasignar": total, "errores": errores[:3]}


def _asignada(r: dict, asig: dict) -> str | None:
    a = asig.get(r["clave"])
    return a["categoria"] if a else ((r.get("clasificacion") or {}).get("categoria") or {}).get("id")


def resolver_reasignacion(nombre: str, clave_rec: str, aceptar: bool, categoria: str | None = None) -> dict:
    with _candado:
        d = carpeta(nombre)
        pend = leer_json(d / "reasignaciones.json", [])
        x = next((p for p in pend if p["clave"] == clave_rec and p["estado"] == "pendiente"), None)
        if not x:
            raise ErrorPanel("No hay una sugerencia pendiente para ese contacto.")
        if aceptar:
            if not x.get("sugerida"):
                raise ErrorPanel("Jev no dejó sugerencia para este contacto: elegí la categoría a mano.")
            mover(nombre, clave_rec, x["sugerida"], origen="sugerencia aceptada")
            x["estado"] = "aceptada"
        else:
            if categoria:
                mover(nombre, clave_rec, categoria, origen="alberto")
            x["estado"] = "rechazada"
            x["elegida"] = categoria
        x["fecha"] = datetime.now().isoformat(timespec="seconds")
        escribir_json(d / "reasignaciones.json", pend)
    return {"ok": True, "estado": x["estado"]}


def reclasificar_lote(nombre: str) -> dict:
    """Vuelve a preguntar a Jev la categoría de cada momento (útil después de editar descripciones).
    Los cambios hechos a mano por Alberto se mantienen."""
    with _candado:
        d = carpeta(nombre)
        meta = leer_json(d / "meta.json", {})
        jev, cats, catalogo = jev_para_lote(meta), categorias(), _catalogo(meta)
        recs, cambios, nuevos = leer_recs(d), 0, []
        for r in recs:
            p = ruta_payload(d, r)
            if not p.exists():
                nuevos.append(r)
                continue
            antes = ((r["clasificacion"].get("categoria")) or {}).get("id")
            try:
                n = reclasificar(r, leer_json(p, {})["state"], jev, cats, _MantenerBorrador((r["accion"] or {}).get("borrador")), catalogo)
            except JevError as e:
                raise ErrorPanel(f"Jev falló a mitad de camino: {e}") from e
            n["clave"] = r["clave"]
            cambios += n["clasificacion"]["categoria"]["id"] != antes
            nuevos.append(n)
        escribir_recs(d, nuevos)
    return {"lote": nombre, "momentos": len(recs), "cambiaron": cambios}


# ---------------------------------------------------------------- agregar lote
def agregar_lote(contactos: list[dict], etiqueta: str = "", usar_jev_real: bool = True, simular_plantillas: bool = True) -> dict:
    """contactos: [{'texto': conversación pegada, 'nombre': nombre a borrar (opcional),
    'ultimo_hace_horas': horas desde el último mensaje (opcional), 'resultado': alquilo/no_alquilo/desconocido}]"""
    if not contactos:
        raise ErrorPanel("Pegá al menos una conversación.")
    if len(contactos) > 200:
        raise ErrorPanel("Máximo 200 conversaciones por lote desde esta pantalla.")
    ahora = datetime.now()
    consultas = []
    for i, c in enumerate(contactos, 1):
        texto = (c.get("texto") or "").strip()
        if not texto:
            continue
        try:
            k = desde_texto(texto, ultimo_hace_horas=float(c.get("ultimo_hace_horas") or 0), ahora=ahora,
                            ident=f"{etiqueta}-{i}-{ahora.isoformat()}", nombres_a_borrar=[c.get("nombre") or ""])
        except ValueError as e:
            raise ErrorPanel(f"Contacto {i}: {e}") from e
        res = (c.get("resultado") or "desconocido").strip().lower().replace(" ", "_").replace("ó", "o")
        k.resultado = {"estado": res if res in ("alquilo", "no_alquilo") else "desconocido"}
        consultas.append(k)
    if not consultas:
        raise ErrorPanel("Pegá al menos una conversación.")
    return _correr_lote(consultas, etiqueta or "contactos", usar_jev_real, simular_plantillas, entrada="pegado en el panel")


def _correr_lote(consultas, etiqueta: str, usar_jev_real: bool, simular_plantillas: bool, entrada: str) -> dict:
    if usar_jev_real:
        if not ajustes.aprobado():
            raise ErrorPanel("Para usar Jev real, activá en Ajustes que Don Box aprobó enviar conversaciones anonimizadas.")
        if not ajustes.clave("typesafe"):
            raise ErrorPanel("Falta la clave de TypeSafe (Jev). Cargala en Ajustes.")
    try:
        jev, redactor, catalogo = herramientas("api" if usar_jev_real else "simulado", ajustes.proveedor_borradores(),
                                               ajustes.aprobado(), simular_plantillas)
    except Exception as e:  # noqa: BLE001
        raise ErrorPanel(str(e)) from e
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    limpio = re.sub(r"[^\w-]", "_", etiqueta.strip())[:40] or "lote"
    nombre = f"{ts}_{limpio}"
    res = correr(consultas, OUT / nombre, jev, redactor, catalogo, entrada=entrada)
    return {"lote": nombre, "consultas": res["meta"]["consultas"], "sugerencias": res["meta"]["recomendaciones"],
            "errores": [e["error"] for e in res["errores"][:3]]}
