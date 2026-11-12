"""Prueba retrospectiva: corre el circuito sobre conversaciones históricas.

No envía mensajes, no toca HubSpot ni Atom. Por defecto no sale nada a
internet (Jev simulado + redactor offline). Los resultados se ven en el panel
(`python scripts/abrir_panel.py`) o en los archivos de la carpeta de salida.

Ejemplos:
  # todo local, para probar el circuito
  python scripts/correr_piloto.py --entrada data/sinteticas/consultas_500.jsonl --simular-plantillas

  # Jev real sobre 20 consultas (requiere aprobación de Don Box y TYPESAFE_API_KEY)
  python scripts/correr_piloto.py --entrada data/reales/consultas.jsonl --jev api --envio-externo-aprobado --limite 20
"""
from __future__ import annotations

import argparse
import itertools
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from jeventas.corrida import correr, herramientas  # noqa: E402
from jeventas.modelo import leer_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True, help="JSONL en formato canónico")
    ap.add_argument("--salida", default=None, help="carpeta de salida (por defecto out/<fecha>)")
    ap.add_argument("--jev", choices=["simulado", "api"], default="simulado")
    ap.add_argument("--redactor", choices=["offline", "claude"], default="offline")
    ap.add_argument("--envio-externo-aprobado", action="store_true",
                    help="confirma que Don Box aprobó enviar estas conversaciones (anonimizadas) a TypeSafe/Anthropic")
    ap.add_argument("--simular-plantillas", action="store_true",
                    help="trata las plantillas de ejemplo como aprobadas (modo laboratorio, queda marcado)")
    ap.add_argument("--limite", type=int, default=None)
    a = ap.parse_args()

    salida = Path(a.salida or RAIZ / "out" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    jev, redactor, catalogo = herramientas(a.jev, a.redactor, a.envio_externo_aprobado, a.simular_plantillas)
    consultas = itertools.islice(leer_jsonl(a.entrada), a.limite)
    res = correr(consultas, salida, jev, redactor, catalogo, entrada=a.entrada)
    m = res["metricas"]
    print(f"{m['consultas']} consultas, {res['meta']['recomendaciones']} recomendaciones, {len(res['errores'])} errores -> {salida}")
    print(f"Acuerdo con Ventas: {m['acuerdo']['pct']} · acciones: {m['acciones']}")


if __name__ == "__main__":
    main()
