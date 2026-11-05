"""Ejecuta una corrida (lote de consultas) y guarda todos sus archivos.

Lo usan `scripts/correr_piloto.py` y el panel web (`panel/servidor.py`).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .evaluacion import informe_md, metricas
from .jev import JevAPI, JevError, JevSimulado
from .modelo import Consulta, escribir_jsonl
from .pipeline import evaluar, puntos_de_decision
from .plantillas import CatalogoPlantillas
from .redactor import RedactorClaude, RedactorOffline, cargar_info

RAIZ = Path(__file__).resolve().parents[1]

COLUMNAS_REVISION = [
    "id_consulta", "punto", "evaluado_en", "ventana", "ultimo_mensaje_prospecto",
    "segmento_sistema", "necesidad", "sede", "explicacion", "accion", "borrador_o_plantilla", "alertas",
    "REV_segmento_correcto (si/no/cual)", "REV_borrador_utilizable (1-5)", "REV_plantilla_adecuada (si/no/cual)", "REV_comentario",
]


def herramientas(jev: str = "simulado", redactor: str = "offline", envio_externo_aprobado: bool = False, simular_plantillas: bool = False):
    j = JevAPI(envio_externo_aprobado) if jev == "api" else JevSimulado()
    info = cargar_info(RAIZ / "config" / "info_comercial.json")
    r = RedactorClaude(info, envio_externo_aprobado) if redactor == "claude" else RedactorOffline(info)
    c = CatalogoPlantillas(RAIZ / "config" / "plantillas.json", simular=simular_plantillas)
    return j, r, c


def correr(consultas: Iterable[Consulta], salida: Path, jev, redactor, catalogo: CatalogoPlantillas, entrada: str = "") -> dict:
    salida = Path(salida)
    (salida / "payloads").mkdir(parents=True, exist_ok=True)
    consultas = list(consultas)

    recs, errores = [], []
    for c in consultas:
        for ts, motivo in puntos_de_decision(c):
            try:
                r = evaluar(c, ts, motivo, jev, redactor, catalogo)
            except JevError as e:  # un error es un error: no se convierte en respuesta
                errores.append({"id_consulta": c.id_consulta, "punto": motivo, "error": str(e)})
                continue
            payload = r.pop("_payload")
            (salida / "payloads" / f"{c.id_consulta}__{motivo}__{ts:%Y%m%dT%H%M}.json").write_text(
                json.dumps({"preguntas_version": r["jev"]["version_preguntas"], **payload}, ensure_ascii=False, indent=1), encoding="utf-8")
            r["_ultimo_prospecto"] = next((m["texto"] for m in reversed(payload["state"]["conversacion"]) if m["de"] == "Prospecto"), "")
            recs.append(r)

    escribir_jsonl(salida / "consultas.jsonl", consultas)
    with open(salida / "recomendaciones.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")

    with open(salida / "revision_ventas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS_REVISION)
        for r in recs:
            ac, cl = r["accion"], r["clasificacion"]
            if ac.get("borrador"):
                propuesta = ac["borrador"]["texto"]
            elif ac.get("plantilla"):
                propuesta = f"{ac['plantilla']['id']}: {ac['plantilla']['texto']}"
            else:
                propuesta = ac.get("detalle") or ac.get("motivo") or ""
            w.writerow([
                r["id_consulta"], r["punto"], r["evaluado_en"], "abierta" if r["ventana"]["abierta"] else "cerrada",
                r["_ultimo_prospecto"], cl["segmento"], cl["necesidad"] or "", cl["sede"] or "", " | ".join(cl["explicacion"]),
                ac["tipo"], propuesta, " | ".join(cl["alertas"] + ((ac.get("borrador") or {}).get("riesgos") or [])),
                "", "", "", "",
            ])

    if errores:
        (salida / "errores.json").write_text(json.dumps(errores, ensure_ascii=False, indent=1), encoding="utf-8")

    sinteticas = sum(c.sintetica for c in consultas)
    m = metricas(recs)
    meta = {
        "entrada": entrada,
        "jev": "simulado" if jev.simulado else getattr(jev, "modelo", "api"),
        "redactor": redactor.nombre,
        "plantillas_simuladas": catalogo.simular,
        "consultas": len(consultas),
        "sinteticas": sinteticas,
        "recomendaciones": len(recs),
        "errores": len(errores),
        "fecha": datetime.now().isoformat(timespec="seconds"),
    }
    (salida / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "metricas.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    informe_meta = {
        "entrada": entrada, "Jev": meta["jev"], "redactor": meta["redactor"],
        "plantillas": "SIMULADAS (ejemplos tratados como aprobadas)" if catalogo.simular else "solo aprobadas y vigentes",
        "datos_sinteticos": f"{sinteticas} consultas sintéticas" if sinteticas else "", "errores": len(errores), "fecha": meta["fecha"],
    }
    (salida / "informe.md").write_text(informe_md(m, informe_meta), encoding="utf-8")
    return {"meta": meta, "metricas": m, "errores": errores}
