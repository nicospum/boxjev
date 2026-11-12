"""Cliente de Jev (TypeSafe System One) + un Jev simulado para probar sin red.

- `JevAPI`: POST https://api.typesafe.ai/v1/systemone (doc: docs.typesafe.ai/api/system-one).
  Bloqueado por defecto: solo envía si se lo habilita explícitamente
  (aprobación de Don Box para compartir conversaciones) y si el state no
  contiene teléfonos, emails ni DNI/CUIT.
- `JevSimulado`: heurística por palabras clave, determinística. SOLO sirve para
  probar el circuito de punta a punta; sus "probabilidades" no significan nada.

Un error de la API es un error, nunca una respuesta "no".
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import unicodedata

URL_API = "https://api.typesafe.ai/v1/systemone"
MODELO_POR_DEFECTO = "jev-1.14.0"  # fijar versión: 'jev-latest' cambia sin aviso

_PATRONES_PII = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "telefono": re.compile(r"(?<!\d)(?:\+?54\s?9?\s?)?(?:\d[\s-]?){8,12}(?!\d)"),
    "dni_cuit": re.compile(r"\b\d{2}[.-]?\d{3}[.-]?\d{3}\b|\b\d{2}-\d{8}-\d\b"),
}


class JevError(RuntimeError):
    pass


class DatosPersonalesError(JevError):
    pass


# Fechas y horas (15/03/2026, 2026-05-04T10:00) no son datos personales: se ignoran.
FECHA = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?\b")


def detectar_pii(obj) -> list[str]:
    texto = FECHA.sub(" ", json.dumps(obj, ensure_ascii=False))
    return [nombre for nombre, pat in _PATRONES_PII.items() if pat.search(texto)]


class JevAPI:
    nombre = "jev-api"
    simulado = False

    def __init__(
        self,
        envio_externo_aprobado: bool,
        api_key: str | None = None,
        modelo: str = MODELO_POR_DEFECTO,
        timeout: float = 30.0,
        reintentos: int = 3,
    ) -> None:
        if not envio_externo_aprobado:
            raise JevError("falta la aprobación de Don Box para enviar conversaciones a TypeSafe.")
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise JevError("falta la clave de TypeSafe (TYPESAFE_API_KEY).")
        self.modelo = modelo
        self.timeout = timeout
        self.reintentos = reintentos

    def preguntar(self, estado: dict, preguntas: dict) -> dict:
        pii = detectar_pii(estado)
        if pii:
            raise DatosPersonalesError(f"El state contiene posibles datos personales ({', '.join(pii)}); anonimizar antes.")
        cuerpo = json.dumps({"model": self.modelo, "state": estado, "questions": preguntas}).encode("utf-8")
        req = urllib.request.Request(
            URL_API,
            data=cuerpo,
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        espera = 1.0
        for intento in range(self.reintentos + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                return {"modelo": data.get("model"), "respuestas": data["answers"], "uso": data.get("usage")}
            except urllib.error.HTTPError as e:
                detalle = e.read().decode("utf-8", "replace")[:500]
                if e.code in (429, 500, 502, 503, 504) and intento < self.reintentos:
                    time.sleep(espera)
                    espera *= 2
                    continue
                raise JevError(f"TypeSafe respondió {e.code}: {detalle}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if intento < self.reintentos:
                    time.sleep(espera)
                    espera *= 2
                    continue
                raise JevError(f"No se pudo conectar con TypeSafe: {e}") from e
        raise JevError("Reintentos agotados")


# ---------------------------------------------------------------------------
# Jev simulado (sin red). No usar sus resultados para medir calidad.
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_KW = {
    "mudanza": ["mudanza", "mudo", "mudamos", "mudarme", "mudarnos", "departamento nuevo", "entrego el depto", "alquiler nuevo"],
    "reforma": ["reforma", "obra", "pintar", "pintura", "remodel", "arreglo"],
    "viaje_o_relocalizacion": ["viaje", "viajo", "exterior", "afuera", "me voy a vivir", "europa", "espana", "meses afuera"],
    "stock_empresa": ["mercaderia", "stock", "emprendimiento", "tienda online", "local", "herramientas", "pymes", "empresa", "mi negocio", "insumos"],
    "documentos_archivo": ["documentos", "archivo", "cajas de archivo", "expedientes", "papeles contables"],
    "espacio_extra": ["espacio", "bicicleta", "bici", "kayak", "tabla", "cosas de temporada", "no me entra", "camping"],
    "sucesion_o_separacion": ["sucesion", "herencia", "fallecio", "mi viejo", "casa de mi abuela", "separacion", "divorcio", "me separe"],
}
_SEDE_KW = {
    "nunez": ["nunez", "belgrano", "coghlan", "vicente lopez", "olivos"],
    "palermo": ["palermo", "colegiales", "chacarita", "villa crespo", "recoleta"],
    "saavedra": ["saavedra", "villa martelli", "munro", "florida"],
    "villa_urquiza": ["urquiza", "pueyrredon", "parque chas", "ortuzar"],
    "agronomia": ["agronomia", "villa del parque", "paternal", "devoto"],
    "almagro": ["almagro", "caballito", "boedo", "once", "balvanera", "centro"],
    "tigre": ["tigre", "nordelta", "san fernando", "pacheco", "don torcuato", "zona norte"],
    "quilmes_bernal": ["quilmes", "bernal", "avellaneda", "berazategui", "lanus", "zona sur"],
    "cordoba": ["cordoba"],
    "fuera_de_cobertura": ["rosario", "mar del plata", "mendoza", "la plata", "neuquen"],
}
_ITEMS = ["muebles", "cajas", "heladera", "lavarropas", "sillon", "cama", "colchon", "mesa", "sillas", "m2", "m3", "metros", "ropero", "placard", "monoambiente", "2 ambientes", "3 ambientes", "pallets", "bici"]
_CUANDO = ["manana", "pasado", "semana", "mes que viene", "proximo mes", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "fin de mes", "hoy", "ya mismo", "urgente", "en marzo", "en abril", "en diciembre", "en enero", "15 dias", "quincena"]
_URGENTE = ["hoy", "manana", "es urgente", "ya mismo", "esta semana", "pasado manana", "lo antes posible"]
_PRONTO = ["semana que viene", "proxima semana", "15 dias", "fin de mes", "quincena", "lunes", "viernes", "sabado"]


def _p(cond: bool, si: float = 0.9, no: float = 0.08) -> float:
    return si if cond else no


def _choice(opciones: list[str], ganador: str, conf: float) -> dict:
    resto = (1 - conf) / max(1, len(opciones) - 1)
    probs = {o: (conf if o == ganador else resto) for o in opciones}
    return {"type": "choice", "choice": ganador, "confidence": conf, "probabilities": probs}


class JevSimulado:
    nombre = "jev-simulado"
    simulado = True
    modelo = "simulado"

    def preguntar(self, estado: dict, preguntas: dict) -> dict:
        conv = estado.get("conversacion", [])
        cli = _norm(" ".join(m["texto"] for m in conv if m["de"] == "Prospecto"))
        form = _norm(json.dumps(estado.get("datos_del_formulario", {}), ensure_ascii=False))
        todo = cli + " " + form
        ult_cli = _norm(next((m["texto"] for m in reversed(conv) if m["de"] == "Prospecto"), ""))
        cli = cli.replace("no es urgente", "")

        def hay(kws, t=todo):  # palabra completa, para no confundir "once" con "entonces"
            return any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in kws)

        r: dict = {}
        for nombre, q in preguntas.items():
            if nombre == "tipo_de_mensaje":
                if hay(["cv", "curriculum", "busqueda laboral", "ofrecemos", "proveedor"], cli):
                    g = "empleo_o_proveedor"
                elif hay(["ya alquilo", "mi baulera", "soy cliente", "factura", "mi contrato", "no puedo entrar"], cli):
                    g = "cliente_actual"
                elif hay(["ganaste", "promo cripto", "click aca", "inverti"], cli):
                    g = "no_relacionado"
                else:
                    g = "consulta_nueva"
                r[nombre] = _choice(list(q["criteria"]), g, 0.88)
            elif nombre == "necesidad":
                g = next((k for k, kws in _KW.items() if hay(kws)), "otra")
                r[nombre] = _choice(list(q["criteria"]), g, 0.75 if g != "otra" else 0.4)
            elif nombre == "dice_motivo":
                r[nombre] = {"type": "noul", "noul": _p(any(hay(k) for k in _KW.values()))}
            elif nombre == "sede":
                g = next((k for k, kws in _SEDE_KW.items() if hay(kws)), "palermo")
                r[nombre] = _choice(list(q["criteria"]), g, 0.8 if hay(sum(_SEDE_KW.values(), [])) else 0.2)
            elif nombre == "menciona_ubicacion":
                r[nombre] = {"type": "noul", "noul": _p(hay(sum(_SEDE_KW.values(), [])) or "zona" in form)}
            elif nombre == "describe_que_guarda":
                r[nombre] = {"type": "noul", "noul": _p(hay(_ITEMS))}
            elif nombre == "dice_cuando":
                r[nombre] = {"type": "noul", "noul": _p(hay(_CUANDO, cli))}
            elif nombre == "urgencia":
                pos = 3 if hay(_URGENTE, cli) else 2 if hay(_PRONTO, cli) else 1 if hay(_CUANDO, cli) else 0
                probs = {str(i): (0.7 if i == pos else 0.1) for i in range(4)}
                r[nombre] = {"type": "score", "score": float(pos), "confidence": 0.7, "probabilities": probs,
                             "legend": {str(i): t for i, t in enumerate(q["criteria"])}}
            elif nombre == "pide_precio":
                r[nombre] = {"type": "noul", "noul": _p(hay(["precio", "cuanto sale", "cuanto cuesta", "valor", "tarifa", "cotiz"], cli))}
            elif nombre == "es_empresa":
                r[nombre] = {"type": "noul", "noul": _p(hay(_KW["stock_empresa"]))}
            elif nombre == "quiere_visitar":
                r[nombre] = {"type": "noul", "noul": _p(hay(["visitar", "pasar a ver", "conocer", "ir a ver"], cli))}
            elif nombre == "desistio":
                r[nombre] = {"type": "noul", "noul": _p(hay(["ya consegui", "ya lo resolvi", "no necesito", "otro lugar", "ya no"], ult_cli))}
            elif nombre == "objecion_precio":
                r[nombre] = {"type": "noul", "noul": _p(hay(["caro", "presupuesto", "descuento", "se me va"], ult_cli))}
            elif nombre == "pidio_tiempo":
                r[nombre] = {"type": "noul", "noul": _p(hay(["lo pienso", "te aviso", "les aviso", "mas adelante", "despues te confirmo", "lo charlo"], ult_cli))}
            elif nombre == "quiere_reservar":
                r[nombre] = {"type": "noul", "noul": _p(hay(["reservar", "lo tomo", "como pago", "que necesito para", "dale avancemos", "lo quiero"], ult_cli))}
            elif nombre == "pregunta_sin_responder":
                ult = conv[-1] if conv else {}
                r[nombre] = {"type": "noul", "noul": _p(ult.get("de") == "Prospecto" and "?" in ult.get("texto", ""))}
            elif nombre == "categoria":
                r[nombre] = self._categoria(q["criteria"], conv, cli, ult_cli, form, hay)
            elif nombre == "categoria_encaja":
                r[nombre] = {"type": "noul", "noul": 0.85}
            else:
                r[nombre] = {"type": q["type"], "noul": 0.5}
        return {"modelo": "simulado", "respuestas": r, "uso": None}

    @staticmethod
    def _categoria(opciones: dict, conv: list, cli: str, ult_cli: str, form: str, hay) -> dict:
        """Elige categoría: primero reglas para las categorías de la propuesta inicial,
        después coincidencia de palabras entre la descripción y la conversación."""
        de = [m["de"] for m in conv]
        i_ventas = de.index("Ventas Don Box") if "Ventas Don Box" in de else None
        respondio = i_ventas is not None and "Prospecto" in de[i_ventas + 1:]
        hubo_plantilla = any(m["texto"].startswith("[Plantilla") for m in conv)
        ubic = hay(sum(_SEDE_KW.values(), [])) or "zona" in form
        pronto = hay(_URGENTE + _PRONTO, cli)
        datos = sum([ubic, hay(_ITEMS), hay(_CUANDO, cli), any(hay(k) for k in _KW.values())])
        candidatos = [
            ("no_es_prospecto", hay(["cv", "curriculum", "busqueda laboral", "ofrecemos", "proveedor", "soy cliente", "factura", "mi contrato", "ganaste", "inverti"], cli)),
            ("desistio", hay(["ya consegui", "ya lo resolvi", "no necesito", "otro lugar", "ya no"], ult_cli)),
            ("quiere_reservar", hay(["reservar", "reservo", "lo tomo", "como pago", "lo quiero", "dale avancemos"], ult_cli)),
            ("objecion_precio", hay(["caro", "presupuesto", "descuento", "se me va"], ult_cli)),
            ("pidio_tiempo", hay(["lo pienso", "te aviso", "les aviso", "mas adelante", "lo charlo"], ult_cli)),
            ("volvio_interesado", hubo_plantilla and conv and conv[-1]["de"] == "Prospecto"),
            ("nunca_respondio", i_ventas is not None and not respondio),
            ("se_enfrio", respondio),
            ("empresa", hay(_KW["stock_empresa"] + _KW["documentos_archivo"])),
            ("alta_intencion", ubic and pronto),
            ("lista_para_cotizar", ubic and datos >= 2),
            ("exploratoria", datos >= 1 or hay(["precio", "cuanto sale", "valor"], cli)),
            ("informacion_insuficiente", True),
        ]
        ganador = next((cid for cid, ok in candidatos if ok and cid in opciones), None)
        if ganador is None:  # categorías nuevas: coincidencia de palabras
            texto = _norm(" ".join(m["texto"] for m in conv))
            def puntaje(desc: str) -> int:
                return sum(1 for w in set(re.findall(r"[a-z]{5,}", _norm(desc))) if w in texto)
            ganador = max(opciones, key=lambda k: puntaje(opciones[k]))
        return _choice(list(opciones), ganador, 0.72)
