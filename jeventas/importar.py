"""Conversión de exportes al formato canónico + anonimización.

Todavía no sabemos en qué formato exportan Atom y HubSpot. Se soportan los
tres formatos más probables; agregar un adaptador nuevo cuando llegue el
exporte real (ver data/FORMATO_DE_ENTRADA.md):

1. CSV de mensajes (una fila por mensaje) + CSV opcional de consultas
   (una fila por consulta, con propiedades HubSpot y resultado).
2. Exporte de chat de WhatsApp (.txt, formato Android o iPhone).
3. JSONL canónico (ya en el formato de `modelo.Consulta`).
"""
from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .jev import FECHA
from .modelo import Consulta, Mensaje

# ---------------------------------------------------------------- anonimizar
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_TEL = re.compile(r"(?<!\d)(?:\+?54\s?9?\s?)?(?:\d[\s-]?){8,12}(?!\d)")
_DOC = re.compile(r"\b\d{2}[.-]?\d{3}[.-]?\d{3}\b|\b\d{2}-\d{8}-\d\b")


def anonimizar_texto(texto: str, nombres: list[str] = ()) -> str:
    fechas: list[str] = []

    def guardar(m: re.Match) -> str:  # las fechas no se anonimizan
        fechas.append(m.group(0))
        return f"\x00{len(fechas) - 1}\x00"

    texto = FECHA.sub(guardar, texto)
    texto = _EMAIL.sub("[email]", texto)
    texto = _DOC.sub("[documento]", texto)
    texto = _TEL.sub("[teléfono]", texto)
    texto = re.sub(r"\x00(\d+)\x00", lambda m: fechas[int(m.group(1))], texto)
    for n in sorted({n for n in nombres if n and len(n) > 2}, key=len, reverse=True):
        texto = re.sub(rf"\b{re.escape(n)}\b", "[nombre]", texto, flags=re.I)
    return texto


