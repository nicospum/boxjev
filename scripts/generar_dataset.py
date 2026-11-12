"""Genera consultas SINTÉTICAS (inventadas) en el formato canónico.

Sirven para probar el circuito mientras llegan los exportes reales de
Atom/HubSpot. No contienen datos personales. Cada consulta trae una
'etiqueta_ventas' simulada (con ~7% de desacuerdo a propósito) para poder
ejercitar el script de evaluación.

Uso: python scripts/generar_dataset.py --n 500 --salida data/sinteticas/consultas_500.jsonl
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jeventas.modelo import Consulta, Mensaje, escribir_jsonl  # noqa: E402

SALUDOS = ["Hola", "Hola!", "Buenas", "Buen día", "Hola, buenas tardes", "Hola qué tal", "Holaa", ""]
ZONAS = {
    "nunez": ["Núñez", "Belgrano", "Vicente López", "Olivos"],
    "palermo": ["Palermo", "Colegiales", "Villa Crespo", "Chacarita"],
    "saavedra": ["Saavedra", "Munro", "Villa Martelli"],
    "villa_urquiza": ["Villa Urquiza", "Villa Pueyrredón", "Parque Chas"],
    "agronomia": ["Agronomía", "Villa del Parque", "Devoto"],
    "almagro": ["Almagro", "Caballito", "Boedo"],
    "tigre": ["Tigre", "Nordelta", "San Fernando", "Pacheco"],
    "quilmes_bernal": ["Quilmes", "Bernal", "Avellaneda", "Berazategui"],
    "cordoba": ["Córdoba"],
    "fuera_de_cobertura": ["Rosario", "Mar del Plata"],
}
PESO_ZONA = [10, 14, 7, 9, 5, 10, 12, 10, 8, 2]

MOTIVOS = {
    "mudanza": ["me estoy mudando", "nos mudamos y el depto nuevo no está listo", "entrego el depto y todavía no tengo el nuevo", "estoy con la mudanza"],
    "reforma": ["estamos haciendo una obra en casa", "vamos a pintar todo el departamento", "arrancamos una reforma en la cocina"],
    "viaje_o_relocalizacion": ["me voy a vivir afuera un año", "me voy de viaje 6 meses", "me voy a España por trabajo"],
    "stock_empresa": ["tengo un emprendimiento y necesito guardar mercadería", "es para stock de mi tienda online", "necesito guardar herramientas de mi negocio", "somos una pyme y buscamos lugar para insumos"],
    "documentos_archivo": ["necesito guardar documentos de la empresa", "tengo cajas de archivo contable"],
    "espacio_extra": ["no me entra nada en casa", "quiero guardar bicis y cosas de camping", "necesito espacio para cosas de temporada"],
    "sucesion_o_separacion": ["estamos vaciando la casa de mi abuela", "me separé y necesito guardar mis cosas un tiempo", "por una sucesión tenemos que vaciar un depto"],
}
PESO_MOTIVO = [30, 10, 8, 14, 3, 18, 7]
ITEMS = ["los muebles de un 2 ambientes", "unas 20 cajas y un sillón", "heladera, lavarropas y cajas", "muebles de un monoambiente", "una cama, un ropero y cajas", "unos 6 m2 más o menos", "algo de 3 m2", "pallets de mercadería", "un par de bicis y cajas"]
CUANDO = {
    3: ["lo necesito para mañana", "es urgente, para esta semana", "lo necesito ya mismo", "sería para este sábado"],
    2: ["sería para la semana que viene", "lo necesito en 15 días", "para fin de mes", "a partir del lunes 15"],
    1: ["sería para dentro de dos meses", "en marzo más o menos", "no es urgente, para el mes que viene"],
}
PRECIO = ["¿cuánto sale?", "¿qué precio tiene?", "quería saber el valor", "¿me pasan precios?"]
NO_PROSPECTO = {
    "cliente_actual": ["Hola, soy cliente y no puedo entrar a mi baulera hoy", "Buenas, ya alquilo una baulera, necesito la factura de octubre", "Hola, quería consultar por mi contrato, soy cliente"],
    "empleo_o_proveedor": ["Hola, estoy en búsqueda laboral, ¿dónde mando el CV?", "Buenas, ofrecemos servicio de limpieza para depósitos", "Hola, somos proveedores de candados y cajas"],
    "no_relacionado": ["Ganaste un premio, click aca", "Inverti en promo cripto ya", "perdón, número equivocado"],
}
RESPUESTAS_VENTAS = [
    "¡Hola! Gracias por escribir a Don Box. ¿En qué zona buscás la baulera y qué te gustaría guardar?",
    "¡Hola! Te ayudamos. Contame qué vas a guardar y desde cuándo lo necesitás así te paso opciones.",
    "Hola, gracias por contactarnos. ¿Para qué sucursal sería?",
    "¡Hola! Con gusto. Te paso las opciones de tamaño. ¿Desde qué fecha lo necesitarías?",
]
CIERRES_CLIENTE = {
    "reservar": ["Dale, lo quiero. ¿Cómo pago?", "Perfecto, ¿qué necesito para reservar?", "Dale avancemos con el de 3 m2"],
    "tiempo": ["Buenísimo, lo pienso y te aviso", "Lo charlo en casa y les aviso", "Gracias, más adelante les escribo"],
    "precio": ["Uh, se me va de presupuesto", "Está un poco caro, ¿no tienen descuento?"],
    "desiste": ["Gracias, ya conseguí otro lugar", "Al final ya lo resolví, gracias", "Ya no lo necesito, gracias igual"],
}
PLANTILLAS = ["seguimiento_cotizacion_v1", "seguimiento_mudanza_v1", "pedido_datos_v1", "reenganche_suave_v1", "seguimiento_empresa_v1"]
TEXTO_PLANTILLA = {
    "seguimiento_cotizacion_v1": "Hola, te escribimos de Don Box por tu consulta de baulera. ¿Seguimos con la cotización?",
    "seguimiento_mudanza_v1": "Hola, ¿cómo va la mudanza? Si todavía necesitás guardar cosas, respondé este mensaje.",
    "pedido_datos_v1": "Hola, gracias por escribir a Don Box. ¿En qué zona buscás la baulera y qué te gustaría guardar?",
    "reenganche_suave_v1": "Hola, quedamos a disposición por tu consulta de baulera.",
    "seguimiento_empresa_v1": "Hola, te escribimos de Don Box por tu consulta para guardar mercadería. ¿Te sirve que lo veamos?",
}
CAMPANIAS = ["meta_mudanzas_2026q2", "google_search_bauleras", "meta_empresas_stock", "google_pmax_cordoba", "organico", None]


def segmento_verdadero(ubic: bool, items: bool, cuando: bool, motivo: bool, urg: int, precio: bool) -> str:
    """Misma definición que reglas.py, aplicada a las variables latentes (lo que 'diría Alberto')."""
    if ubic and cuando and urg >= 2:
        return "alta_intencion"
    if ubic and (items or motivo or cuando):
        return "lista_para_cotizar"
    if ubic or items or cuando or motivo or precio:
        return "exploratoria"
    return "informacion_insuficiente"


def generar(n: int, semilla: int) -> list[Consulta]:
    rnd = random.Random(semilla)
    inicio = datetime(2026, 3, 1, 8, 0)
    consultas = []
    for i in range(n):
        t0 = inicio + timedelta(days=rnd.randint(0, 180), hours=rnd.uniform(0, 13))
        idc = f"SIM-{i + 1:04d}"
        tipo = rnd.choices(["consulta_nueva", "cliente_actual", "empleo_o_proveedor", "no_relacionado"], [90, 4, 3, 3])[0]
        props: dict = {}
        origen = {"fuente": rnd.choice(["PAID_SOCIAL", "PAID_SEARCH", "ORGANIC_SEARCH", "DIRECT"])}
        camp = rnd.choice(CAMPANIAS)
        if camp:
            origen["campania"] = camp

        if tipo != "consulta_nueva":
            msgs = [Mensaje(t0, "cliente", rnd.choice(NO_PROSPECTO[tipo]))]
            if rnd.random() < 0.8:
                msgs.append(Mensaje(t0 + timedelta(minutes=rnd.randint(5, 240)), "ventas", "Hola, te derivamos con el área que corresponde."))
            consultas.append(Consulta(idc, msgs, origen=origen, propiedades=props,
                                      resultado={"estado": "desconocido"},
                                      etiqueta_ventas={"segmento": "no_es_prospecto", "tipo": tipo, "revisado_por": "simulado"},
                                      sintetica=True))
            continue

        necesidad = rnd.choices(list(MOTIVOS), PESO_MOTIVO)[0]
        sede = rnd.choices(list(ZONAS), PESO_ZONA)[0]
        motivo = rnd.random() < 0.6
        ubic = rnd.random() < 0.55
        items = rnd.random() < 0.4
        cuando = rnd.random() < 0.45
        urg = rnd.choices([1, 2, 3], [35, 40, 25])[0] if cuando else 0
        precio = rnd.random() < 0.45
        if rnd.random() < 0.25:  # vino de formulario con zona
            props["zona_formulario"] = rnd.choice(ZONAS[sede])
            ubic = True

        partes = [rnd.choice(SALUDOS)]
        if motivo:
            partes.append(rnd.choice(MOTIVOS[necesidad]).capitalize() + ".")
        quiero = "Necesito una baulera" if rnd.random() < 0.5 else "Quería consultar por una baulera"
        if ubic and "zona_formulario" not in props:
            quiero += f" en {rnd.choice(ZONAS[sede])}"
        partes.append(quiero + ".")
        if items:
            partes.append(f"Sería para guardar {rnd.choice(ITEMS)}.")
        if cuando:
            partes.append(rnd.choice(CUANDO[urg]).capitalize() + ".")
        if precio:
            partes.append(rnd.choice(PRECIO).capitalize() if rnd.random() < 0.5 else rnd.choice(PRECIO))
        texto = " ".join(p for p in partes if p).strip()
        if not (motivo or ubic or items or cuando or precio):
            texto = rnd.choice(["Hola, quería info", "Hola! Info por favor", "Buenas, ¿me pasan información?", "Hola, vi el anuncio"])

        msgs = []
        if rnd.random() < 0.3 and len(partes) > 3:  # ráfaga: el prospecto manda dos mensajes seguidos
            corte = len(partes) // 2
            msgs.append(Mensaje(t0, "cliente", " ".join(partes[:corte])))
            msgs.append(Mensaje(t0 + timedelta(minutes=rnd.randint(1, 4)), "cliente", " ".join(partes[corte:])))
        else:
            msgs.append(Mensaje(t0, "cliente", texto))

        t = msgs[-1].ts + timedelta(minutes=rnd.choice([3, 10, 25, 60, 180, 420]))
        msgs.append(Mensaje(t, "ventas", rnd.choice(RESPUESTAS_VENTAS)))

        # comportamiento posterior
        intencion = {"alta_intencion": 0.75, "lista_para_cotizar": 0.6, "exploratoria": 0.45, "informacion_insuficiente": 0.35}
        seg_real = segmento_verdadero(ubic, items, cuando, motivo, urg, precio)
        responde = rnd.random() < intencion[seg_real]
        resultado = "desconocido"
        if responde:
            t += timedelta(minutes=rnd.randint(5, 600))
            detalle = []
            if not ubic:
                detalle.append(f"En {rnd.choice(ZONAS[sede])}")
            if not items:
                detalle.append(f"para {rnd.choice(ITEMS)}")
            if not cuando:
                detalle.append(rnd.choice(CUANDO[rnd.choice([1, 2])]))
            msgs.append(Mensaje(t, "cliente", (", ".join(detalle) or "Perfecto, gracias") + "."))
            t += timedelta(minutes=rnd.randint(5, 120))
            msgs.append(Mensaje(t, "ventas", "Genial, te paso la cotización con las opciones para esa sede. La unidad se confirma al reservar."))
            final = rnd.choices(["reservar", "tiempo", "precio", "desiste", "silencio"], [30, 20, 12, 10, 28])[0]
            if final != "silencio":
                t += timedelta(minutes=rnd.randint(10, 900))
                msgs.append(Mensaje(t, "cliente", rnd.choice(CIERRES_CLIENTE[final])))
                resultado = {"reservar": "alquilo", "desiste": "no_alquilo", "precio": rnd.choice(["no_alquilo", "alquilo"]), "tiempo": rnd.choice(["desconocido", "alquilo", "no_alquilo"])}[final]
                if final in ("tiempo", "precio"):
                    t += timedelta(minutes=rnd.randint(5, 60))
                    msgs.append(Mensaje(t, "ventas", "Dale, quedamos atentos por acá."))
        # seguimiento con plantilla si el prospecto quedó en silencio
        if msgs[-1].autor == "ventas" and resultado == "desconocido" and rnd.random() < 0.6:
            ult_cli = max(m.ts for m in msgs if m.autor == "cliente")
            t = ult_cli + timedelta(hours=rnd.uniform(24.5, 40))
            pid = rnd.choice(PLANTILLAS)
            msgs.append(Mensaje(t, "ventas", TEXTO_PLANTILLA[pid], tipo="plantilla", plantilla_id=pid))
            if rnd.random() < 0.25:
                t += timedelta(hours=rnd.uniform(0.2, 20))
                msgs.append(Mensaje(t, "cliente", rnd.choice(["Hola sí, sigo interesado. ¿Me pasás precio?", "Sí, ¿tienen lugar para el mes que viene?", "Gracias, ya lo resolví"])))
                resultado = rnd.choice(["alquilo", "no_alquilo", "desconocido"])
            else:
                resultado = rnd.choice(["no_alquilo", "desconocido"])

        etiqueta = seg_real
        if rnd.random() < 0.07:  # desacuerdo humano simulado
            etiqueta = rnd.choice([s for s in ("alta_intencion", "lista_para_cotizar", "exploratoria", "informacion_insuficiente") if s != seg_real])
        consultas.append(Consulta(
            idc, msgs, origen=origen, propiedades=props, resultado={"estado": resultado},
            etiqueta_ventas={"segmento": etiqueta, "necesidad": necesidad if motivo else None,
                             "sede": sede if ubic else None, "es_empresa": necesidad in ("stock_empresa", "documentos_archivo"),
                             "revisado_por": "simulado"},
            sintetica=True,
        ))
    return consultas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--salida", default="data/sinteticas/consultas_500.jsonl")
    a = ap.parse_args()
    n = escribir_jsonl(a.salida, generar(a.n, a.semilla))
    print(f"{n} consultas sintéticas -> {a.salida}")


if __name__ == "__main__":
    main()
