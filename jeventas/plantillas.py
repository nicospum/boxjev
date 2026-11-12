"""Recomendación de plantillas de WhatsApp (solo fuera de la ventana de 24 h).

Reglas duras (código, no modelo):
- Solo plantillas con estado 'aprobada' y vigentes a la fecha de evaluación.
  Nunca se genera ni se edita una plantilla.
- No se recomiendan plantillas a quien desistió, no es prospecto o quiere
  reservar/objeta precio (eso lo maneja una persona).
- Máximo N plantillas seguidas sin respuesta (config): las plantillas sirven
  para reenganchar, no para presionar.
- Si ninguna aprobada encaja -> sin plantilla, revisión humana.
Modo laboratorio (`simular=True`): trata las de estado 'ejemplo' como aprobadas
para poder probar la lógica antes de tener el listado real. Queda marcado.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

SIN_PLANTILLA = {"desistio", "no_es_prospecto", "listo_para_reservar", "objecion_precio", "revision_humana"}


class CatalogoPlantillas:
    def __init__(self, ruta: str | Path, simular: bool = False) -> None:
        data = json.loads(Path(ruta).read_text(encoding="utf-8"))
        self.plantillas = data["plantillas"]
        self.max_sin_respuesta = int(data.get("max_plantillas_sin_respuesta", 2))
        self.simular = simular

    def _habilitada(self, p: dict, hoy: date) -> tuple[bool, str]:
        estados_ok = {"aprobada", "ejemplo"} if self.simular else {"aprobada"}
        if p["estado"] not in estados_ok:
            return False, f"estado '{p['estado']}'"
        if p.get("vigente_desde") and hoy < date.fromisoformat(p["vigente_desde"]):
            return False, "todavía no vigente"
        if p.get("vigente_hasta") and hoy > date.fromisoformat(p["vigente_hasta"]):
            return False, "vencida"
        return True, "ok"

    def recomendar(self, segmento: str, necesidad: str | None, plantillas_sin_respuesta: int, ahora: datetime,
                   ids: list[str] | None = None) -> dict:
        """ids: plantillas elegidas para la categoría (si se pasan, mandan sobre 'uso_previsto')."""
        if ids is None and segmento in SIN_PLANTILLA:
            return {"plantilla": None, "motivo": f"No corresponde plantilla para el segmento '{segmento}'.", "revision_humana": segmento != "desistio"}
        if plantillas_sin_respuesta >= self.max_sin_respuesta:
            return {"plantilla": None, "motivo": f"Ya se enviaron {plantillas_sin_respuesta} plantillas sin respuesta: pausar el seguimiento.", "revision_humana": False}

        numero = plantillas_sin_respuesta + 1
        candidatas, descartes = [], []
        for p in self.plantillas:
            ok, por_que = self._habilitada(p, ahora.date())
            uso = p["uso_previsto"]
            if not ok:
                descartes.append({"id": p["id"], "motivo": por_que})
                continue
            if numero not in uso.get("seguimiento_numero", [1, 2]):
                continue
            if ids is not None:
                if p["id"] in ids:
                    candidatas.append(((necesidad in uso["necesidades"]) * 2 - ids.index(p["id"]) / 100, p))
                continue
            seg_ok = "*" in uso["segmentos"] or segmento in uso["segmentos"]
            nec_ok = "*" in uso["necesidades"] or (necesidad in uso["necesidades"])
            if not (seg_ok and nec_ok):
                continue
            # más específica primero: coincidencia exacta de segmento y necesidad
            especificidad = (segmento in uso["segmentos"]) + (necesidad in uso["necesidades"])
            candidatas.append((especificidad, p))

        if not candidatas:
            motivo = ("Ninguna de las plantillas elegidas para esta categoría está aprobada y vigente." if ids
                      else "Ninguna plantilla aprobada y vigente encaja con este caso.")
            return {"plantilla": None, "motivo": motivo, "revision_humana": True, "descartadas": descartes}

        candidatas.sort(key=lambda x: -x[0])
        elegida = candidatas[0][1]
        return {
            "plantilla": {
                "id": elegida["id"],
                "nombre_meta": elegida["nombre_meta"],
                "texto": elegida["texto"],
                "variables": elegida.get("variables", []),
                "estado": elegida["estado"],
            },
            "alternativas": [p["id"] for _, p in candidatas[1:3]],
            "seguimiento_numero": numero,
            "motivo": (f"Elegida para la categoría '{segmento}'" if ids else f"Encaja con segmento '{segmento}'")
                      + (f" y necesidad '{necesidad}'" if necesidad else "") + f"; seguimiento n.º {numero}.",
            "simulada": elegida["estado"] != "aprobada",
            "revision_humana": False,
        }
