"""Tabla de decisión: de los juicios de Jev a un segmento y un próximo paso.

Jev juzga; este archivo decide. Las categorías son una PROPUESTA para validar
con Alberto y Ventas (ver docs/DISENO_PILOTO.md §3). Cambiarlas acá.

Lectura de un Noul: >= SI -> "si", <= NO -> "no", en el medio -> "duda".
"""
from __future__ import annotations

from dataclasses import dataclass, field

SI = 0.7
NO = 0.3
CONF_MIN_TIPO = 0.6  # si Jev duda qué tipo de mensaje es -> revisión humana
URGENCIA_ALTA = 1.75  # score 0..3, solo si la respuesta no trae la distribución por nivel

SEGMENTOS = {
    # prospectos
    "alta_intencion": "Dice dónde y lo necesita pronto (2-3 semanas o menos).",
    "lista_para_cotizar": "Dice dónde y qué guarda o por qué; sin urgencia clara.",
    "exploratoria": "Una sola señal (solo zona, solo precio o solo motivo).",
    "informacion_insuficiente": "Ninguna señal útil todavía: hay que pedir datos.",
    # después de conversar
    "listo_para_reservar": "Quiere reservar: prioridad, lo toma una persona.",
    "objecion_precio": "Dice que es caro: lo maneja una persona, sin prometer descuentos.",
    "pidio_tiempo": "Pidió que lo contacten más adelante.",
    "desistio": "Ya no lo necesita o eligió otra opción: no insistir.",
    # fuera de flujo
    "no_es_prospecto": "Cliente actual, empleo/proveedor o spam: derivar.",
    "revision_humana": "Las señales no alcanzan para decidir: revisa una persona.",
}

DATOS_A_PEDIR = {
    "menciona_ubicacion": "sucursal o zona",
    "describe_que_guarda": "qué quiere guardar o tamaño",
    "dice_cuando": "desde cuándo lo necesita",
    "dice_motivo": "para qué lo necesita",
}


def leer_noul(p: float) -> str:
    return "si" if p >= SI else "no" if p <= NO else "duda"


@dataclass
class Clasificacion:
    segmento: str
    necesidad: str | None
    sede: str | None
    es_empresa: str
    senales: dict
    datos_faltantes: list[str]
    explicacion: list[str]
    revision_humana: bool
    motivo_revision: str | None = None
    alertas: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "segmento": self.segmento,
            "descripcion_segmento": SEGMENTOS[self.segmento],
            "necesidad": self.necesidad,
            "sede": self.sede,
            "es_empresa": self.es_empresa,
            "senales": self.senales,
            "datos_faltantes": self.datos_faltantes,
            "explicacion": self.explicacion,
            "revision_humana": self.revision_humana,
            "motivo_revision": self.motivo_revision,
            "alertas": self.alertas,
        }


