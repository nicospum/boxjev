"""Modelos de IA generativa para el chat asistente y los borradores.

- Claude: SDK oficial de Anthropic.
- OpenAI, DeepSeek y Gemini: API compatible con OpenAI (chat/completions con tools).

Se usan con API keys (se pagan por uso). Las suscripciones de consumo
(ChatGPT Plus, Claude Pro, Gemini Advanced) no se pueden conectar a apps propias.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable

from . import ajustes

URLS_COMPATIBLES = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}
MAX_PASOS = 8

Ejecutor = Callable[[str, dict], dict]


class ErrorProveedor(RuntimeError):
    pass


def _resumen(x, n=300) -> str:
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def _sin_extras(x):
    """Gemini rechaza 'additionalProperties' en los esquemas de funciones."""
    if isinstance(x, dict):
        return {k: _sin_extras(v) for k, v in x.items() if k != "additionalProperties"}
    if isinstance(x, list):
        return [_sin_extras(i) for i in x]
    return x


class Claude:
    def __init__(self, api_key: str, modelo: str) -> None:
        import anthropic  # import diferido

        self.anthropic = anthropic
        # base_url explícita: no heredar proxies de otras herramientas del entorno
        self.cliente = anthropic.Anthropic(api_key=api_key, base_url=os.environ.get("JEVENTAS_ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
        self.modelo = modelo

    def _crear(self, **kw):
        try:
            return self.cliente.messages.create(
                model=self.modelo, max_tokens=8000,
                extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                extra_body={"output_config": {"effort": "low"}, "fallbacks": "default"},
                **kw,
            )
        except self.anthropic.AuthenticationError as e:
            raise ErrorProveedor("La clave de Claude no es válida. Revisala en Ajustes.") from e
        except self.anthropic.RateLimitError as e:
            raise ErrorProveedor("Claude está limitando pedidos (rate limit). Probá en un minuto.") from e
        except self.anthropic.APIStatusError as e:
            raise ErrorProveedor(f"Claude respondió con error {e.status_code}: {str(e)[:300]}") from e
        except self.anthropic.APIConnectionError as e:
            raise ErrorProveedor("No se pudo conectar con Claude.") from e

    def generar(self, sistema: str, usuario: str) -> str:
        r = self._crear(system=sistema, messages=[{"role": "user", "content": usuario}])
        if r.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in r.content if b.type == "text").strip()

    def conversar(self, sistema: str, historial: list[dict], herramientas: list[dict], ejecutar: Ejecutor) -> dict:
        msgs = [{"role": h["rol"] if h["rol"] == "user" else "assistant", "content": h["texto"]} for h in historial]
        tools = [{"name": h["name"], "description": h["description"], "input_schema": h["parameters"]} for h in herramientas]
        pasos = []
        for _ in range(MAX_PASOS):
            r = self._crear(system=sistema, messages=msgs, tools=tools)
            if r.stop_reason == "refusal":
                return {"texto": "El modelo no quiso responder este pedido.", "pasos": pasos}
            usos = [b for b in r.content if b.type == "tool_use"]
            if not usos:
                return {"texto": "".join(b.text for b in r.content if b.type == "text").strip(), "pasos": pasos}
            msgs.append({"role": "assistant", "content": r.content})
            resultados = []
            for u in usos:
                res = ejecutar(u.name, dict(u.input or {}))
                pasos.append({"herramienta": u.name, "argumentos": u.input, "resultado": _resumen(res)})
                resultados.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(res, ensure_ascii=False),
                                   **({"is_error": True} if "error" in res else {})})
            msgs.append({"role": "user", "content": resultados})
        return {"texto": "Hice varios pasos y me detuve. Pedime que siga si falta algo.", "pasos": pasos}


class Compatible:
    """OpenAI, DeepSeek y Gemini (endpoint compatible con OpenAI)."""

    def __init__(self, proveedor: str, api_key: str, modelo: str) -> None:
        self.url = URLS_COMPATIBLES[proveedor]
        self.proveedor = proveedor
        self.api_key = api_key
        self.modelo = modelo

    def _post(self, cuerpo: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403):
                raise ErrorProveedor(f"La clave de {ajustes.PROVEEDORES[self.proveedor]['nombre']} no es válida. Revisala en Ajustes.") from e
            raise ErrorProveedor(f"{ajustes.PROVEEDORES[self.proveedor]['nombre']} respondió con error {e.code}: {detalle}") from e
        except urllib.error.URLError as e:
            raise ErrorProveedor(f"No se pudo conectar con {ajustes.PROVEEDORES[self.proveedor]['nombre']}.") from e

    def generar(self, sistema: str, usuario: str) -> str:
        d = self._post({"model": self.modelo, "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]})
        return (d["choices"][0]["message"].get("content") or "").strip()

    def conversar(self, sistema: str, historial: list[dict], herramientas: list[dict], ejecutar: Ejecutor) -> dict:
        msgs = [{"role": "system", "content": sistema}] + [
            {"role": "user" if h["rol"] == "user" else "assistant", "content": h["texto"]} for h in historial]
        tools = [{"type": "function", "function": {**h, "parameters": _sin_extras(h["parameters"])}} for h in herramientas]
        pasos = []
        for _ in range(MAX_PASOS):
            d = self._post({"model": self.modelo, "messages": msgs, "tools": tools})
            m = d["choices"][0]["message"]
            llamadas = m.get("tool_calls") or []
            if not llamadas:
                return {"texto": (m.get("content") or "").strip(), "pasos": pasos}
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": llamadas})
            for ll in llamadas:
                try:
                    args = json.loads(ll["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args, res = {}, {"error": "Argumentos inválidos (JSON mal formado)."}
                else:
                    res = ejecutar(ll["function"]["name"], args)
                pasos.append({"herramienta": ll["function"]["name"], "argumentos": args, "resultado": _resumen(res)})
                msgs.append({"role": "tool", "tool_call_id": ll["id"], "content": json.dumps(res, ensure_ascii=False)})
        return {"texto": "Hice varios pasos y me detuve. Pedime que siga si falta algo.", "pasos": pasos}


def crear(proveedor: str, envio_externo_aprobado: bool | None = None):
    """envio_externo_aprobado: None = usar lo que dice Ajustes; True/False = forzar (línea de comandos)."""
    if proveedor not in ajustes.PROVEEDORES:
        raise ErrorProveedor(f"Proveedor desconocido: {proveedor}")
    key = ajustes.clave(proveedor)
    if not key:
        raise ErrorProveedor(f"Falta la clave de {ajustes.PROVEEDORES[proveedor]['nombre']}. Cargala en Ajustes.")
    if not (ajustes.aprobado() if envio_externo_aprobado is None else envio_externo_aprobado):
        raise ErrorProveedor("Para usar IA externa, activá en Ajustes que Don Box aprobó enviar conversaciones anonimizadas.")
    m = ajustes.modelo(proveedor)
    return Claude(key, m) if proveedor == "anthropic" else Compatible(proveedor, key, m)
