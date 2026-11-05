"""Circuito completo para una consulta en un momento dado.

    conversación hasta 'ahora' -> ventana 24 h (código) -> state -> Jev (juicios)
    -> reglas (segmento) -> acción: borrador libre | plantilla aprobada | esperar | derivar

En modo retrospectivo se reconstruyen los momentos en que Ventas tuvo que
decidir algo (`puntos_de_decision`) y se evalúa cada uno con lo que se sabía
entonces. Lo que pasó después queda en `observado`, separado, para comparar.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import estado as est
from .modelo import Consulta
from .plantillas import CatalogoPlantillas
from .preguntas import VERSION_PREGUNTAS, preguntas_para_jev
from .reglas import clasificar
from .ventana import MARGEN_SEGUIMIENTO_LIBRE, VENTANA, estado_ventana

UN_MINUTO = timedelta(minutes=1)
RAFAGA = timedelta(minutes=10)


def puntos_de_decision(c: Consulta) -> list[tuple[datetime, str]]:
    """Momentos en que el sistema habría generado una recomendación:
    - primer_contacto: llega el primer mensaje del prospecto.
    - cierre_ventana: pasaron 24 h desde el último entrante sin nuevo mensaje del prospecto
      (se evalúa 1 min después del cierre).
    - reactivacion: el prospecto vuelve a escribir después de que cerró la ventana.
    """
    entrantes = [m.ts for m in c.mensajes if m.autor == "cliente"]
    if not entrantes:
        return []
    # El primer contacto incluye la ráfaga inicial (mensajes seguidos en 10 min, antes de que responda Ventas).
    primer_ventas = next((m.ts for m in c.mensajes if m.autor == "ventas"), None)
    rafaga = [t for t in entrantes if t <= entrantes[0] + RAFAGA and (primer_ventas is None or t < primer_ventas)]
    puntos = [(max(rafaga) if rafaga else entrantes[0], "primer_contacto")]
    fin = c.mensajes[-1].ts
    for i, ts in enumerate(entrantes):
        siguiente = entrantes[i + 1] if i + 1 < len(entrantes) else None
        cierre = ts + VENTANA
        if siguiente is None or siguiente > cierre:
            puntos.append((cierre + UN_MINUTO, "cierre_ventana"))
            if siguiente is not None:
                puntos.append((siguiente, "reactivacion"))
    # no evaluar cierres muy posteriores al último mensaje registrado (más de 2 seguimientos)
    limite = fin + VENTANA * 3
    return [(t, m) for t, m in puntos if t <= limite]


def _observado(c: Consulta, ahora: datetime) -> dict:
    """Qué hizo Ventas y qué pasó después (NO se le muestra a Jev)."""
    despues = [m for m in c.mensajes if m.ts > ahora]
    sig_ventas = next((m for m in despues if m.autor == "ventas"), None)
    sig_cliente = next((m for m in despues if m.autor == "cliente"), None)
    return {
        "siguiente_mensaje_ventas": sig_ventas.texto if sig_ventas else None,
        "plantilla_usada_por_ventas": sig_ventas.plantilla_id if sig_ventas and sig_ventas.tipo == "plantilla" else None,
        "horas_hasta_respuesta_ventas": round((sig_ventas.ts - ahora).total_seconds() / 3600, 2) if sig_ventas else None,
        "prospecto_volvio_a_escribir": sig_cliente is not None,
        "resultado": c.resultado.get("estado", "desconocido"),
    }


def evaluar(c: Consulta, ahora: datetime, motivo: str, jev, redactor, catalogo: CatalogoPlantillas) -> dict:
    v = estado_ventana(c, ahora)
    state = est.construir_estado(c, ahora, v)
    preguntas = preguntas_para_jev()
    respuesta_jev = jev.preguntar(state, preguntas)

    msgs = c.mensajes_hasta(ahora)
    primer_ventas = next((m.ts for m in msgs if m.autor == "ventas"), None)
    hubo_dialogo = primer_ventas is not None and any(m.autor == "cliente" and m.ts > primer_ventas for m in msgs)
    clasif = clasificar(respuesta_jev["respuestas"], hubo_dialogo).a_dict()
    if primer_ventas is None:  # si Ventas todavía no escribió, que haya una pregunta pendiente es obvio
        clasif["alertas"] = [a for a in clasif["alertas"] if "pregunta" not in a]

    accion: dict
    seg = clasif["segmento"]
    if seg == "no_es_prospecto":
        accion = {"tipo": "derivar", "detalle": clasif["motivo_revision"]}
    elif seg == "desistio":
        accion = {"tipo": "cerrar_sin_mensaje", "detalle": "Registrar como perdido; no enviar plantillas."}
    elif v.abierta and v.ultimo_autor == "cliente":
        if seg in ("listo_para_reservar", "objecion_precio", "revision_humana"):
            accion = {"tipo": "atencion_humana_prioritaria", "detalle": clasif["motivo_revision"]}
        else:
            accion = {"tipo": "borrador_libre", "borrador": redactor.redactar(state["conversacion"], clasif)}
    elif v.abierta:
        # habló último Ventas y la ventana sigue abierta
        if v.horas_restantes <= MARGEN_SEGUIMIENTO_LIBRE.total_seconds() / 3600 and v.mensajes_ventas_sin_respuesta < 2:
            accion = {"tipo": "seguimiento_libre_antes_de_cierre",
                      "detalle": f"Quedan {v.horas_restantes:.1f} h de ventana: se puede enviar un último mensaje libre."}
        else:
            accion = {"tipo": "esperar", "detalle": f"Ventana abierta {v.horas_restantes:.1f} h más; Ventas ya respondió."}
    else:
        rec = catalogo.recomendar(seg, clasif["necesidad"], v.plantillas_sin_respuesta, ahora)
        accion = {"tipo": "plantilla" if rec["plantilla"] else "sin_plantilla", **rec}

    return {
        "id_consulta": c.id_consulta,
        "punto": motivo,
        "evaluado_en": ahora.isoformat(),
        "ventana": v.a_dict(),
        "mensaje_permitido": "libre" if v.abierta else "solo_plantilla_aprobada",
        "clasificacion": clasif,
        "accion": accion,
        "envio": "manual: una persona revisa y envía",
        "datos_utilizados": est.campos_usados(state),
        "jev": {"modelo": respuesta_jev["modelo"], "simulado": jev.simulado, "version_preguntas": VERSION_PREGUNTAS, "uso": respuesta_jev.get("uso")},
        "observado": _observado(c, ahora),
        # La etiqueta de Ventas describe el primer contacto; se compara solo ahí.
        "etiqueta_ventas": c.etiqueta_ventas if motivo == "primer_contacto" else None,
        "_payload": {"state": state, "respuestas_jev": respuesta_jev["respuestas"]},
    }
