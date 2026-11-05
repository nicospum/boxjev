"""Métricas de la prueba retrospectiva.

Separa tres preguntas, como pide el plan del piloto:
1. Clasificación: ¿coincide el segmento con el de Ventas? (primer contacto)
2. Borradores y plantillas: se miden con la planilla que completa Ventas
   (`revision_ventas.csv`); acá solo se cuentan cobertura y alertas.
3. Resultado comercial: descriptivo por segmento. NO prueba causalidad.
"""
from __future__ import annotations

from collections import Counter, defaultdict

SEG_PROSPECTO = ["alta_intencion", "lista_para_cotizar", "exploratoria", "informacion_insuficiente"]


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "—"


def metricas(recs: list[dict]) -> dict:
    primeros = [r for r in recs if r["punto"] == "primer_contacto"]
    con_etiqueta = [r for r in primeros if r.get("etiqueta_ventas") and r["etiqueta_ventas"].get("segmento")]
    decididos = [r for r in con_etiqueta if not r["clasificacion"]["revision_humana"] or r["clasificacion"]["segmento"] == "no_es_prospecto"]
    aciertos = sum(r["clasificacion"]["segmento"] == r["etiqueta_ventas"]["segmento"] for r in decididos)

    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in con_etiqueta:
        confusion[r["etiqueta_ventas"]["segmento"]][r["clasificacion"]["segmento"]] += 1

    por_seg = {}
    for seg in sorted({r["etiqueta_ventas"]["segmento"] for r in con_etiqueta}):
        filas = [r for r in decididos if r["etiqueta_ventas"]["segmento"] == seg]
        pred = [r for r in decididos if r["clasificacion"]["segmento"] == seg]
        tp = sum(r["clasificacion"]["segmento"] == seg for r in filas)
        por_seg[seg] = {"n": len(filas), "recall": _pct(tp, len(filas)), "precision": _pct(tp, len(pred))}

    acciones = Counter(r["accion"]["tipo"] for r in recs)
    puntos = Counter(r["punto"] for r in recs)
    cierres = [r for r in recs if r["punto"] == "cierre_ventana"]
    con_plantilla = [r for r in cierres if r["accion"]["tipo"] == "plantilla"]
    coincide_plantilla = sum(
        1 for r in con_plantilla
        if r["observado"]["plantilla_usada_por_ventas"] and r["observado"]["plantilla_usada_por_ventas"] == r["accion"]["plantilla"]["id"]
    )
    ventas_uso_plantilla = sum(1 for r in cierres if r["observado"]["plantilla_usada_por_ventas"])

    riesgos = Counter(x for r in recs if r["accion"]["tipo"] == "borrador_libre" for x in r["accion"]["borrador"]["riesgos"])

    resultado_por_seg: dict[str, Counter] = defaultdict(Counter)
    for r in primeros:
        resultado_por_seg[r["clasificacion"]["segmento"]][r["observado"]["resultado"]] += 1

    return {
        "consultas": len(primeros),
        "puntos_de_decision": dict(puntos),
        "con_etiqueta": len(con_etiqueta),
        "derivadas_a_revision": len(con_etiqueta) - len(decididos),
        "acuerdo": {"aciertos": aciertos, "total": len(decididos), "pct": _pct(aciertos, len(decididos))},
        "por_segmento": por_seg,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "acciones": dict(acciones),
        "plantillas": {
            "cierres_de_ventana": len(cierres),
            "con_plantilla_recomendada": len(con_plantilla),
            "ventas_uso_plantilla": ventas_uso_plantilla,
            "misma_plantilla_que_ventas": coincide_plantilla,
            "simuladas": sum(1 for r in con_plantilla if r["accion"].get("simulada")),
        },
        "riesgos_en_borradores": dict(riesgos),
        "resultado_por_segmento": {k: dict(v) for k, v in resultado_por_seg.items()},
    }


def informe_md(m: dict, meta: dict) -> str:
    L = []
    L.append("# Resultado de la corrida retrospectiva\n")
    for k, v in meta.items():
        L.append(f"- **{k}:** {v}")
    if meta.get("Jev") == "simulado" or meta.get("datos_sinteticos"):
        L.append("\n> **Atención:** esta corrida usa Jev simulado y/o datos sintéticos. Los números prueban que el circuito funciona, "
                 "no la calidad de Jev. Para medir calidad: datos reales + etiquetas de Ventas + Jev real.\n")
    L.append("\n## 1. Clasificación (primer contacto)\n")
    L.append(f"- Consultas: {m['consultas']} · con etiqueta de Ventas: {m['con_etiqueta']}")
    L.append(f"- Derivadas a revisión humana por el sistema: {m['derivadas_a_revision']} ({_pct(m['derivadas_a_revision'], m['con_etiqueta'])})")
    a = m["acuerdo"]
    L.append(f"- **Acuerdo con Ventas** (sobre las que el sistema decidió): {a['aciertos']}/{a['total']} = **{a['pct']}**\n")
    L.append("| Segmento (Ventas) | n | Recall | Precisión |\n|---|---:|---:|---:|")
    for s, d in m["por_segmento"].items():
        L.append(f"| {s} | {d['n']} | {d['recall']} | {d['precision']} |")
    segs = sorted({s for row in m["confusion"].values() for s in row} | set(m["confusion"]))
    L.append("\n**Matriz de confusión** (filas: Ventas · columnas: sistema)\n")
    L.append("| | " + " | ".join(segs) + " |\n|---|" + "---:|" * len(segs))
    for s in segs:
        fila = m["confusion"].get(s, {})
        L.append(f"| **{s}** | " + " | ".join(str(fila.get(c, "")) for c in segs) + " |")
    L.append("\n## 2. Acciones recomendadas\n")
    L.append("| Punto de decisión | n |\n|---|---:|")
    for k, v in m["puntos_de_decision"].items():
        L.append(f"| {k} | {v} |")
    L.append("\n| Acción | n |\n|---|---:|")
    for k, v in sorted(m["acciones"].items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} |")
    p = m["plantillas"]
    L.append(f"\n**Plantillas** — cierres de ventana: {p['cierres_de_ventana']}; con plantilla recomendada: {p['con_plantilla_recomendada']} "
             f"(simuladas: {p['simuladas']}); Ventas usó plantilla en {p['ventas_uso_plantilla']}; misma plantilla que Ventas: {p['misma_plantilla_que_ventas']}.")
    L.append(f"\n**Alertas en borradores:** {m['riesgos_en_borradores'] or 'ninguna'}")
    L.append("\nLa calidad de borradores y plantillas se mide con `revision_ventas.csv` (lo completa Ventas).")
    L.append("\n## 3. Resultado comercial por segmento (descriptivo, no causal)\n")
    L.append("| Segmento | alquiló | no alquiló | desconocido |\n|---|---:|---:|---:|")
    for s, d in sorted(m["resultado_por_segmento"].items()):
        L.append(f"| {s} | {d.get('alquilo', 0)} | {d.get('no_alquilo', 0)} | {d.get('desconocido', 0)} |")
    return "\n".join(L) + "\n"
