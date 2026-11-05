import json

import pytest

from jeventas import ajustes, asistente

CHATS = [
    {"texto": "Hola! Me mudo la semana que viene y necesito baulera en Palermo para muebles de un 2 ambientes. Soy Juan, 11 5555 4444", "nombre": "Juan"},
    {"texto": "Cliente: Hola, cuánto sale?\nVentas: Hola, ¿para qué zona?", "ultimo_hace_horas": 30},
    {"texto": "Cliente: tengo un emprendimiento y necesito guardar mercadería\nVentas: ¡Hola! ¿En qué zona?\nCliente: Gracias, ya lo resolví", "ultimo_hace_horas": 2},
]


def _lote(acc):
    return acc.agregar_lote(CHATS, "prueba", usar_jev_real=False)["lote"]


def test_agregar_lote_pegado_simulado_y_categorias(panel_tmp):
    _, acc = panel_tmp
    lote = _lote(acc)
    d = acc.cargar_lote(lote)
    assert len(d["consultas"]) == 3
    assert "Juan" not in json.dumps(d["consultas"], ensure_ascii=False)
    cats = {r["clasificacion"]["categoria"]["id"] for r in d["recomendaciones"]}
    assert cats <= {c["id"] for c in acc.ver_categorias()["categorias"]} | {"sin_categoria"}
    primeros = [r for r in d["recomendaciones"] if r["punto"] == "primer_contacto"]
    assert any(r["clasificacion"]["categoria"]["id"] == "alta_intencion" for r in primeros)


def test_jev_real_pide_aprobacion_y_clave(panel_tmp):
    _, acc = panel_tmp
    with pytest.raises(acc.ErrorPanel, match="Ajustes"):
        acc.agregar_lote(CHATS, "x", usar_jev_real=True)
    ajustes.actualizar({"envio_externo_aprobado": True})
    with pytest.raises(acc.ErrorPanel, match="TypeSafe"):
        acc.agregar_lote(CHATS, "x", usar_jev_real=True)


def test_crear_editar_mover_y_eliminar_con_sugerencias(panel_tmp):
    _, acc = panel_tmp
    lote = _lote(acc)
    nueva = acc.crear_categoria({"etapa": "primer_contacto", "nombre": "Mudanza urgente",
                                 "descripcion": "El prospecto se muda en los próximos días y necesita guardar muebles ya.", "accion": "responder"})
    assert nueva["id"] == "mudanza_urgente"
    acc.editar_categoria("mudanza_urgente", {"color": "#123456"})
    with pytest.raises(acc.ErrorPanel):
        acc.crear_categoria({"etapa": "primer_contacto", "nombre": "X", "descripcion": "corta", "accion": "responder"})

    d = acc.cargar_lote(lote)
    r = next(x for x in d["recomendaciones"] if x["punto"] == "primer_contacto")
    acc.mover(lote, r["clave"], "mudanza_urgente")
    assert acc.miembros(lote, "mudanza_urgente")["total"] == 1
    with pytest.raises(acc.ErrorPanel):  # categoría de otra etapa
        acc.mover(lote, r["clave"], "desistio")

    res = acc.eliminar_categoria("mudanza_urgente")
    assert res["contactos_a_reasignar"] == 1
    pend = acc.cargar_lote(lote)["reasignaciones"]
    assert pend[0]["estado"] == "pendiente" and pend[0]["sugerida"] != "mudanza_urgente"
    acc.resolver_reasignacion(lote, r["clave"], aceptar=False, categoria="exploratoria")
    assert acc.miembros(lote, "exploratoria")["total"] >= 1
    assert acc.cargar_lote(lote)["reasignaciones"][0]["estado"] == "rechazada"


def test_aceptar_sugerencia(panel_tmp):
    _, acc = panel_tmp
    lote = _lote(acc)
    r = next(x for x in acc.cargar_lote(lote)["recomendaciones"] if x["punto"] == "primer_contacto")
    acc.mover(lote, r["clave"], "lista_para_cotizar")
    acc.eliminar_categoria("lista_para_cotizar")
    p = acc.cargar_lote(lote)["reasignaciones"][0]
    acc.resolver_reasignacion(lote, r["clave"], aceptar=True)
    assert acc.cargar_lote(lote)["asignaciones"][r["clave"]]["categoria"] == p["sugerida"]


