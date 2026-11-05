"""Formato canónico de una consulta (conversación + datos comerciales).

Todo lo que entra al sistema (exportes de Atom, HubSpot, WhatsApp, CSV) se
convierte primero a este formato con `jeventas.importar`. Ver
`data/FORMATO_DE_ENTRADA.md`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

AUTORES = ("cliente", "ventas", "sistema")
RESULTADOS = ("alquilo", "no_alquilo", "desconocido")


@dataclass
class Mensaje:
    ts: datetime
    autor: str  # cliente | ventas | sistema (respuestas automáticas, bots)
    texto: str
    tipo: str = "texto"  # texto | plantilla | audio | imagen | documento
    plantilla_id: str | None = None

    def __post_init__(self) -> None:
        if self.autor not in AUTORES:
            raise ValueError(f"autor inválido: {self.autor!r} (usar {AUTORES})")

    def a_dict(self) -> dict:
        d = {"ts": self.ts.isoformat(), "autor": self.autor, "texto": self.texto, "tipo": self.tipo}
        if self.plantilla_id:
            d["plantilla_id"] = self.plantilla_id
        return d


@dataclass
class Consulta:
    id_consulta: str
    mensajes: list[Mensaje]
    canal: str = "whatsapp"
    origen: dict = field(default_factory=dict)  # fuente, campaña, anuncio
    propiedades: dict = field(default_factory=dict)  # propiedades HubSpot conocidas al primer contacto
    resultado: dict = field(default_factory=lambda: {"estado": "desconocido"})
    etiqueta_ventas: dict | None = None  # clasificación hecha por Ventas (para evaluar)
    sintetica: bool = False

    def __post_init__(self) -> None:
        self.mensajes.sort(key=lambda m: m.ts)

    def mensajes_hasta(self, ts: datetime) -> list[Mensaje]:
        return [m for m in self.mensajes if m.ts <= ts]

    def a_dict(self) -> dict:
        return {
            "id_consulta": self.id_consulta,
            "canal": self.canal,
            "origen": self.origen,
            "propiedades": self.propiedades,
            "mensajes": [m.a_dict() for m in self.mensajes],
            "resultado": self.resultado,
            "etiqueta_ventas": self.etiqueta_ventas,
            "sintetica": self.sintetica,
        }

    @classmethod
    def desde_dict(cls, d: dict) -> "Consulta":
        mensajes = [
            Mensaje(
                ts=datetime.fromisoformat(m["ts"]),
                autor=m["autor"],
                texto=m.get("texto", ""),
                tipo=m.get("tipo", "texto"),
                plantilla_id=m.get("plantilla_id"),
            )
            for m in d["mensajes"]
        ]
        return cls(
            id_consulta=str(d["id_consulta"]),
            mensajes=mensajes,
            canal=d.get("canal", "whatsapp"),
            origen=d.get("origen") or {},
            propiedades=d.get("propiedades") or {},
            resultado=d.get("resultado") or {"estado": "desconocido"},
            etiqueta_ventas=d.get("etiqueta_ventas"),
            sintetica=bool(d.get("sintetica", False)),
        )


def leer_jsonl(ruta: str | Path) -> Iterator[Consulta]:
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield Consulta.desde_dict(json.loads(linea))
            except (KeyError, ValueError) as e:
                raise ValueError(f"{ruta}:{n}: consulta inválida: {e}") from e


def escribir_jsonl(ruta: str | Path, consultas: Iterable[Consulta]) -> int:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(ruta, "w", encoding="utf-8") as f:
        for c in consultas:
            f.write(json.dumps(c.a_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n
