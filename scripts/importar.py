"""Convierte exportes (CSV de mensajes o chats de WhatsApp .txt) al formato canónico, anonimizados.

Ejemplos:
  python scripts/importar.py csv --mensajes export/mensajes.csv --consultas export/consultas.csv --salida data/reales/consultas.jsonl
  python scripts/importar.py whatsapp --carpeta export/chats_txt --ventas "Don Box Ventas" --salida data/reales/whatsapp.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jeventas.importar import desde_csv, desde_whatsapp_txt  # noqa: E402
from jeventas.modelo import escribir_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="formato", required=True)
    c = sub.add_parser("csv")
    c.add_argument("--mensajes", required=True)
    c.add_argument("--consultas")
    w = sub.add_parser("whatsapp")
    w.add_argument("--carpeta", required=True)
    w.add_argument("--ventas", nargs="+", required=True, help="nombre(s) con que aparece Don Box en los chats")
    for p in (c, w):
        p.add_argument("--salida", required=True)
        p.add_argument("--sal", default="donbox", help="sal para los códigos anónimos (guardar en lugar seguro)")
        p.add_argument("--sin-anonimizar", action="store_true", help="solo para uso local, nunca para enviar a terceros")
    a = ap.parse_args()

    anon = not a.sin_anonimizar
    if a.formato == "csv":
        consultas = desde_csv(a.mensajes, a.consultas, sal=a.sal, anonimizar=anon)
    else:
        consultas = [desde_whatsapp_txt(p, a.ventas, sal=a.sal, anonimizar=anon) for p in sorted(Path(a.carpeta).glob("*.txt"))]
    n = escribir_jsonl(a.salida, consultas)
    print(f"{n} consultas -> {a.salida}" + ("" if anon else "  (SIN anonimizar: no compartir)"))


if __name__ == "__main__":
    main()
