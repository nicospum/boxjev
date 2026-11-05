# JeVentas — Diseño del piloto

Asistente interno para Ventas de Don Box. Clasifica consultas de WhatsApp, sugiere la próxima respuesta y, fuera de la ventana de 24 h, recomienda una plantilla aprobada. **No envía nada**: una persona revisa y envía.

Estado al 05/11/2026: circuito completo funcionando con 500 consultas **sintéticas**, Jev **simulado** y plantillas **de ejemplo**. Falta: datos reales, plantillas reales, categorías validadas por Alberto y aprobación de Don Box para usar proveedores externos.

---

## 1. Flujo y componentes

```
Exporte Atom/HubSpot ──► importar.py (formato común + anonimizar)
                              │
                              ▼
        para cada momento de decisión (primer contacto · cierre de ventana · reactivación)
                              │
   ventana.py ── reloj de 24 h desde el último mensaje del cliente (código)
                              │
   estado.py ─── arma el "state": conversación hasta ese momento + datos del formulario + hechos
                              │
   jev.py ────── Jev responde ~16 preguntas en UNA llamada (juicios observables con probabilidad)
                              │
   reglas.py ─── tabla de decisión en código → segmento, datos faltantes, explicación, revisión humana
                              │
          ┌───────────────────┼─────────────────────────┐
   ventana abierta,      ventana cerrada           no es prospecto / desistió
   habló el cliente           │                          │
          │              plantillas.py               derivar / cerrar
   redactor.py           (solo aprobadas y
   (Claude) borrador      vigentes)
          │                   │
          └──────► recomendación + datos usados + cuándo interviene una persona
                              │
                    PERSONA DE VENTAS revisa y envía
```

| Componente | Archivo | Qué hace |
|---|---|---|
| Formato común | `jeventas/modelo.py` | Consulta = mensajes + propiedades + resultado + etiqueta de Ventas. |
| Importación | `jeventas/importar.py` | CSV de mensajes, chats `.txt` de WhatsApp; anonimiza. |
| Ventana 24 h | `jeventas/ventana.py` | Reglas de WhatsApp, 100 % código. |
| State | `jeventas/estado.py` | Lo que Ventas veía en ese momento, sin futuro ni resultado. |
| Preguntas | `jeventas/preguntas.py` | Todas las preguntas a Jev, versionadas, en un solo lugar. |
| Jev | `jeventas/jev.py` | Cliente HTTP (bloqueado sin aprobación) + Jev simulado para pruebas. |
| Decisión | `jeventas/reglas.py` | De juicios a segmento. Umbrales 0,7 / 0,3. |
| Borradores | `jeventas/redactor.py` | Claude (otro modelo) o textos base offline. Marca montos y promesas. |
| Plantillas | `jeventas/plantillas.py` | Solo aprobadas y vigentes; máximo 2 seguidas sin respuesta. |
| Evaluación | `jeventas/evaluacion.py` | Acuerdo con Ventas, matriz de confusión, uso de plantillas, resultado por segmento. |

### Por qué Jev no decide el segmento

Siguiendo la guía de TypeSafe, a Jev no se le pregunta "¿qué tipo de prospecto es?". Se le hacen preguntas simples y observables ("¿dice en qué zona?", "¿dice cuándo lo necesita?", "¿pidió precio?") y **el código** combina las respuestas. Así la regla es visible, se puede discutir con Alberto y cambiar sin re-entrenar nada; y si Jev duda (probabilidad entre 0,3 y 0,7) el caso va a revisión humana en lugar de forzar una categoría.

---

## 2. Datos requeridos y faltantes

| Dato | Para qué | Estado |
|---|---|---|
| Mensajes con fecha/hora, cliente y Ventas | State + ventana | **Falta** exporte de Atom |
| Plantillas enviadas (cuál y cuándo) | Ventana + comparar recomendación | **Falta** (¿Atom lo registra?) |
| Zona/sede y propiedades al primer contacto | State | **Falta** confirmar qué guarda HubSpot y si hay histórico de valores |
| Resultado comercial (alquiló / no / desconocido) | Evaluación | **Falta** vincular Atom ↔ HubSpot |
| Clasificación de Ventas sobre una muestra | Medir acuerdo | **Falta** (Alberto, ~100 casos) |
| Listado de plantillas aprobadas, texto, vigencia y uso | Recomendación | **Falta** (hay ejemplos en `config/plantillas.json`) |
| Información comercial aprobada | Borradores | Precargada desde el FAQ (`config/info_comercial.json`), **falta validar** |
| Aprobación de Don Box para enviar a TypeSafe/Anthropic | Usar Jev y Claude reales | **Falta** |

---

## 3. Categorías propuestas (validar con Alberto y Ventas)

Se calculan en `reglas.py` a partir de señales observables.

