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
from .categorias import ETAPA_POR_PUNTO, SIN_CATEGORIA, Categorias
from .categorias import leer as leer_categoria
from .categorias import preguntas as preguntas_categoria
from .modelo import Consulta
from .plantillas import CatalogoPlantillas
from .preguntas import VERSION_PREGUNTAS, preguntas_para_jev
from .reglas import clasificar
from .ventana import MARGEN_SEGUIMIENTO_LIBRE, VENTANA, estado_ventana  # noqa: F401

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


EQUIVALENCIA_SEGMENTO = {"listo_para_reservar": "quiere_reservar"}


def categoria_desde_jev(respuestas: dict, cats_etapa: list[dict], etapa: str, segmento: str | None = None) -> dict:
    """segmento: lo que indican las preguntas puntuales (reglas.py). Si equivale a una categoría
    existente y Jev eligió otra con la descripción completa, gana la de las señales y queda para revisar:
    con condiciones compuestas ("zona Y pronto") las preguntas puntuales son más confiables."""
    lect = leer_categoria(respuestas, cats_etapa)
    ids = {c["id"] for c in cats_etapa}
    por_senales = EQUIVALENCIA_SEGMENTO.get(segmento or "", segmento)
    if por_senales in ids and lect["id"] not in (SIN_CATEGORIA, por_senales):
        nombre = {c["id"]: c["nombre"] for c in cats_etapa}
        lect.update({"elegida_por_jev": lect["id"], "id": por_senales, "revisar": True, "por_senales": True,
                     "motivo": f"Con la descripción completa Jev eligió «{nombre[lect['id']]}», pero las preguntas puntuales indican «{nombre[por_senales]}»."})
    c = next((x for x in cats_etapa if x["id"] == lect["id"]), None)
    lect.update({"etapa": etapa, "origen": "jev"})
    if c:
        lect.update({k: c[k] for k in ("nombre", "descripcion", "accion", "color")})
    else:
        lect.update({"nombre": "Sin categoría", "descripcion": lect.get("motivo") or "", "accion": None, "color": "#C77D12"})
    return lect


def _seguimiento_o_espera(v: dict) -> dict:
    if v["horas_restantes"] <= MARGEN_SEGUIMIENTO_LIBRE.total_seconds() / 3600 and v["mensajes_ventas_sin_respuesta"] < 2:
        return {"tipo": "seguimiento_libre_antes_de_cierre",
                "detalle": f"Quedan {v['horas_restantes']:.1f} h de ventana: se puede enviar un último mensaje libre."}
    return {"tipo": "esperar", "detalle": f"Ventana abierta {v['horas_restantes']:.1f} h más; Ventas ya respondió."}


def decidir_por_categoria(clasif: dict, v: dict, conversacion: list[dict], cats: Categorias, redactor, catalogo: CatalogoPlantillas, ahora: datetime) -> dict:
    """La acción la define la categoría; la ventana de 24 h la limita siempre."""
    cat = clasif["categoria"]
    if cat["id"] == SIN_CATEGORIA:
        return {"tipo": "revisar_categoria", "detalle": cat.get("motivo") or "Elegí la categoría a mano."}
    accion = cat["accion"]
    if accion == "derivar":
        return {"tipo": "derivar", "detalle": f"Categoría '{cat['nombre']}': derivar a quien corresponda."}
    if accion == "no_escribir":
        return {"tipo": "cerrar_sin_mensaje", "detalle": "Registrar como perdido; no enviar más mensajes."}
    if accion == "persona":
        return {"tipo": "atencion_humana_prioritaria", "detalle": f"Categoría '{cat['nombre']}': lo atiende una persona."}
    # responder / plantilla
    if v["abierta"] and v["ultimo_autor"] == "cliente":
        return {"tipo": "borrador_libre", "borrador": redactor.redactar(conversacion, clasif)}
    if v["abierta"]:
        return _seguimiento_o_espera(v)
    definida = cats.obtener(cat["id"]) or {}
    rec = catalogo.recomendar(cat["id"], clasif.get("necesidad"), v["plantillas_sin_respuesta"], ahora,
                              ids=definida.get("plantillas") or None)
    return {"tipo": "plantilla" if rec["plantilla"] else "sin_plantilla", **rec}


