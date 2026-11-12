"""Ejemplos del historial para el redactor.

Un lote de tipo "historial" son conversaciones terminadas, con resultado conocido.
Se clasifican igual que las actuales y de cada momento se guarda qué respondió
Ventas y qué pasó después. Cuando el redactor escribe un borrador para una
categoría, ve respuestas reales de esa categoría que funcionaron (el cliente
siguió y alquiló) y otras que no, para copiar el tono y lo que sirve.

No es entrenamiento: el modelo no cambia, solo recibe ejemplos en cada pedido.
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_BUENOS = 3
MAX_MALOS = 2
MAX_TEXTO = 400


def _leer(p: Path, defecto):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else defecto


def _categoria(r: dict, asig: dict) -> str | None:
    a = asig.get(f"{r['id_consulta']}|{r['punto']}|{r['evaluado_en']}")
    if a:
        return a["categoria"]
    return ((r.get("clasificacion") or {}).get("categoria") or {}).get("id")


def casos(out: Path) -> list[dict]:
    """Todos los momentos de los lotes de historial con la respuesta de Ventas y lo que pasó."""
    res = []
    for meta_p in sorted(Path(out).glob("*/meta.json")):
        meta = _leer(meta_p, {})
        if meta.get("tipo") != "historial":
            continue
        d = meta_p.parent
        asig = _leer(d / "asignaciones.json", {})
        consultas = {}
        if (d / "consultas.jsonl").exists():
            for linea in open(d / "consultas.jsonl", encoding="utf-8"):
                if linea.strip():
                    c = json.loads(linea)
                    consultas[c["id_consulta"]] = c
        for linea in open(d / "recomendaciones.jsonl", encoding="utf-8"):
            if not linea.strip():
                continue
            r = json.loads(linea)
            o = r.get("observado") or {}
            if not o.get("siguiente_mensaje_ventas"):
                continue
            c = consultas.get(r["id_consulta"]) or {}
            previos = [m for m in c.get("mensajes", []) if m["autor"] == "cliente" and m["ts"] <= r["evaluado_en"]]
            res.append({
                "lote": d.name,
                "id_consulta": r["id_consulta"],
                "categoria": _categoria(r, asig),
                "momento": r["punto"],
                "cliente": (previos[-1]["texto"] if previos else "")[:MAX_TEXTO],
                "respuesta_ventas": o["siguiente_mensaje_ventas"][:MAX_TEXTO],
                "plantilla": o.get("plantilla_usada_por_ventas"),
                "volvio_a_escribir": bool(o.get("prospecto_volvio_a_escribir")),
                "resultado": o.get("resultado", "desconocido"),
            })
    return res


def _puntaje(c: dict) -> int:
    return (2 if c["resultado"] == "alquilo" else 0) + (1 if c["volvio_a_escribir"] else 0)


def para_categoria(out: Path, categoria: str | None) -> dict:
    """Ejemplos buenos (alquiló / siguió la charla) y malos (no volvió a escribir y no alquiló)."""
    if not categoria:
        return {"buenos": [], "malos": []}
    todos = [c for c in casos(out) if c["categoria"] == categoria and not c["plantilla"]]
    buenos = sorted((c for c in todos if _puntaje(c) >= 2 or (c["volvio_a_escribir"] and c["resultado"] != "no_alquilo")),
                    key=_puntaje, reverse=True)[:MAX_BUENOS]
    malos = [c for c in todos if not c["volvio_a_escribir"] and c["resultado"] == "no_alquilo"][:MAX_MALOS]
    return {"buenos": buenos, "malos": malos}


def estadisticas(out: Path) -> dict:
    """Por categoría y por plantilla: cuántos casos, cuántos siguieron la charla y cuántos alquilaron."""
    por_cat: dict = {}
    por_plantilla: dict = {}
    vistos_resultado: set = set()
    for c in casos(out):
        k = c["categoria"] or "sin_categoria"
        s = por_cat.setdefault(k, {"casos": 0, "respondieron": 0, "alquilaron": 0, "ejemplos_buenos": 0})
        s["casos"] += 1
        s["respondieron"] += c["volvio_a_escribir"]
        clave = (c["lote"], c["id_consulta"], k)
        if c["resultado"] == "alquilo" and clave not in vistos_resultado:
            s["alquilaron"] += 1
            vistos_resultado.add(clave)
        if not c["plantilla"] and (_puntaje(c) >= 2 or (c["volvio_a_escribir"] and c["resultado"] != "no_alquilo")):
            s["ejemplos_buenos"] += 1
        if c["plantilla"]:
            p = por_plantilla.setdefault(c["plantilla"], {"enviadas": 0, "respondieron": 0, "alquilaron": 0})
            p["enviadas"] += 1
            p["respondieron"] += c["volvio_a_escribir"]
            p["alquilaron"] += c["resultado"] == "alquilo"
    return {"por_categoria": por_cat, "por_plantilla": por_plantilla}


def bloque_prompt(ej: dict) -> str:
    if not ej["buenos"] and not ej["malos"]:
        return ""
    partes = ["<ejemplos_historial>",
              "Respuestas reales de Ventas en conversaciones parecidas (misma categoría). "
              "Imitá el tono y lo que hizo avanzar la charla; evitá lo que no funcionó. "
              "No copies datos concretos (fechas, precios, nombres) de los ejemplos."]
    for c in ej["buenos"]:
        partes.append(f"FUNCIONÓ ({'alquiló' if c['resultado'] == 'alquilo' else 'el cliente siguió la charla'}):\n"
                      f"  Cliente: {c['cliente']}\n  Ventas: {c['respuesta_ventas']}")
    for c in ej["malos"]:
        partes.append(f"NO FUNCIONÓ (no volvió a escribir, no alquiló):\n  Cliente: {c['cliente']}\n  Ventas: {c['respuesta_ventas']}")
    partes.append("</ejemplos_historial>")
    return "\n".join(partes)
