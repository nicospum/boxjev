"""Categorías editables (las define Alberto) y la pregunta a Jev que las usa.

Cada categoría tiene una descripción escrita como situación observable. Jev
elige, para cada momento, la que mejor describe la conversación (Choice) y un
Noul compañero dice si alguna encaja de verdad. El código decide con eso:
- si ninguna encaja (p < 0,3) o Jev duda (confianza < 0,4) -> queda para revisar;
- si encaja -> la acción sale de la categoría (responder, plantilla, persona,
  derivar o no escribir), respetando siempre la ventana de 24 h.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path

ETAPA_POR_PUNTO = {"primer_contacto": "primer_contacto", "cierre_ventana": "post_24h", "reactivacion": "post_24h"}
ACCIONES = {
    "responder": "Responder (borrador si la ventana está abierta; plantilla si está cerrada)",
    "plantilla": "Enviar una plantilla aprobada",
    "persona": "Lo atiende una persona",
    "derivar": "Derivar a otra área",
    "no_escribir": "No escribir más",
}
ENCAJA_MIN = 0.3
CONFIANZA_MIN = 0.55  # por debajo, Jev reparte la probabilidad entre varias categorías
SIN_CATEGORIA = "sin_categoria"

_candado = threading.Lock()


class ErrorCategorias(ValueError):
    pass


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:40] or "categoria"


class Categorias:
    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)
        self.datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        self.datos.setdefault("eliminadas", [])

    # ------------------------------------------------------------ lectura
    @property
    def lista(self) -> list[dict]:
        return self.datos["categorias"]

    def de_etapa(self, etapa: str) -> list[dict]:
        return [c for c in self.lista if c["etapa"] == etapa]

    def obtener(self, cid: str) -> dict | None:
        return next((c for c in self.lista if c["id"] == cid), None)

    def nombre(self, cid: str) -> str:
        c = self.obtener(cid) or next((e for e in self.datos["eliminadas"] if e["id"] == cid), None)
        return c["nombre"] if c else ("Sin categoría" if cid == SIN_CATEGORIA else cid)

    def a_dict(self) -> dict:
        return {"etapas": self.datos["etapas"], "acciones": ACCIONES, "categorias": self.lista, "eliminadas": self.datos["eliminadas"]}

    # ------------------------------------------------------------ edición
    def _guardar(self) -> None:
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.ruta)

    def _validar(self, c: dict) -> dict:
        nombre = (c.get("nombre") or "").strip()
        desc = (c.get("descripcion") or "").strip()
        if not nombre:
            raise ErrorCategorias("La categoría necesita un nombre.")
        if len(desc) < 15:
            raise ErrorCategorias("La descripción tiene que contar la situación del prospecto (al menos una frase). Jev clasifica leyendo esa descripción.")
        if c.get("etapa") not in self.datos["etapas"]:
            raise ErrorCategorias(f"Etapa inválida. Opciones: {', '.join(self.datos['etapas'])}.")
        if c.get("accion") not in ACCIONES:
            raise ErrorCategorias(f"Acción inválida. Opciones: {', '.join(ACCIONES)}.")
        color = c.get("color") or "#6B7570"
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            color = "#6B7570"
        plantillas = [p for p in (c.get("plantillas") or []) if isinstance(p, str)]
        return {"etapa": c["etapa"], "nombre": nombre[:60], "descripcion": desc[:500], "accion": c["accion"], "color": color, "plantillas": plantillas}

    def crear(self, c: dict) -> dict:
        with _candado:
            limpio = self._validar(c)
            base = slug(limpio["nombre"])
            cid, n = base, 2
            while self.obtener(cid) or cid == SIN_CATEGORIA:
                cid, n = f"{base}_{n}", n + 1
            nueva = {"id": cid, **limpio}
            self.lista.append(nueva)
            self._guardar()
            return nueva

    def editar(self, cid: str, cambios: dict) -> dict:
        with _candado:
            c = self.obtener(cid)
            if not c:
                raise ErrorCategorias(f"No existe la categoría '{cid}'.")
            limpio = self._validar({**c, **{k: v for k, v in cambios.items() if v is not None}})
            if limpio["etapa"] != c["etapa"]:
                raise ErrorCategorias("No se puede cambiar la etapa de una categoría: creá una nueva.")
            c.update(limpio)
            self._guardar()
            return c

    def eliminar(self, cid: str) -> dict:
        with _candado:
            c = self.obtener(cid)
            if not c:
                raise ErrorCategorias(f"No existe la categoría '{cid}'.")
            if len(self.de_etapa(c["etapa"])) <= 1:
                raise ErrorCategorias("Tiene que quedar al menos una categoría en cada etapa.")
            self.datos["categorias"] = [x for x in self.lista if x["id"] != cid]
            self.datos["eliminadas"].append({"id": c["id"], "nombre": c["nombre"], "etapa": c["etapa"]})
            self._guardar()
            return c


# ---------------------------------------------------------------- preguntas a Jev
def preguntas(cats: list[dict]) -> dict:
    """Choice entre las categorías de una etapa + Noul compañero (¿encaja alguna?)."""
    if not cats:
        return {}
    situaciones = "; ".join(f"{c['nombre']}: {c['descripcion']}" for c in cats)
    return {
        "categoria": {
            "type": "choice",
            "instructions": "Which of these situations best describes the prospect in `conversacion`?",
            "criteria": {c["id"]: c["descripcion"] for c in cats},
        },
        "categoria_encaja": {
            "type": "noul",
            "instructions": f"Does the prospect in `conversacion` fit at least one of these situations? {situaciones}",
            "criteria": {
                "true": "The conversation clearly shows one of the listed situations",
                "false": "The conversation shows a situation that none of the listed descriptions covers",
            },
        },
    }


def leer(respuestas: dict, cats: list[dict]) -> dict:
    """Convierte las respuestas de Jev en la categoría asignada."""
    ch = respuestas.get("categoria")
    if not ch or not cats:
        return {"id": SIN_CATEGORIA, "confianza": 0.0, "encaja": 0.0, "alternativas": [], "revisar": True,
                "motivo": "No hay categorías definidas para esta etapa."}
    probs = ch.get("probabilities") or {}
    alternativas = sorted(({"id": k, "prob": round(float(v), 3)} for k, v in probs.items()), key=lambda x: -x["prob"])[:3]
    encaja = float((respuestas.get("categoria_encaja") or {}).get("noul", 1.0))
    conf = float(ch.get("confidence") or 0.0)
    if encaja < ENCAJA_MIN:
        return {"id": SIN_CATEGORIA, "sugerida": ch["choice"], "confianza": conf, "encaja": encaja, "alternativas": alternativas,
                "revisar": True, "motivo": "Ninguna categoría describe bien esta conversación."}
    revisar = conf < CONFIANZA_MIN
    return {"id": ch["choice"], "confianza": round(conf, 3), "encaja": round(encaja, 3), "alternativas": alternativas,
            "revisar": revisar, "motivo": "Jev duda entre varias categorías." if revisar else None}
