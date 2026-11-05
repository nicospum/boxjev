"""Reglas de la ventana de atención de WhatsApp (24 h). Todo en código, nada en Jev.

Reglas:
1. La ventana se cuenta desde el ÚLTIMO mensaje ENTRANTE del cliente.
2. Solo un mensaje del cliente la renueva. Los mensajes de Ventas, las plantillas
   enviadas y las respuestas automáticas ('sistema') NO la renuevan.
3. Con la ventana abierta se puede sugerir un mensaje libre (borrador).
4. Con la ventana cerrada solo se puede sugerir una plantilla aprobada y vigente.
5. Si el cliente responde una plantilla, la ventana se abre otra vez (regla 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .modelo import Consulta, Mensaje

VENTANA = timedelta(hours=24)
# Margen para sugerir un último mensaje libre antes de que cierre la ventana.
# Propuesta a validar con Ventas (evita gastar una plantilla).
MARGEN_SEGUIMIENTO_LIBRE = timedelta(hours=4)


@dataclass
class EstadoVentana:
    evaluado_en: datetime
    ultimo_entrante: datetime | None
    cierra_en: datetime | None
    abierta: bool
    horas_restantes: float
    ultimo_autor: str | None  # quién habló último (cliente/ventas)
    plantillas_sin_respuesta: int  # plantillas enviadas desde el último entrante
    mensajes_ventas_sin_respuesta: int

    def a_dict(self) -> dict:
        return {
            "evaluado_en": self.evaluado_en.isoformat(),
            "ultimo_entrante": self.ultimo_entrante.isoformat() if self.ultimo_entrante else None,
            "cierra_en": self.cierra_en.isoformat() if self.cierra_en else None,
            "abierta": self.abierta,
            "horas_restantes": round(self.horas_restantes, 2),
            "ultimo_autor": self.ultimo_autor,
            "plantillas_sin_respuesta": self.plantillas_sin_respuesta,
            "mensajes_ventas_sin_respuesta": self.mensajes_ventas_sin_respuesta,
        }


def ultimo_entrante(mensajes: list[Mensaje], hasta: datetime) -> datetime | None:
    ts = [m.ts for m in mensajes if m.autor == "cliente" and m.ts <= hasta]
    return max(ts) if ts else None


def estado_ventana(consulta: Consulta, ahora: datetime) -> EstadoVentana:
    msgs = consulta.mensajes_hasta(ahora)
    ult = ultimo_entrante(msgs, ahora)
    cierra = ult + VENTANA if ult else None
    abierta = bool(cierra and ahora < cierra)
    restantes = (cierra - ahora).total_seconds() / 3600 if abierta else 0.0
    humanos = [m for m in msgs if m.autor in ("cliente", "ventas")]
    posteriores = [m for m in msgs if m.autor == "ventas" and (ult is None or m.ts > ult)]
    return EstadoVentana(
        evaluado_en=ahora,
        ultimo_entrante=ult,
        cierra_en=cierra,
        abierta=abierta,
        horas_restantes=restantes,
        ultimo_autor=humanos[-1].autor if humanos else None,
        plantillas_sin_respuesta=sum(1 for m in posteriores if m.tipo == "plantilla"),
        mensajes_ventas_sin_respuesta=len(posteriores),
    )


def tipo_de_mensaje_permitido(v: EstadoVentana) -> str:
    """'libre' dentro de la ventana; 'plantilla' fuera de ella."""
    return "libre" if v.abierta else "plantilla"