| Segmento | Regla (señales) | Próximo paso sugerido |
|---|---|---|
| `alta_intencion` | Dice dónde **y** lo necesita en ≤ 2–3 semanas | Borrador para cotizar ya; pedir solo lo que falte |
| `lista_para_cotizar` | Dice dónde **y** (qué guarda, para qué o cuándo) | Borrador con opciones; pedir 1–2 datos |
| `exploratoria` | Una sola señal (solo zona, solo precio, solo motivo) | Borrador que pide zona y qué guarda |
| `informacion_insuficiente` | Ninguna señal ("hola, info") | Borrador que pide datos; nunca forzar categoría |
| `listo_para_reservar` | Pide reservar / cómo pagar (tras conversar) | **Persona**, prioridad |
| `objecion_precio` | Dice que es caro | **Persona**; no prometer descuentos |
| `pidio_tiempo` | "Lo pienso y te aviso" | Esperar; plantilla de retomar |
| `desistio` | Ya lo resolvió / otro proveedor | Cerrar; no enviar plantillas |
| `no_es_prospecto` | Cliente actual, empleo/proveedor, spam | Derivar |
| `revision_humana` | Tipo de mensaje dudoso o ≥ 2 señales dudosas | **Persona** |

Además, en cada caso: **necesidad** (mudanza, reforma, viaje, stock de empresa, documentos, espacio extra, sucesión/separación, otra), **sede** más cercana, **empresa sí/no**, **urgencia** (0–3) y **alertas** (pregunta sin responder, zona sin cobertura).

Preguntas para Alberto: ¿estas señales son las que él mira? ¿La urgencia de "2–3 semanas" es el corte correcto? ¿Empresa debe ser un segmento propio o una marca? ¿Hay segmentos que faltan (p. ej. "compara con la competencia")?

---

## 4. Esquema de entrada y salida de Jev

**Entrada** (una llamada por momento de decisión): `POST https://api.typesafe.ai/v1/systemone`

```json
{
  "model": "jev-1.14.0",
  "state": {
    "empresa": "Don Box alquila bauleras privadas (self storage) en CABA, Tigre, Quilmes/Bernal y Córdoba.",
    "canal": "WhatsApp",
    "conversacion": [
      {"de": "Prospecto", "cuando": "+0 min desde el primer mensaje", "texto": "Hola! Me mudo la semana que viene..."},
      {"de": "Ventas Don Box", "cuando": "+20 min desde el primer mensaje", "texto": "¡Hola! ¿Qué vas a guardar?"}
    ],
    "datos_del_formulario": {"Zona elegida en el formulario": "Palermo"},
    "hechos": ["El prospecto no escribió nada en las últimas 24 h; Ventas le envió 1 mensaje(s) que siguen sin respuesta."]
  },
  "questions": { "...": "ver jeventas/preguntas.py (16 preguntas: 3 choice, 1 score, 12 noul)" }
}
```

**Salida de JeVentas** (una línea de `recomendaciones.jsonl` por momento de decisión):

```json
{
  "id_consulta": "C-…", "punto": "cierre_ventana", "evaluado_en": "…",
  "ventana": {"abierta": false, "ultimo_entrante": "…", "cierra_en": "…", "plantillas_sin_respuesta": 0},
  "mensaje_permitido": "solo_plantilla_aprobada",
  "clasificacion": {
    "segmento": "lista_para_cotizar", "necesidad": "mudanza", "sede": "palermo", "es_empresa": "no",
    "senales": {"menciona_ubicacion": {"prob": 0.93, "lectura": "si"}, "...": "..."},
    "datos_faltantes": ["desde cuándo lo necesita"],
    "explicacion": ["Señal presente: sucursal o zona (p=0.93)."],
    "revision_humana": false, "alertas": []
  },
  "accion": {"tipo": "plantilla", "plantilla": {"id": "…", "texto": "…"}, "motivo": "…"},
  "envio": "manual: una persona revisa y envía",
  "datos_utilizados": ["canal", "conversacion", "datos_del_formulario"],
  "jev": {"modelo": "jev-1.14.0", "version_preguntas": "2026-11-05.1"},
  "observado": {"siguiente_mensaje_ventas": "…", "plantilla_usada_por_ventas": "…", "resultado": "alquilo"}
}
```

`observado` es lo que pasó después; **nunca** se le muestra a Jev, solo sirve para comparar. Cada llamada guarda su payload en `payloads/` para poder repetirla.

---

## 5. Reglas de la ventana de WhatsApp y de plantillas

1. La ventana de 24 h se cuenta desde el **último mensaje entrante del cliente**.
2. Solo un mensaje del cliente la renueva. Mensajes de Ventas, plantillas y respuestas automáticas no.
3. Ventana abierta → se puede sugerir un mensaje libre. Si habló último Ventas, se espera; con ≤ 4 h restantes se sugiere un último mensaje libre (ahorra una plantilla; **a validar**).
4. Ventana cerrada → solo plantilla **aprobada y vigente** del catálogo. Nunca se genera ni se edita una plantilla.
5. Si el cliente responde la plantilla, la ventana se abre otra vez y se reclasifica con toda la conversación.
6. Máximo 2 plantillas seguidas sin respuesta; después se pausa (las plantillas reenganchan, no presionan).
7. Sin plantilla para: desistió, no es prospecto, listo para reservar, objeción de precio, revisión humana.
8. Si ninguna plantilla aprobada encaja → "sin plantilla" y revisión humana.

