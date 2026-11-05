import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jeventas.importar import anonimizar_texto, desde_csv, desde_whatsapp_txt
from jeventas.jev import DatosPersonalesError, JevAPI, JevError, JevSimulado, detectar_pii
from jeventas.modelo import Consulta, Mensaje
from jeventas.pipeline import evaluar, puntos_de_decision
from jeventas.plantillas import CatalogoPlantillas
from jeventas.redactor import RedactorOffline, cargar_info, verificar_borrador
from jeventas.reglas import clasificar
from jeventas.ventana import estado_ventana

RAIZ = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 5, 4, 10, 0)


def c(*msgs, **kw):
    return Consulta("T-1", [Mensaje(T0 + timedelta(hours=h), a, t, tipo=tp) for h, a, t, tp in msgs], **kw)


def M(h, autor, texto="hola", tipo="texto"):
    return (h, autor, texto, tipo)


# ------------------------------------------------------------------ ventana
def test_ventana_se_cuenta_desde_ultimo_entrante():
    k = c(M(0, "cliente"), M(1, "ventas"), M(5, "cliente"), M(6, "ventas"))
    assert estado_ventana(k, T0 + timedelta(hours=28)).abierta  # 5 + 24 = 29
    assert not estado_ventana(k, T0 + timedelta(hours=29, minutes=1)).abierta


def test_mensajes_de_ventas_y_plantillas_no_renuevan():
    k = c(M(0, "cliente"), M(23, "ventas"), M(30, "ventas", "plantilla", "plantilla"))
    v = estado_ventana(k, T0 + timedelta(hours=31))
    assert not v.abierta and v.plantillas_sin_respuesta == 1


def test_respuesta_a_plantilla_reabre_ventana():
    k = c(M(0, "cliente"), M(30, "ventas", "plantilla", "plantilla"), M(40, "cliente"))
    assert estado_ventana(k, T0 + timedelta(hours=41)).abierta


def test_mensaje_de_sistema_no_renueva():
    k = c(M(0, "cliente"), M(10, "sistema", "respuesta automática"))
    assert not estado_ventana(k, T0 + timedelta(hours=25)).abierta


# ------------------------------------------------------------------ reglas
def _resp(**nouls):
    base = {k: 0.05 for k in ["dice_motivo", "menciona_ubicacion", "describe_que_guarda", "dice_cuando", "pide_precio",
                              "es_empresa", "quiere_visitar", "desistio", "objecion_precio", "pidio_tiempo",
                              "quiere_reservar", "pregunta_sin_responder"]}
    base.update(nouls)
    r = {k: {"type": "noul", "noul": v} for k, v in base.items()}
    r["tipo_de_mensaje"] = {"type": "choice", "choice": "consulta_nueva", "confidence": 0.9}
    r["necesidad"] = {"type": "choice", "choice": "mudanza", "confidence": 0.8}
    r["sede"] = {"type": "choice", "choice": "palermo", "confidence": 0.8}
    r["urgencia"] = {"type": "score", "score": 0.2, "probabilities": {}}
    return r


def test_sin_senales_es_informacion_insuficiente():
    assert clasificar(_resp(), False).segmento == "informacion_insuficiente"


def test_ubicacion_y_urgencia_es_alta_intencion():
    r = _resp(menciona_ubicacion=0.95, dice_cuando=0.9)
    r["urgencia"]["score"] = 2.6
    cl = clasificar(r, False)
    assert cl.segmento == "alta_intencion" and cl.sede == "palermo"


def test_urgencia_con_dos_picos_no_cuenta_como_pronto():
    r = _resp(menciona_ubicacion=0.95, dice_cuando=0.9)
    r["urgencia"] = {"type": "score", "score": 2.3, "probabilities": {"0": 0.3, "1": 0.05, "2": 0.1, "3": 0.55}}
    assert clasificar(r, False).segmento == "lista_para_cotizar"
    r["urgencia"]["probabilities"] = {"0": 0.02, "1": 0.03, "2": 0.15, "3": 0.8}
    assert clasificar(r, False).segmento == "alta_intencion"


