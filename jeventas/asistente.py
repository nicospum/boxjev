"""Chat asistente: un modelo de IA (Claude, OpenAI, DeepSeek o Gemini) maneja el panel
con lenguaje natural usando herramientas. Jev sigue siendo quien clasifica.

Reglas:
- Lo que se puede deshacer (crear/editar categoría, mover un contacto, reclasificar)
  se ejecuta directo y queda a la vista.
- Eliminar una categoría NO se ejecuta desde el chat: el asistente lo propone y
  aparece un botón para que la persona confirme.
- El asistente no envía mensajes a clientes ni toca HubSpot/Atom.
"""
from __future__ import annotations

import json

from jeventas import proveedores

SISTEMA = """Sos el asistente del panel JeVentas de Don Box (alquiler de bauleras / self storage).
El panel ayuda al equipo de Ventas a clasificar consultas de WhatsApp. Jev (TypeSafe) clasifica cada
conversación en categorías que define Alberto (jefe de Ventas); vos ayudás a manejar el panel.

Hay dos etapas de categorías: "primer_contacto" (el primer mensaje del prospecto) y "post_24h"
(cuando pasaron 24 h sin respuesta o el prospecto volvió a escribir). Cada categoría tiene una
descripción escrita como situación observable: Jev clasifica leyendo esa descripción, así que
tiene que ser concreta (qué dice o hace el prospecto), una sola situación, sin depender de otras.

Cómo trabajar:
- Usá las herramientas para consultar datos antes de responder; no inventes números ni contactos.
- Crear, editar categorías, mover contactos y reclasificar se hacen directo. Contá qué hiciste.
- Para eliminar una categoría usá proponer_eliminar_categoria: la persona confirma con un botón.
- Si cambian descripciones, ofrecé reclasificar el lote para que Jev vuelva a ubicar a los contactos.
- Para mostrar algo en pantalla usá mostrar.
- Nunca enviás mensajes a clientes. Respondé en español rioplatense, breve y claro.
Lote abierto en pantalla: {lote}."""


