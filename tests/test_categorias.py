from jeventas.categorias import leer
from jeventas.pipeline import categoria_desde_jev

CATS = [
    {"id": "alta_intencion", "nombre": "Alta intención", "descripcion": "d", "accion": "responder", "color": "#000000"},
    {"id": "exploratoria", "nombre": "Exploratoria", "descripcion": "d", "accion": "responder", "color": "#000000"},
]


def _r(choice, conf, encaja=0.9):
    return {"categoria": {"type": "choice", "choice": choice, "confidence": conf,
                          "probabilities": {"alta_intencion": conf, "exploratoria": 1 - conf}},
            "categoria_encaja": {"type": "noul", "noul": encaja}}


def test_ninguna_encaja_queda_sin_categoria():
    assert leer(_r("alta_intencion", 0.9, encaja=0.1), CATS)["id"] == "sin_categoria"


def test_confianza_baja_queda_para_revisar():
    x = leer(_r("alta_intencion", 0.5), CATS)
    assert x["id"] == "alta_intencion" and x["revisar"]


def test_senales_puntuales_mandan_y_marcan_revision():
    x = categoria_desde_jev(_r("alta_intencion", 0.9), CATS, "primer_contacto", segmento="exploratoria")
    assert x["id"] == "exploratoria" and x["revisar"] and x["elegida_por_jev"] == "alta_intencion"


def test_si_coinciden_no_hay_revision():
    x = categoria_desde_jev(_r("alta_intencion", 0.9), CATS, "primer_contacto", segmento="alta_intencion")
    assert x["id"] == "alta_intencion" and not x["revisar"]


def test_segmento_sin_categoria_equivalente_no_interfiere():
    x = categoria_desde_jev(_r("alta_intencion", 0.9), CATS, "primer_contacto", segmento="revision_humana")
    assert x["id"] == "alta_intencion" and not x["revisar"]