def test_senales_dudosas_van_a_revision_humana():
    cl = clasificar(_resp(menciona_ubicacion=0.5, describe_que_guarda=0.55), False)
    assert cl.segmento == "revision_humana" and cl.revision_humana


def test_tipo_de_mensaje_dudoso_va_a_revision():
    r = _resp()
    r["tipo_de_mensaje"]["confidence"] = 0.4
    assert clasificar(r, False).segmento == "revision_humana"


def test_senales_de_dialogo_solo_cuentan_si_hubo_dialogo():
    r = _resp(desistio=0.95)
    assert clasificar(r, False).segmento != "desistio"
    assert clasificar(r, True).segmento == "desistio"


def test_sede_sin_mencion_de_ubicacion_no_se_informa():
    assert clasificar(_resp(), False).sede is None


# ------------------------------------------------------------------ plantillas
def test_sin_simulacion_no_recomienda_plantillas_no_aprobadas():
    cat = CatalogoPlantillas(RAIZ / "config/plantillas.json", simular=False)
    rec = cat.recomendar("lista_para_cotizar", "mudanza", 0, T0)
    assert rec["plantilla"] is None and rec["revision_humana"]


def test_no_recomienda_plantilla_vencida(tmp_path):
    p = tmp_path / "p.json"
    p.write_text('{"plantillas": [{"id": "x", "nombre_meta": "x", "estado": "aprobada", "vigente_desde": "2025-01-01", '
                 '"vigente_hasta": "2025-12-31", "texto": "t", "uso_previsto": {"segmentos": ["*"], "necesidades": ["*"], "seguimiento_numero": [1]}}]}',
                 encoding="utf-8")
    assert CatalogoPlantillas(p).recomendar("exploratoria", None, 0, T0)["plantilla"] is None


def test_maximo_de_plantillas_sin_respuesta():
    cat = CatalogoPlantillas(RAIZ / "config/plantillas.json", simular=True)
    assert cat.recomendar("exploratoria", None, 2, T0)["plantilla"] is None


def test_desistio_no_recibe_plantilla():
    cat = CatalogoPlantillas(RAIZ / "config/plantillas.json", simular=True)
    assert cat.recomendar("desistio", None, 0, T0)["plantilla"] is None


def test_prefiere_plantilla_especifica():
    cat = CatalogoPlantillas(RAIZ / "config/plantillas.json", simular=True)
    rec = cat.recomendar("exploratoria", "stock_empresa", 0, T0)
    assert rec["plantilla"]["id"] == "seguimiento_empresa_v1" and rec["simulada"]


# ------------------------------------------------------------------ pipeline
def _herramientas():
    info = cargar_info(RAIZ / "config/info_comercial.json")
    return JevSimulado(), RedactorOffline(info), CatalogoPlantillas(RAIZ / "config/plantillas.json", simular=True)


def test_puntos_de_decision_y_no_mira_el_futuro():
    k = c(M(0, "cliente", "Hola, me mudo la semana que viene, busco baulera en Palermo"), M(1, "ventas", "¡Hola! ¿Qué vas a guardar?"),
          M(50, "cliente", "Ya conseguí otro lugar"))
    puntos = puntos_de_decision(k)
    assert [m for _, m in puntos] == ["primer_contacto", "cierre_ventana", "reactivacion", "cierre_ventana"]
    r = evaluar(k, puntos[0][0], "primer_contacto", *_herramientas())
    textos = [m["texto"] for m in r["_payload"]["state"]["conversacion"]]
    assert "Ya conseguí otro lugar" not in " ".join(textos)
    assert r["accion"]["tipo"] == "borrador_libre"
    r2 = evaluar(k, puntos[1][0], "cierre_ventana", *_herramientas())
    assert r2["mensaje_permitido"] == "solo_plantilla_aprobada" and r2["accion"]["tipo"] in ("plantilla", "sin_plantilla")


def test_rafaga_inicial_entra_en_primer_contacto():
    k = Consulta("T-2", [Mensaje(T0, "cliente", "Hola"), Mensaje(T0 + timedelta(minutes=2), "cliente", "busco baulera en Tigre"),
                         Mensaje(T0 + timedelta(minutes=30), "ventas", "Hola!")])
    assert puntos_de_decision(k)[0] == (T0 + timedelta(minutes=2), "primer_contacto")