def _p(props: dict, req: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


_S = {"type": "string"}
HERRAMIENTAS = [
    {"name": "listar_lotes", "description": "Lista los lotes de conversaciones analizadas.", "parameters": _p({}, [])},
    {"name": "resumen_lote", "description": "Cantidad de contactos por categoría en un lote y sugerencias pendientes.",
     "parameters": _p({"lote": _S}, ["lote"])},
    {"name": "ver_categorias", "description": "Lista las categorías (id, etapa, nombre, descripción, acción, plantillas).",
     "parameters": _p({}, [])},
    {"name": "contactos_de_categoria", "description": "Contactos que están hoy en una categoría dentro de un lote.",
     "parameters": _p({"lote": _S, "categoria": {**_S, "description": "id de la categoría"}}, ["lote", "categoria"])},
    {"name": "ver_consulta", "description": "Conversación completa de un contacto y sus momentos de decisión (con su 'clave').",
     "parameters": _p({"lote": _S, "id_consulta": _S}, ["lote", "id_consulta"])},
    {"name": "crear_categoria", "description": "Crea una categoría nueva.",
     "parameters": _p({"etapa": {"type": "string", "enum": ["primer_contacto", "post_24h"]}, "nombre": _S,
                       "descripcion": {**_S, "description": "Situación observable del prospecto, una o dos frases."},
                       "accion": {"type": "string", "enum": ["responder", "plantilla", "persona", "derivar", "no_escribir"]},
                       "plantillas": {"type": "array", "items": _S}}, ["etapa", "nombre", "descripcion", "accion"])},
    {"name": "editar_categoria", "description": "Cambia nombre, descripción, acción, color o plantillas de una categoría.",
     "parameters": _p({"id": _S, "nombre": _S, "descripcion": _S,
                       "accion": {"type": "string", "enum": ["responder", "plantilla", "persona", "derivar", "no_escribir"]},
                       "color": _S, "plantillas": {"type": "array", "items": _S}}, ["id"])},
    {"name": "proponer_eliminar_categoria", "description": "Propone eliminar una categoría. No la elimina: muestra un botón para que la persona confirme.",
     "parameters": _p({"id": _S, "motivo": _S}, ["id"])},
    {"name": "mover_contacto", "description": "Cambia la categoría de un momento de una consulta (usar la 'clave' de ver_consulta).",
     "parameters": _p({"lote": _S, "clave": _S, "categoria": _S}, ["lote", "clave", "categoria"])},
    {"name": "reclasificar_lote", "description": "Jev vuelve a elegir la categoría de cada contacto del lote con las descripciones actuales.",
     "parameters": _p({"lote": _S}, ["lote"])},
    {"name": "mostrar", "description": "Cambia lo que se ve en pantalla.",
     "parameters": _p({"vista": {"type": "string", "enum": ["consultas", "categorias", "resumen"]},
                       "lote": _S, "categoria": _S, "id_consulta": _S}, ["vista"])},
]


def conversar(proveedor: str, historial: list[dict], lote: str | None, acciones) -> dict:
    """historial: [{'rol': 'user'|'assistant', 'texto': ...}], el último es el pedido nuevo.
    acciones: módulo panel.acciones (inyectado para poder probar)."""
    ia = proveedores.crear(proveedor)
    ui: list[dict] = []
    confirmaciones: list[dict] = []
    cambios = False

    def ejecutar(nombre: str, a: dict) -> dict:
        nonlocal cambios
        try:
            if nombre == "listar_lotes":
                return {"lotes": [{"nombre": l["nombre"], "consultas": l["meta"].get("consultas"), "jev": l["meta"].get("jev")}
                                  for l in acciones.listar_lotes()]}
            if nombre == "resumen_lote":
                return acciones.resumen_lote(a["lote"])
            if nombre == "ver_categorias":
                return acciones.ver_categorias()
            if nombre == "contactos_de_categoria":
                return acciones.miembros(a["lote"], a["categoria"], limite=30)
            if nombre == "ver_consulta":
                return acciones.ver_consulta(a["lote"], a["id_consulta"])
            if nombre == "crear_categoria":
                cambios = True
                return {"creada": acciones.crear_categoria(a)}
            if nombre == "editar_categoria":
                cambios = True
                cid = a.pop("id")
                return {"editada": acciones.editar_categoria(cid, a)}
            if nombre == "proponer_eliminar_categoria":
                cats = acciones.ver_categorias()["categorias"]
                c = next((x for x in cats if x["id"] == a["id"]), None)
                if not c:
                    return {"error": f"No existe la categoría '{a['id']}'."}
                confirmaciones.append({"tipo": "eliminar_categoria", "id": c["id"], "nombre": c["nombre"], "motivo": a.get("motivo", "")})
                return {"ok": "Se mostró un botón para que la persona confirme. Todavía no se eliminó."}
            if nombre == "mover_contacto":
                cambios = True
                return acciones.mover(a["lote"], a["clave"], a["categoria"], origen="asistente")
            if nombre == "reclasificar_lote":
                cambios = True
                return acciones.reclasificar_lote(a["lote"])
            if nombre == "mostrar":
                ui.append({k: v for k, v in a.items() if v})
                return {"ok": True}
            return {"error": f"Herramienta desconocida: {nombre}"}
        except acciones.ErrorPanel as e:
            return {"error": str(e)}
        except KeyError as e:
            return {"error": f"Falta el dato {e}."}

    r = ia.conversar(SISTEMA.format(lote=lote or "ninguno"), historial, HERRAMIENTAS, ejecutar)
    return {"texto": r["texto"], "pasos": r["pasos"], "ui": ui, "confirmaciones": confirmaciones, "cambios": cambios,
            "modelo": getattr(ia, "modelo", proveedor)}


def resumen_pasos(pasos: list[dict]) -> str:
    return "\n".join(f"- {p['herramienta']}({json.dumps(p['argumentos'], ensure_ascii=False)})" for p in pasos)
