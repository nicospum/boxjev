"""TODAS las preguntas que se le hacen a Jev, en un solo lugar.

Diseño (guía TypeSafe):
- Jev da juicios observables; la clasificación final la decide el código
  (`reglas.py`). Nunca se le pregunta "¿qué segmento es?" ni "¿qué hacer?".
- Una pregunta = un juicio. Choice + Noul compañero para el caso "ninguno".
- Las instrucciones van en inglés (mejor precisión según la doc de Jev); la
  conversación queda en español. Validar en la prueba retrospectiva.
- Todas las preguntas van en UNA sola llamada sobre el mismo state
  (fan-out especulativo): el código lee solo las que necesita.

Si cambiás un texto, subí VERSION_PREGUNTAS para poder comparar corridas.
"""
from __future__ import annotations

VERSION_PREGUNTAS = "2026-11-05.1"

# Sedes: nombre de opción descriptivo + barrios cercanos como criterio.
SEDES = {
    "nunez": "Núñez branch (CABA). Also nearby: Belgrano, Coghlan, Vicente López, Olivos",
    "palermo": "Palermo branch (CABA). Also nearby: Colegiales, Chacarita, Villa Crespo, Recoleta",
    "saavedra": "Saavedra branch (CABA). Also nearby: Villa Martelli, Florida, Munro",
    "villa_urquiza": "Villa Urquiza branch (CABA). Also nearby: Villa Pueyrredón, Parque Chas, Villa Ortúzar",
    "agronomia": "Agronomía branch (CABA). Also nearby: Villa del Parque, Paternal, Devoto",
    "almagro": "Almagro branch (CABA). Also nearby: Caballito, Boedo, Once, Balvanera, Centro",
    "tigre": "Tigre branch. Also nearby: Nordelta, San Fernando, Don Torcuato, Pacheco, zona norte",
    "quilmes_bernal": "Quilmes / Bernal branch. Also nearby: Avellaneda, Berazategui, Lanús, zona sur",
    "cordoba": "Córdoba city branch, in the province of Córdoba",
    "fuera_de_cobertura": "A city or province far from all branches, such as Rosario, Mar del Plata or Mendoza",
}

NECESIDADES = {
    "mudanza": "Moving to a new home, or between homes while waiting for the new one",
    "reforma": "Renovation, painting or construction work at home",
    "viaje_o_relocalizacion": "Travelling, living abroad or away for a period",
    "stock_empresa": "Storing a business's merchandise, stock, tools or equipment",
    "documentos_archivo": "Storing documents, files or archives",
    "espacio_extra": "Freeing up space at home: furniture, seasonal items, bikes, hobbies",
    "sucesion_o_separacion": "Emptying a relative's home, an inheritance, or a separation or divorce",
    "otra": "A reason different from all of the above",
}

TIPO_DE_MENSAJE = {
    "consulta_nueva": "The person wants information about renting a storage unit from Don Box",
    "cliente_actual": "The person already rents a unit and writes about access, payment, invoices or their contract",
    "empleo_o_proveedor": "The person is looking for a job, or offers a product, service or partnership to Don Box",
    "no_relacionado": "Spam, a wrong number, or a message unrelated to storage",
}

URGENCIA = [
    "The prospect gives no sign of when they need the storage unit",
    "The prospect needs the unit at some point in the coming months",
    "The prospect needs the unit within the next two or three weeks",
    "The prospect needs the unit this week or immediately",
]


def _noul(instr: str, true: str, false: str) -> dict:
    return {"type": "noul", "instructions": instr, "criteria": {"true": true, "false": false}}


PREGUNTAS: dict[str, dict] = {
    # --- Qué tipo de mensaje es ---
    "tipo_de_mensaje": {
        "type": "choice",
        "instructions": "What is the person who writes in `conversacion` contacting Don Box about?",
        "criteria": TIPO_DE_MENSAJE,
    },
    # --- Señales del prospecto (primer contacto y reclasificación) ---
    "dice_motivo": _noul(
        "Does the prospect say why they need a storage unit?",
        "The prospect states a reason, such as a move, a renovation, a trip or storing stock",
        "The prospect asks about storage without saying what situation they are in",
    ),
    "necesidad": {
        "type": "choice",
        "instructions": "Why does the prospect in `conversacion` need a storage unit?",
        "criteria": NECESIDADES,
    },
    "menciona_ubicacion": _noul(
        "Does the prospect say in which branch, neighborhood or city they want the storage unit?",
        "The prospect names a branch, a neighborhood, a city or an area, or picked one in `datos_del_formulario`",
        "The prospect gives no place, only asks in general",
    ),
    "sede": {
        "type": "choice",
        "instructions": "Which Don Box location is closest to where the prospect wants the storage unit?",
        "criteria": SEDES,
    },
    "describe_que_guarda": _noul(
        "Does the prospect describe what they want to store or what size of unit they need?",
        "The prospect lists items (furniture, boxes, appliances, stock) or gives a size in m² or m³",
        "The prospect does not say what they would store nor a size",
    ),
    "dice_cuando": _noul(
        "Does the prospect say when they need the storage unit?",
        "The prospect gives a date, a day of the week, or a period such as 'next month'",
        "The prospect gives no time reference for when they need it",
    ),
    "urgencia": {
        "type": "score",
        "instructions": "How soon does the prospect need the storage unit?",
        "criteria": URGENCIA,
    },
    "pide_precio": _noul(
        "Does the prospect ask for the price or the monthly cost?",
        "The prospect asks how much it costs, for rates, or for a quote",
        "The prospect does not ask about price",
    ),
    "es_empresa": _noul(
        "Is the storage unit for a company, shop or business?",
        "The prospect mentions a company, shop, business stock, an online store or work equipment",
        "The storage is for personal or household belongings",
    ),
    "quiere_visitar": _noul(
        "Does the prospect want to visit a branch or see a unit in person?",
        "The prospect asks to visit, to see a unit, or for opening hours to come by",
        "The prospect does not mention visiting",
    ),
    # --- Señales que solo importan si el prospecto ya conversó con Ventas ---
    "desistio": _noul(
        "Has the prospect said they no longer need a storage unit or chose another provider?",
        "The prospect says they solved it another way, found another place, or are no longer interested",
        "The prospect has not said they are no longer interested",
    ),
    "objecion_precio": _noul(
        "Has the prospect said the price is too high for them?",
        "The prospect says it is expensive, over budget, or asks for a discount",
        "The prospect has not complained about the price",
    ),
    "pidio_tiempo": _noul(
        "Has the prospect asked to be contacted later or said they will decide later?",
        "The prospect says they will think about it, will confirm later, or to write back in some days",
        "The prospect has not asked to postpone",
    ),
    "quiere_reservar": _noul(
        "Has the prospect said they want to reserve or rent a unit?",
        "The prospect asks how to reserve, how to pay, what documents they need, or says they will take it",
        "The prospect has not said they want to go ahead",
    ),
    "pregunta_sin_responder": _noul(
        "Did the prospect ask a question that Ventas Don Box has not answered yet in `conversacion`?",
        "The last question from the prospect has no answer from Ventas Don Box after it",
        "Every question from the prospect was answered, or the prospect asked nothing",
    ),
}


def preguntas_para_jev() -> dict[str, dict]:
    return PREGUNTAS
