"""Redacción de borradores de respuesta (modelo generativo, distinto de Jev).

Solo se usa con la ventana de 24 h abierta. Nunca envía: devuelve un borrador
que una persona revisa, corrige y envía a mano.

- `RedactorOffline`: textos base por segmento, sin red. Para probar el circuito.
- `RedactorClaude`: Claude (Anthropic API). Bloqueado salvo aprobación de
  Don Box para enviar conversaciones a un proveedor externo.

Toda salida pasa por `verificar_borrador`, que marca precios, montos o
promesas de disponibilidad para revisión.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .jev import detectar_pii

MODELO_CLAUDE = "claude-opus-5-5"

_RIESGOS = {
    "menciona un monto": re.compile(r"\$\s?\d|\d+\s?(pesos|usd|dólares|ars)\b", re.I),
    "promete disponibilidad": re.compile(r"\b(tenemos disponible|te la reservamos|está libre|garantizad)", re.I),
    "menciona descuento": re.compile(r"\b(descuento|bonificaci|promo)", re.I),
}


def verificar_borrador(texto: str) -> list[str]:
    return [nombre for nombre, pat in _RIESGOS.items() if pat.search(texto)]


def _pedir(faltan: list[str]) -> str:
    """Pregunta por los dos datos faltantes más útiles para cotizar."""
    frases = {
        "sucursal o zona": "en qué zona o sucursal te queda mejor",
        "qué quiere guardar o tamaño": "qué te gustaría guardar (muebles, cajas o medidas aproximadas)",
        "desde cuándo lo necesita": "desde cuándo lo necesitarías",
        "para qué lo necesita": "si es por una mudanza, una obra u otro motivo",
    }
    items = [frases[f] for f in faltan if f in frases][:2]
    if not items:
        return ""
    return "¿Me contás " + " y ".join(items) + "?"


class RedactorOffline:
    nombre = "offline"

    def __init__(self, info: dict) -> None:
        self.info = info

    def redactar(self, conversacion: list[dict], clasif: dict) -> dict:
        seg = clasif["segmento"]
        sede = self.info["sedes"].get(clasif.get("sede") or "", None)
        pedido = _pedir(clasif["datos_faltantes"])
        lugar = f" en {sede['nombre']}" if sede and clasif.get("sede") != "fuera_de_cobertura" else ""
        if seg == "alta_intencion":
            dire = f" ({sede['direccion']})" if lugar else ""
            texto = (f"¡Hola! Gracias por escribirnos. Te ayudamos con la baulera{lugar}{dire}. "
                     + (f"{pedido} Así te pasamos la cotización con las opciones que encajan. " if pedido
                        else "Te pasamos la cotización con las opciones que encajan. ")
                     + "La unidad se confirma al momento de la reserva.")
        elif seg == "lista_para_cotizar":
            texto = f"¡Hola! Gracias por escribir a Don Box. Podemos cotizarte una baulera{lugar}. " + (f"{pedido} Así te paso las opciones." if pedido else "Te paso las opciones.")
        elif seg in ("exploratoria", "informacion_insuficiente"):
            texto = "¡Hola! Gracias por escribir a Don Box. Para recomendarte el tamaño y la sede, " + (
                "¿me" + pedido[3:] if pedido else "contame un poco más qué necesitás.")
        elif seg == "pidio_tiempo":
            texto = "¡Perfecto! Quedamos atentos. Cuando lo tengas definido, escribinos por acá y retomamos."
        else:
            texto = ""
        return {"texto": texto, "modelo": "offline", "riesgos": verificar_borrador(texto)}


_SISTEMA = """Sos asistente del equipo de Ventas de Don Box (alquiler de bauleras / self storage en Argentina).
Redactás UN borrador de respuesta por WhatsApp que una persona de Ventas va a revisar y enviar.
Reglas:
- Usá solo la información comercial que aparece en <info_comercial>. Si falta un dato, no lo inventes.
- No informes precios, montos ni promociones. No prometas disponibilidad ni fechas.
- Respondé primero lo que el prospecto preguntó, si la información está disponible.
- Pedí como máximo los dos datos faltantes más útiles para cotizar.
- Español rioplatense con voseo, cordial, breve (2 a 4 oraciones), sin emojis excesivos.
Devolvé solo el texto del mensaje."""


class RedactorIA:
    """Borrador con un modelo generativo (Claude, OpenAI, DeepSeek o Gemini; ver proveedores.py)."""

    def __init__(self, info: dict, proveedor: str, envio_externo_aprobado: bool | None = None) -> None:
        from . import proveedores

        self.ia = proveedores.crear(proveedor, envio_externo_aprobado)
        self.info = info
        self.nombre = proveedor

    def redactar(self, conversacion: list[dict], clasif: dict) -> dict:
        if detectar_pii(conversacion):
            raise RuntimeError("La conversación contiene posibles datos personales; anonimizar antes.")
        info = dict(self.info)
        if clasif.get("sede") in info["sedes"]:
            info["sedes"] = {clasif["sede"]: info["sedes"][clasif["sede"]]}
        cat = clasif.get("categoria") or {}
        contexto = {k: clasif.get(k) for k in ("necesidad", "sede", "datos_faltantes", "alertas")}
        contexto["categoria"] = {"nombre": cat.get("nombre"), "descripcion": cat.get("descripcion")}
        usuario = (
            f"<info_comercial>\n{json.dumps(info, ensure_ascii=False, indent=1)}\n</info_comercial>\n"
            f"<clasificacion>\n{json.dumps(contexto, ensure_ascii=False)}\n</clasificacion>\n"
            f"<conversacion>\n{json.dumps(conversacion, ensure_ascii=False, indent=1)}\n</conversacion>\n"
            "Redactá el próximo mensaje de Ventas."
        )
        texto = self.ia.generar(_SISTEMA, usuario)
        if not texto:
            return {"texto": "", "modelo": self.ia.modelo, "riesgos": ["el modelo no generó borrador"]}
        return {"texto": texto, "modelo": self.ia.modelo, "riesgos": verificar_borrador(texto)}


def RedactorClaude(info: dict, envio_externo_aprobado: bool) -> RedactorIA:  # noqa: N802 (compatibilidad CLI)
    return RedactorIA(info, "anthropic", envio_externo_aprobado)


def cargar_info(ruta: str | Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))