---

## 6. Plan de prueba retrospectiva, métricas y criterios

**Paso 1 — Datos (semana 1).** Exporte de 100–200 conversaciones, anonimizado. Separar 30 % como conjunto de control que no se mira mientras se ajustan las preguntas.

**Paso 2 — Etiquetas (semana 1–2).** Alberto clasifica el primer contacto de ~100 casos con las categorías acordadas, **sin** ver la salida del sistema. Si se puede, un segundo vendedor etiqueta 30 de esos para medir el acuerdo entre personas (techo realista).

**Paso 3 — Clasificación con Jev (semana 2).** Correr con Jev real sobre los datos anonimizados. Revisar caso por caso los desacuerdos: ¿falla el state, la pregunta o la regla?

**Paso 4 — Borradores y plantillas (semana 3).** Ventas completa `revision_ventas.csv`: ¿segmento correcto?, ¿borrador utilizable (1–5)?, ¿plantilla adecuada?

**Métricas**

| Métrica | Cómo se mide |
|---|---|
| Acuerdo de segmento con Ventas | % de coincidencia en primer contacto (y por segmento: recall/precisión) |
| Tasa de revisión humana | % que el sistema deriva; ni muy alta (no ayuda) ni ~0 (fuerza categorías) |
| Errores graves | Prospecto de alta intención clasificado como insuficiente/no prospecto, o al revés |
| Borradores utilizables | % con nota ≥ 4; % con alertas (montos, promesas) |
| Plantillas | % de cierres con plantilla adecuada según Ventas; 0 recomendaciones no aprobadas |
| Tiempo de revisión | Minutos por caso con y sin la sugerencia (muestra cronometrada) |
| Resultado comercial | Descriptivo por segmento, separando registros incompletos. **No** prueba causalidad. |

**Criterios para seguir (propuesta)**
- Acuerdo con Ventas ≥ 80 % en el conjunto de control y ≥ al acuerdo entre dos vendedores menos 10 puntos.
- Errores graves ≤ 3 %.
- ≥ 70 % de borradores con nota ≥ 4 y 0 borradores con precios o promesas no aprobadas que pasen sin alerta.
- 0 plantillas no aprobadas recomendadas.

**Criterios para frenar:** errores graves > 8 %, revisión humana > 40 %, o Ventas no ahorra tiempo.

---

## 7. Riesgos

**Privacidad**
- Conversaciones con nombres, teléfonos y direcciones → anonimizar antes de todo; el envío a TypeSafe/Anthropic está bloqueado en código hasta tener aprobación (`--envio-externo-aprobado`) y además rechaza payloads con teléfonos/emails/DNI.
- Revisar condiciones de uso y retención de datos de TypeSafe y Anthropic antes del primer envío real.
- Los audios y fotos no se procesan (Jev no admite audio); quedan como "[audio sin transcripción]".

**Integración**
- No sabemos el formato de Atom ni si registra plantillas enviadas → pedir 5 conversaciones crudas antes del lote.
- HubSpot guarda el valor actual de las propiedades, no el del primer contacto → riesgo de "mirar el futuro". Usar solo propiedades del formulario o el historial de propiedades.
- Vincular Atom ↔ HubSpot para el resultado puede requerir el teléfono → hacerlo dentro de Don Box y entregar solo el código anónimo.

**WhatsApp**
- Enviar fuera de la ventana sin plantilla aprobada viola la política de Meta → la regla está en código y probada.
- Exceso de plantillas → bloqueos o baja de calidad del número → tope de 2 seguidas sin respuesta.
- Las plantillas de marketing tienen costo por envío y límites → considerar en la etapa en vivo.

**Modelo**
- Jev rinde mejor en inglés; las conversaciones están en español rioplatense → medir en el piloto (preguntas en inglés, conversación en español) y revisar los casos dudosos.
- Fijar versión del modelo (`jev-1.14.0`) y de preguntas para poder comparar corridas.

---

## 8. Esfuerzo estimado por etapas (sin envíos automáticos)

| Etapa | Contenido | Esfuerzo |
|---|---|---|
| 0. Hecho | Circuito, reglas, tests, datos sintéticos, planilla de revisión | — |
| 1. Datos reales | Adaptador para el exporte de Atom/HubSpot, anonimización, control de calidad | 2–4 días |
| 2. Categorías | Sesión con Alberto, ajuste de `reglas.py` y `preguntas.py`, etiquetado de ~100 casos | 2–3 días (+ tiempo de Ventas) |
| 3. Jev real | Corrida, análisis de desacuerdos, ajuste de state/preguntas (sin sobreajustar) | 3–5 días |
| 4. Borradores y plantillas | Claude con info aprobada, catálogo real de plantillas, revisión de Ventas | 3–4 días |
| 5. Informe y decisión | Métricas en conjunto de control, recomendación seguir/frenar | 1–2 días |
| 6. (Después) Asistente en vivo | Panel o integración de solo lectura con Atom para sugerir en tiempo real; el envío sigue siendo manual | a estimar tras el piloto |
