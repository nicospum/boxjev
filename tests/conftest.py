import shutil
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def panel_tmp(tmp_path, monkeypatch):
    """Panel aislado: copia de config/, out/ vacío y ajustes propios."""
    shutil.copytree(RAIZ / "config", tmp_path / "config", ignore=shutil.ignore_patterns("*.local.json"))
    import jeventas.ajustes as aj
    import jeventas.corrida as corrida
    import panel.acciones as acc
    import panel.servidor as srv

    monkeypatch.setattr(corrida, "RAIZ", tmp_path)
    monkeypatch.setattr(acc, "RAIZ", tmp_path)
    monkeypatch.setattr(acc, "OUT", tmp_path / "out")
    monkeypatch.setattr(srv, "RAIZ", tmp_path)
    monkeypatch.setattr(srv, "OUT", tmp_path / "out")
    monkeypatch.setattr(aj, "RUTA", tmp_path / "config" / "ajustes.local.json")
    for v in aj.CLAVES.values():
        monkeypatch.delenv(v, raising=False)
    (tmp_path / "out").mkdir()
    return srv, acc
