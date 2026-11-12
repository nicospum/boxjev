"""Exporta lotes ya analizados a panel/static/datos/ para la demo estática (Netlify).

Solo exporta lotes 100 % sintéticos: las conversaciones reales nunca van a un
sitio público.

  python scripts/exportar_demo.py jev_real_20 demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from panel.servidor import cargar_corrida  # noqa: E402

DESTINO = RAIZ / "panel" / "static" / "datos"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corridas", nargs="+", help="nombres de carpetas en out/, en el orden en que se muestran")
    a = ap.parse_args()

    DESTINO.mkdir(parents=True, exist_ok=True)
    indice = []
    for nombre in a.corridas:
        d = cargar_corrida(nombre)
        meta = d["meta"]
        if not d["consultas"] or meta.get("sinteticas") != len(d["consultas"]):
            sys.exit(f"'{nombre}' tiene conversaciones que no son sintéticas: no se exporta a la demo pública.")
        for r in d["recomendaciones"]:
            r.pop("clave", None)
        salida = {"nombre": nombre, "meta": meta, "consultas": d["consultas"], "recomendaciones": d["recomendaciones"]}
        (DESTINO / f"{nombre}.json").write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        indice.append({"nombre": nombre, "meta": meta, "revisadas": 0})
        print(f"{nombre}: {len(d['consultas'])} consultas, {len(d['recomendaciones'])} sugerencias")
    (DESTINO / "corridas.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {DESTINO}")


if __name__ == "__main__":
    main()