# ------------------------------------------------------------------ privacidad
def test_jev_api_bloqueado_sin_aprobacion():
    with pytest.raises(JevError):
        JevAPI(envio_externo_aprobado=False)


def test_jev_api_rechaza_datos_personales(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    with pytest.raises(DatosPersonalesError):
        JevAPI(True).preguntar({"conversacion": [{"texto": "mi cel es 11 5555 4444"}]}, {})


def test_anonimizar():
    t = anonimizar_texto("Soy Juan Pérez, mi mail es juan@x.com y mi cel 11-5555-4444, DNI 30.123.456", ["Juan", "Pérez"])
    assert not detectar_pii(t) and "Juan" not in t and "Pérez" not in t


def test_fechas_no_son_datos_personales():
    assert not detectar_pii({"texto": "lo necesito el 15/03/2026 o el 2026-03-20"})
    assert anonimizar_texto("entro el 15-03-2026") == "entro el 15-03-2026"


def test_verificar_borrador_marca_montos():
    assert "menciona un monto" in verificar_borrador("Sale $45.000 por mes")


# ------------------------------------------------------------------ importar
def test_importar_whatsapp_android(tmp_path):
    p = tmp_path / "chat.txt"
    p.write_text("04/05/26, 10:00 - Ana Gómez: Hola, busco baulera\n04/05/26, 10:05 - Don Box: ¡Hola Ana! ¿En qué zona?\n"
                 "04/05/26, 10:07 - Ana Gómez: En Palermo\ny es para la semana que viene\n", encoding="utf-8")
    k = desde_whatsapp_txt(p, ["Don Box"])
    assert [m.autor for m in k.mensajes] == ["cliente", "ventas", "cliente"]
    assert "semana que viene" in k.mensajes[2].texto and k.id_consulta.startswith("C-")


def test_panel_importa_whatsapp_con_resultados(panel_tmp):
    srv, _ = panel_tmp
    chat = "12/03/26, 10:00 - Laura Pérez: Hola, busco baulera en Caballito para fin de mes. Mi cel 11 5555 4444\n12/03/26, 10:20 - Don Box: ¡Hola!\n"
    r = srv.importar({"archivos": [{"nombre": "chat_1.txt", "contenido": chat},
                                    {"nombre": "res.csv", "contenido": "archivo,resultado\nchat_1.txt,Alquiló\n"}],
                      "nombres_ventas": "Don Box"})
    d = srv.cargar_corrida(r["corrida"])
    [c] = d["consultas"]
    assert c["resultado"]["estado"] == "alquilo"
    assert "Laura" not in json.dumps(c, ensure_ascii=False) and not detectar_pii(c["mensajes"])
    srv.guardar_revision({"corrida": r["corrida"], "clave": d["recomendaciones"][0]["clave"], "revision": {"segmento_ok": "si", "sugerencia_nota": 4}})
    assert len(srv.cargar_corrida(r["corrida"])["revisiones"]) == 1
    with pytest.raises(srv.ErrorPanel):
        srv.importar({"archivos": [{"nombre": "x.txt", "contenido": chat}], "nombres_ventas": "Don Box", "jev": "api"})


def test_importar_csv(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("conversation_id,timestamp,direction,body,template_name\n1,2026-05-04 10:00,inbound,Hola tel 1155554444,\n"
                 "1,2026-05-04 10:05,outbound,Hola!,\n1,2026-05-05 12:00,outbound,Seguimos?,seguimiento_v1\n", encoding="utf-8")
    q = tmp_path / "q.csv"
    q.write_text("id_consulta,telefono,zona_formulario,resultado\n1,1155554444,Palermo,Alquiló\n", encoding="utf-8")
    [k] = desde_csv(m, q)
    assert k.mensajes[2].tipo == "plantilla" and "telefono" not in k.propiedades
    assert not detectar_pii(k.a_dict()["mensajes"]) and k.propiedades["zona_formulario"] == "Palermo"