def codigo_anonimo(valor: str, sal: str) -> str:
    return "C-" + hashlib.sha256((sal + valor).encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- CSV
COLUMNAS_MENSAJES = {
    "id_consulta": ["id_consulta", "conversation_id", "chat_id", "id", "ticket_id"],
    "ts": ["fecha_hora", "timestamp", "fecha", "date", "created_at", "sent_at"],
    "autor": ["autor", "direction", "sender_type", "from", "remitente"],
    "texto": ["texto", "mensaje", "message", "body", "text", "contenido"],
    "tipo": ["tipo", "type", "message_type"],
    "plantilla_id": ["plantilla_id", "template", "template_name", "plantilla"],
}
_AUTOR = {
    "cliente": "cliente", "contacto": "cliente", "inbound": "cliente", "incoming": "cliente", "customer": "cliente", "contact": "cliente", "entrante": "cliente",
    "ventas": "ventas", "agente": "ventas", "agent": "ventas", "outbound": "ventas", "outgoing": "ventas", "user": "ventas", "saliente": "ventas",
    "bot": "sistema", "sistema": "sistema", "system": "sistema", "automation": "sistema",
}


def _col(cabecera: list[str], logico: str) -> str | None:
    bajas = {c.lower().strip(): c for c in cabecera}
    return next((bajas[a] for a in COLUMNAS_MENSAJES[logico] if a in bajas), None)


def _fecha(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def desde_csv(ruta_mensajes: str | Path, ruta_consultas: str | Path | None = None, sal: str = "donbox", anonimizar: bool = True) -> list[Consulta]:
    with open(ruta_mensajes, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        cab = lector.fieldnames or []
        cols = {k: _col(cab, k) for k in COLUMNAS_MENSAJES}
        faltan = [k for k in ("id_consulta", "ts", "autor", "texto") if not cols[k]]
        if faltan:
            raise ValueError(f"Faltan columnas en {ruta_mensajes}: {faltan}. Cabecera: {cab}")
        por_id: dict[str, list[Mensaje]] = defaultdict(list)
        for fila in lector:
            autor = _AUTOR.get(fila[cols["autor"]].strip().lower())
            if autor is None:
                raise ValueError(f"Autor desconocido: {fila[cols['autor']]!r}. Agregarlo a _AUTOR.")
            texto = fila[cols["texto"]] or ""
            por_id[fila[cols["id_consulta"]]].append(Mensaje(
                ts=_fecha(fila[cols["ts"]]),
                autor=autor,
                texto=anonimizar_texto(texto) if anonimizar else texto,
                tipo=(fila.get(cols["tipo"]) if cols["tipo"] else None) or ("plantilla" if cols["plantilla_id"] and fila.get(cols["plantilla_id"]) else "texto"),
                plantilla_id=(fila.get(cols["plantilla_id"]) or None) if cols["plantilla_id"] else None,
            ))

    extras: dict[str, dict] = {}
    if ruta_consultas:
        with open(ruta_consultas, encoding="utf-8-sig", newline="") as f:
            for fila in csv.DictReader(f):
                extras[fila["id_consulta"]] = fila

    consultas = []
    for idc, msgs in por_id.items():
        ex = extras.get(idc, {})
        resultado = (ex.pop("resultado", "") or "desconocido").strip().lower().replace(" ", "_")
        if resultado not in ("alquilo", "no_alquilo", "desconocido"):
            resultado = "desconocido"
        origen = {k: ex.pop(k) for k in ("fuente", "campania") if ex.get(k)}
        props = {k: v for k, v in ex.items() if k != "id_consulta" and v not in ("", None)}
        if anonimizar:
            for sensible in ("nombre", "telefono", "email", "dni", "cuit", "firstname", "lastname", "phone"):
                props.pop(sensible, None)
        consultas.append(Consulta(
            id_consulta=codigo_anonimo(idc, sal) if anonimizar else idc,
            mensajes=msgs, origen=origen, propiedades=props, resultado={"estado": resultado},
        ))
    return consultas


# ---------------------------------------------------------------- WhatsApp .txt
_WA_ANDROID = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),? (\d{1,2}:\d{2})(?:\s?[ap]\.?\s?m\.?)? - ([^:]+): (.*)$", re.I)
_WA_IOS = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?)\] ([^:]+): (.*)$")


def desde_whatsapp_txt(ruta: str | Path, nombres_ventas: list[str], sal: str = "donbox", anonimizar: bool = True) -> Consulta:
    """nombres_ventas: cómo aparece el equipo de Don Box en el chat (p. ej. 'Don Box Ventas')."""
    mensajes: list[Mensaje] = []
    nombres_cliente: set[str] = set()
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        linea = linea.replace("‎", "").replace(" ", " ")
        m = _WA_IOS.match(linea) or _WA_ANDROID.match(linea)
        if not m:
            if mensajes and linea.strip():  # continuación del mensaje anterior
                mensajes[-1].texto += "\n" + linea
            continue
        fecha, hora, quien, texto = m.groups()
        d, mes, a = fecha.split("/")
        a = int(a) + (2000 if len(a) == 2 else 0)
        hh, mm = hora.split(":")[:2]
        ts = datetime(a, int(mes), int(d), int(hh), int(mm))
        autor = "ventas" if quien.strip() in nombres_ventas else "cliente"
        if autor == "cliente":
            nombres_cliente.add(quien.strip())
        tipo = "texto"
        if "<Multimedia omitido>" in texto or "omitted" in texto or "omitido" in texto:
            tipo, texto = "imagen", ""
        mensajes.append(Mensaje(ts=ts, autor=autor, texto=texto, tipo=tipo))
    if not mensajes:
        raise ValueError(f"No se reconocieron mensajes en {ruta}")
    if anonimizar:
        partes = [p for n in nombres_cliente for p in n.split()]
        for msg in mensajes:
            msg.texto = anonimizar_texto(msg.texto, partes)
    ident = Path(ruta).stem
    return Consulta(id_consulta=codigo_anonimo(ident, sal) if anonimizar else ident, mensajes=mensajes)
