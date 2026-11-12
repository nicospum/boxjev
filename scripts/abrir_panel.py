"""Abre el panel de JeVentas en el navegador (http://127.0.0.1:8765).

  python scripts/abrir_panel.py
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.servidor import servir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    s = servir(a.puerto)
    url = f"http://127.0.0.1:{a.puerto}"
    print(f"Panel de JeVentas en {url}  (Ctrl+C para cerrar)")
    if not a.sin_navegador:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel cerrado.")


if __name__ == "__main__":
    main()
