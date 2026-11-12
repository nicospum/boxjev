"""Ajustes locales: claves de API y aprobación de envío externo.

Se guardan en config/ajustes.local.json (no se sube a git). Las claves nunca
se devuelven al navegador: solo se informa si están cargadas.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUTA = RAIZ / "config" / "ajustes.local.json"

PROVEEDORES = {
    "anthropic": {"nombre": "Claude (Anthropic)", "env": "ANTHROPIC_API_KEY", "modelo": "claude-opus-5-5",
                  "ayuda": "console.anthropic.com → API keys"},
    "openai": {"nombre": "ChatGPT (OpenAI)", "env": "OPENAI_API_KEY", "modelo": "gpt-4.1",
               "ayuda": "platform.openai.com → API keys"},
    "deepseek": {"nombre": "DeepSeek", "env": "DEEPSEEK_API_KEY", "modelo": "deepseek-chat",
                 "ayuda": "platform.deepseek.com → API keys"},
    "gemini": {"nombre": "Gemini (Google)", "env": "GEMINI_API_KEY", "modelo": "gemini-2.5-flash",
               "ayuda": "aistudio.google.com → Get API key"},
}
CLAVES = {"typesafe": "TYPESAFE_API_KEY", **{k: v["env"] for k, v in PROVEEDORES.items()}}

_candado = threading.Lock()


def _leer() -> dict:
    if RUTA.exists():
        return json.loads(RUTA.read_text(encoding="utf-8"))
    return {}


def _escribir(d: dict) -> None:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RUTA)


def clave(servicio: str) -> str | None:
    """Clave guardada en el panel; si no hay, la variable de entorno."""
    d = _leer()
    return (d.get("claves") or {}).get(servicio) or os.environ.get(CLAVES[servicio]) or None


def aprobado() -> bool:
    return bool(_leer().get("envio_externo_aprobado"))


def modelo(proveedor: str) -> str:
    return (_leer().get("modelos") or {}).get(proveedor) or PROVEEDORES[proveedor]["modelo"]


def proveedor_chat() -> str | None:
    d = _leer()
    p = d.get("proveedor_chat")
    if p in PROVEEDORES and clave(p):
        return p
    return next((k for k in PROVEEDORES if clave(k)), None)


def proveedor_borradores() -> str:
    p = _leer().get("proveedor_borradores") or "offline"
    return p if p == "offline" or (p in PROVEEDORES and clave(p)) else "offline"


def publico() -> dict:
    """Lo que puede ver el navegador (sin claves)."""
    d = _leer()
    return {
        "envio_externo_aprobado": bool(d.get("envio_externo_aprobado")),
        "typesafe": {"configurada": bool(clave("typesafe")), "desde_entorno": not (d.get("claves") or {}).get("typesafe") and bool(os.environ.get("TYPESAFE_API_KEY"))},
        "proveedores": {k: {**{x: v[x] for x in ("nombre", "ayuda")}, "configurada": bool(clave(k)), "modelo": modelo(k)} for k, v in PROVEEDORES.items()},
        "proveedor_chat": proveedor_chat(),
        "proveedor_borradores": proveedor_borradores(),
    }


def actualizar(cambios: dict) -> dict:
    with _candado:
        d = _leer()
        if "envio_externo_aprobado" in cambios:
            d["envio_externo_aprobado"] = bool(cambios["envio_externo_aprobado"])
        for servicio, valor in (cambios.get("claves") or {}).items():
            if servicio not in CLAVES:
                continue
            d.setdefault("claves", {})
            if valor:
                d["claves"][servicio] = str(valor).strip()
            else:
                d["claves"].pop(servicio, None)
        for prov, m in (cambios.get("modelos") or {}).items():
            if prov in PROVEEDORES:
                d.setdefault("modelos", {})[prov] = str(m).strip() or PROVEEDORES[prov]["modelo"]
        for campo in ("proveedor_chat", "proveedor_borradores"):
            if campo in cambios and (cambios[campo] in PROVEEDORES or cambios[campo] == "offline"):
                d[campo] = cambios[campo]
        _escribir(d)
    return publico()