def clasificar(r: dict, hubo_dialogo: bool) -> Clasificacion:
    """r: respuestas de Jev por nombre de pregunta. hubo_dialogo: el prospecto
    respondió al menos una vez después de un mensaje de Ventas."""
    n = {k: v["noul"] for k, v in r.items() if v.get("type") == "noul"}
    lect = {k: leer_noul(p) for k, p in n.items()}
    senales = {k: {"prob": round(n[k], 3), "lectura": lect[k]} for k in n}
    urg = r["urgencia"]["score"]
    probs_urg = r["urgencia"].get("probabilities") or {}
    # El score promedio esconde respuestas con dos picos (p. ej. 67% "inmediato" + 18% "sin señal" = 2,3).
    # Se decide con la probabilidad de los niveles 2 y 3; si no viene la distribución, con el score.
    p_pronto = sum(float(probs_urg.get(k, 0)) for k in ("2", "3")) if probs_urg else (1.0 if urg >= URGENCIA_ALTA else 0.0)
    senales["urgencia"] = {"score": round(urg, 2), "p_pronto": round(p_pronto, 3), "probabilidades": probs_urg}
    exp: list[str] = []
    alertas: list[str] = []

    tipo = r["tipo_de_mensaje"]
    necesidad = r["necesidad"]["choice"] if lect["dice_motivo"] == "si" else None
    sede = r["sede"]["choice"] if lect["menciona_ubicacion"] == "si" else None
    empresa = lect["es_empresa"]
    faltan = [txt for k, txt in DATOS_A_PEDIR.items() if lect[k] != "si"]

    def C(seg: str, revision: bool = False, motivo: str | None = None) -> Clasificacion:
        return Clasificacion(seg, necesidad, sede, empresa, senales, faltan, exp, revision or seg == "revision_humana", motivo, alertas)

    if lect["pregunta_sin_responder"] == "si":
        alertas.append("El prospecto hizo una pregunta que todavía no se respondió.")
    if sede == "fuera_de_cobertura":
        alertas.append("La zona pedida está lejos de todas las sedes.")

    # 1) ¿Es un prospecto?
    if tipo["confidence"] < CONF_MIN_TIPO:
        exp.append(f"Jev no tiene claro el tipo de mensaje (confianza {tipo['confidence']:.2f}).")
        return C("revision_humana", motivo="tipo de mensaje dudoso")
    if tipo["choice"] != "consulta_nueva":
        exp.append(f"Jev lo identifica como '{tipo['choice']}', no como consulta de alquiler.")
        return C("no_es_prospecto", revision=True, motivo=f"derivar: {tipo['choice']}")

    # 2) Señales que solo cuentan si ya hubo diálogo con Ventas
    if hubo_dialogo:
        if lect["quiere_reservar"] == "si":
            exp.append("El prospecto dice que quiere reservar o pregunta cómo avanzar.")
            return C("listo_para_reservar", revision=True, motivo="cierre: lo toma una persona")
        if lect["desistio"] == "si":
            exp.append("El prospecto dice que ya no lo necesita o eligió otra opción.")
            return C("desistio")
        if lect["objecion_precio"] == "si":
            exp.append("El prospecto dice que el precio es alto.")
            return C("objecion_precio", revision=True, motivo="objeción de precio: no prometer descuentos")
        if lect["pidio_tiempo"] == "si":
            exp.append("El prospecto pidió tiempo o que lo contacten más adelante.")
            return C("pidio_tiempo")

    # 3) Nivel de intención por señales observables
    claves = ["menciona_ubicacion", "describe_que_guarda", "dice_cuando", "dice_motivo"]
    si = [k for k in claves if lect[k] == "si"]
    dudas = [k for k in claves if lect[k] == "duda"]
    for k in si:
        exp.append(f"Señal presente: {DATOS_A_PEDIR[k]} (p={n[k]:.2f}).")
    for k in dudas:
        exp.append(f"Señal dudosa: {DATOS_A_PEDIR[k]} (p={n[k]:.2f}).")
    if len(dudas) >= 2:
        return C("revision_humana", motivo="dos o más señales dudosas")

    ubic = "menciona_ubicacion" in si
    pronto = lect["dice_cuando"] == "si" and p_pronto >= SI
    if pronto:
        exp.append(f"Lo necesita en 2-3 semanas o menos (p={p_pronto:.2f}).")
    elif lect["dice_cuando"] == "si" and NO < p_pronto < SI:
        exp.append(f"No está claro si lo necesita pronto (p={p_pronto:.2f}).")

    if ubic and pronto:
        seg = "alta_intencion"
    elif ubic and ("describe_que_guarda" in si or "dice_motivo" in si or "dice_cuando" in si):
        seg = "lista_para_cotizar"
    elif len(si) >= 1 or lect["pide_precio"] == "si":
        seg = "exploratoria"
        if lect["pide_precio"] == "si" and not si:
            exp.append("Solo pregunta el precio, sin otros datos.")
    else:
        seg = "informacion_insuficiente"
        exp.append("No hay datos sobre zona, qué guarda, cuándo ni para qué.")

    if empresa == "si":
        exp.append("La baulera es para una empresa o negocio.")
    return C(seg)