def _decidir_por_segmento(clasif: dict, v, state: dict, redactor, catalogo: CatalogoPlantillas, ahora: datetime) -> dict:
    """Decisión por la tabla fija de reglas.py (sin categorías editables)."""
    seg = clasif["segmento"]
    if seg == "no_es_prospecto":
        return {"tipo": "derivar", "detalle": clasif["motivo_revision"]}
    if seg == "desistio":
        return {"tipo": "cerrar_sin_mensaje", "detalle": "Registrar como perdido; no enviar plantillas."}
    if v.abierta and v.ultimo_autor == "cliente":
        if seg in ("listo_para_reservar", "objecion_precio", "revision_humana"):
            return {"tipo": "atencion_humana_prioritaria", "detalle": clasif["motivo_revision"]}
        return {"tipo": "borrador_libre", "borrador": redactor.redactar(state["conversacion"], clasif)}
    if v.abierta:
        return _seguimiento_o_espera(v.a_dict())
    rec = catalogo.recomendar(seg, clasif["necesidad"], v.plantillas_sin_respuesta, ahora)
    return {"tipo": "plantilla" if rec["plantilla"] else "sin_plantilla", **rec}


def reclasificar(rec: dict, state: dict, jev, cats: Categorias, redactor, catalogo: CatalogoPlantillas, solo_entre: list[str] | None = None) -> dict:
    """Vuelve a preguntar a Jev SOLO la categoría (sobre el state guardado) y recalcula la acción.
    solo_entre: limitar a esas categorías (para sugerir a dónde mover a los que quedaron sueltos)."""
    etapa = ETAPA_POR_PUNTO[rec["punto"]]
    cats_etapa = [c for c in cats.de_etapa(etapa) if not solo_entre or c["id"] in solo_entre]
    resp = jev.preguntar(state, preguntas_categoria(cats_etapa))
    nuevo = dict(rec)
    segmento = None if solo_entre else rec["clasificacion"].get("segmento")
    nuevo["clasificacion"] = {**rec["clasificacion"], "categoria": categoria_desde_jev(resp["respuestas"], cats_etapa, etapa, segmento)}
    nuevo["accion"] = decidir_por_categoria(nuevo["clasificacion"], rec["ventana"], state["conversacion"], cats, redactor, catalogo,
                                            datetime.fromisoformat(rec["evaluado_en"]))
    return nuevo


def evaluar(c: Consulta, ahora: datetime, motivo: str, jev, redactor, catalogo: CatalogoPlantillas, cats: Categorias | None = None) -> dict:
    v = estado_ventana(c, ahora)
    state = est.construir_estado(c, ahora, v)
    etapa = ETAPA_POR_PUNTO[motivo]
    cats_etapa = cats.de_etapa(etapa) if cats else []
    preguntas = {**preguntas_para_jev(), **preguntas_categoria(cats_etapa)}  # una sola llamada
    respuesta_jev = jev.preguntar(state, preguntas)

    msgs = c.mensajes_hasta(ahora)
    primer_ventas = next((m.ts for m in msgs if m.autor == "ventas"), None)
    hubo_dialogo = primer_ventas is not None and any(m.autor == "cliente" and m.ts > primer_ventas for m in msgs)
    clasif = clasificar(respuesta_jev["respuestas"], hubo_dialogo).a_dict()
    if primer_ventas is None:  # si Ventas todavía no escribió, que haya una pregunta pendiente es obvio
        clasif["alertas"] = [a for a in clasif["alertas"] if "pregunta" not in a]

    if cats is not None:
        clasif["categoria"] = categoria_desde_jev(respuesta_jev["respuestas"], cats_etapa, etapa, clasif["segmento"])
        accion = decidir_por_categoria(clasif, v.a_dict(), state["conversacion"], cats, redactor, catalogo, ahora)
    else:
        accion = _decidir_por_segmento(clasif, v, state, redactor, catalogo, ahora)

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
