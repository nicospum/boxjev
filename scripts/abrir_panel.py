"""Abre el panel de JeVentas.

  python scripts/abrir_panel.py                          # solo en esta computadora
  python scripts/abrir_panel.py --usuario Alberto --clave XXXX   # activa el login (queda guardado cifrado)
  python scripts/abrir_panel.py --publico                # además, link público https con cloudflared

--publico exige login. El link dura mientras esta ventana esté abierta:
al cerrarla (Ctrl+C) el link deja de funcionar. Datos y claves quedan en esta PC.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.servidor import ACCESO, servir  # noqa: E402


def tunel(puerto: int) -> subprocess.Popen | None:
    exe = shutil.which("cloudflared")
    if not exe:
        print("No encontré cloudflared. Instalalo con:  winget install --id Cloudflare.cloudflared")
        return None
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{puerto}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

    def leer():
        for linea in proc.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linea)
            if m:
                print(f"\n  Link público: {m.group(0)}\n  (pide usuario y contraseña; deja de funcionar al cerrar esta ventana)\n", flush=True)

    threading.Thread(target=leer, daemon=True).start()
    return proc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--usuario")
    ap.add_argument("--clave", help="activa el login y lo guarda cifrado en config/acceso.local.json")
    ap.add_argument("--publico", action="store_true", help="crea un link público con cloudflared (requiere login)")
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()

    s = servir(a.puerto, a.usuario, a.clave, guardar=bool(a.clave))
    url = f"http://127.0.0.1:{a.puerto}"
    print(f"Panel de JeVentas en {url}  (Ctrl+C para cerrar)")
    print("Login: " + (f"activado (usuario {ACCESO.usuario})" if ACCESO.activo else "desactivado (solo esta computadora)"))
    proc = None
    if a.publico:
        if not ACCESO.activo:
            sys.exit("Para publicar el panel hace falta login: agregá --usuario y --clave.")
        proc = tunel(a.puerto)
    if not a.sin_navegador:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel cerrado.")
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    main()