def test_no_se_puede_dejar_una_etapa_sin_categorias(panel_tmp):
    _, acc = panel_tmp
    ids = [c["id"] for c in acc.ver_categorias()["categorias"] if c["etapa"] == "post_24h"]
    for cid in ids[:-1]:
        acc.eliminar_categoria(cid)
    with pytest.raises(acc.ErrorPanel):
        acc.eliminar_categoria(ids[-1])


def test_reclasificar_conserva_cambios_manuales(panel_tmp):
    _, acc = panel_tmp
    lote = _lote(acc)
    r = next(x for x in acc.cargar_lote(lote)["recomendaciones"] if x["punto"] == "primer_contacto")
    acc.mover(lote, r["clave"], "informacion_insuficiente")
    out = acc.reclasificar_lote(lote)
    assert out["momentos"] == len(acc.cargar_lote(lote)["recomendaciones"])
    assert acc.cargar_lote(lote)["asignaciones"][r["clave"]]["categoria"] == "informacion_insuficiente"


def test_ajustes_no_devuelven_claves(panel_tmp):
    ajustes.actualizar({"claves": {"openai": "sk-secreta"}, "proveedor_chat": "openai"})
    pub = ajustes.publico()
    assert "sk-secreta" not in json.dumps(pub)
    assert pub["proveedores"]["openai"]["configurada"] and pub["proveedor_chat"] == "openai"


class _IAFalsa:
    """Simula un modelo que pide herramientas: crea una categoría y propone eliminar otra."""
    modelo = "falso"

    def conversar(self, sistema, historial, herramientas, ejecutar):
        assert {h["name"] for h in herramientas} >= {"crear_categoria", "proponer_eliminar_categoria", "mover_contacto"}
        a = ejecutar("crear_categoria", {"etapa": "post_24h", "nombre": "Pide visita",
                                         "descripcion": "El prospecto quiere ir a ver la sucursal antes de decidir.", "accion": "persona"})
        b = ejecutar("proponer_eliminar_categoria", {"id": "objecion_precio"})
        c = ejecutar("mostrar", {"vista": "categorias"})
        return {"texto": "Listo", "pasos": [a, b, c]}


def test_asistente_ejecuta_herramientas_y_pide_confirmar_eliminar(panel_tmp, monkeypatch):
    _, acc = panel_tmp
    monkeypatch.setattr(asistente.proveedores, "crear", lambda p: _IAFalsa())
    r = asistente.conversar("openai", [{"rol": "user", "texto": "creá Pide visita y sacá Le parece caro"}], None, acc)
    ids = [c["id"] for c in acc.ver_categorias()["categorias"]]
    assert "pide_visita" in ids and "objecion_precio" in ids  # no se eliminó sin confirmar
    assert r["confirmaciones"][0]["id"] == "objecion_precio" and r["ui"] == [{"vista": "categorias"}] and r["cambios"]


def test_proveedor_sin_aprobacion(panel_tmp):
    from jeventas import proveedores
    ajustes.actualizar({"claves": {"deepseek": "k"}})
    with pytest.raises(proveedores.ErrorProveedor, match="aprobó"):
        proveedores.crear("deepseek")


def test_compatible_arma_pedido_con_herramientas(panel_tmp, monkeypatch):
    from jeventas import proveedores
    pedidos = []
    respuestas = iter([
        {"choices": [{"message": {"content": None, "tool_calls": [{"id": "t1", "type": "function",
                                                                       "function": {"name": "listar_lotes", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"content": "Hay 0 lotes."}}]},
    ])
    ia = proveedores.Compatible("gemini", "k", "gemini-2.5-flash")
    monkeypatch.setattr(ia, "_post", lambda cuerpo: (pedidos.append(json.loads(json.dumps(cuerpo))), next(respuestas))[1])
    r = ia.conversar("sis", [{"rol": "user", "texto": "hola"}], asistente.HERRAMIENTAS, lambda n, a: {"lotes": []})
    assert r["texto"] == "Hay 0 lotes." and r["pasos"][0]["herramienta"] == "listar_lotes"
    assert "additionalProperties" not in json.dumps(pedidos[0]["tools"])
    assert pedidos[1]["messages"][-1] == {"role": "tool", "tool_call_id": "t1", "content": json.dumps({"lotes": []})}
