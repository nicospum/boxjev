"""Construye el `state` que recibe Jev en un momento dado.

Principios (guía de TypeSafe):
- Solo lo que Ventas veía en ese momento: nunca mensajes posteriores ni el
  resultado comercial (evita "mirar el futuro" en la prueba retrospectiva).
- Quién dijo cada cosa, con nombres legibles, conversación completa.
- Los hechos que el código ya sabe (horas sin respuesta, plantillas enviadas)
  se escriben como hechos; Jev no hace cuentas de fechas.
- Solo campos relevantes: nada de IDs, teléfonos ni campos vacíos.
"""
from __future__ import annotations

from datetime import datetime

from .modelo import Consulta
from .ventana import EstadoVentana

ETIQUETA_AUTOR = {
    "cliente": "Prospecto",
    "ventas": "Ventas Don Box",
    "sistema": "Respuesta automática",
}

# Propiedades de HubSpot que aportan a la clasificación. El resto se descarta.
PROPIEDADES_UTILES = {
    "zona_formulario": "Zona elegida en el formulario",
    "sede_formulario": "Sede elegida en el formulario",
    "tamano_formulario": "Tamaño elegido en el formulario",
    "motivo_formulario": "Motivo elegido en el formulario",
    "tipo_cliente_formulario": "Tipo de cliente elegido en el formulario",
    "mensaje_formulario": "Mensaje escrito en el formulario",
}


def _horas(delta_s: float) -> str:
    h = delta_s / 3600
    if h < 1:
        return f"{int(delta_s // 60)} min"
    if h < 48:
        return f"{h:.0f} h"
    return f"{h / 24:.0f} días"


def construir_estado(consulta: Consulta, ahora: datetime, ventana: EstadoVentana) -> dict:
    msgs = consulta.mensajes_hasta(ahora)
    if not msgs:
        raise ValueError(f"{consulta.id_consulta}: no hay mensajes antes de {ahora}")
    inicio = msgs[0].ts

    conversacion = []
    for m in msgs:
        item = {
            "de": ETIQUETA_AUTOR[m.autor],
            "cuando": f"+{_horas((m.ts - inicio).total_seconds())} desde el primer mensaje",
        }
        if m.tipo == "plantilla":
            item["texto"] = f"[Plantilla de WhatsApp] {m.texto}"
        elif m.tipo in ("audio", "imagen", "documento") and not m.texto:
            item["texto"] = f"[{m.tipo} sin transcripción]"
        else:
            item["texto"] = m.texto
        conversacion.append(item)

    hechos = []
    if ventana.ultimo_autor == "ventas" and ventana.ultimo_entrante:
        sin_resp = (ahora - ventana.ultimo_entrante).total_seconds()
        hechos.append(
            f"El prospecto no escribió nada en las últimas {_horas(sin_resp)}; "
            f"Ventas le envió {ventana.mensajes_ventas_sin_respuesta} mensaje(s) que siguen sin respuesta."
        )
    if ventana.plantillas_sin_respuesta:
        hechos.append(f"Se enviaron {ventana.plantillas_sin_respuesta} plantilla(s) sin respuesta del prospecto.")
    if not any(m.autor == "ventas" for m in msgs):
        hechos.append("Ventas todavía no respondió esta consulta.")

    datos_crm = {
        etiqueta: consulta.propiedades[k]
        for k, etiqueta in PROPIEDADES_UTILES.items()
        if consulta.propiedades.get(k) not in (None, "", [])
    }

    estado: dict = {
        "empresa": "Don Box alquila bauleras privadas (self storage) en CABA, Tigre, Quilmes/Bernal y Córdoba.",
        "canal": "WhatsApp" if consulta.canal == "whatsapp" else consulta.canal,
        "conversacion": conversacion,
    }
    if datos_crm:
        estado["datos_del_formulario"] = datos_crm
    if consulta.origen.get("campania"):
        estado["campania_de_origen"] = consulta.origen["campania"]
    if hechos:
        estado["hechos"] = hechos
    return estado


# Campos del state, para mostrar en cada recomendación qué datos se usaron.
def campos_usados(estado: dict) -> list[str]:
    usados = [k for k in estado if k != "empresa"]
    if "datos_del_formulario" in estado:
        usados += [f"datos_del_formulario.{k}" for k in estado["datos_del_formulario"]]
    return usados
