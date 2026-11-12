# JeVentas

Asistente interno para el equipo de Ventas de Don Box. Para cada consulta de WhatsApp:

1. **Jev (TypeSafe)** responde preguntas simples sobre la conversación: ¿dice la zona? ¿cuándo lo necesita? ¿pidió precio?
2. **El código** combina esas respuestas en un segmento (alta intención, para cotizar, exploratoria, información insuficiente, etc.) y decide el próximo paso.
3. Si la **ventana de 24 h** está abierta, **otro modelo (Claude)** redacta un borrador de respuesta.
4. Si está cerrada, recomienda una **plantilla aprobada y vigente**, elegida según el segmento.
5. **Una persona revisa y envía.** Nada se envía solo; no se toca HubSpot ni Atom.

Diseño completo, categorías, métricas, riesgos y esfuerzo: [docs/DISENO_PILOTO.md](docs/DISENO_PILOTO.md).
Formato de datos y qué pedir a Marketing: [data/FORMATO_DE_ENTRADA.md](data/FORMATO_DE_ENTRADA.md).

## Estado

| Pieza | Estado |
|---|---|
| Circuito completo (ventana, state, Jev, reglas, borrador, plantillas, evaluación) | Funciona, 24 pruebas |
| Datos | 500 consultas **sintéticas** (`data/sinteticas/`). Faltan los exportes reales |
| Jev | **Simulado** por defecto. El real está listo pero bloqueado hasta tener aprobación de Don Box |
| Plantillas | **Ejemplos** en `config/plantillas.json`. Falta el listado aprobado |
| Info comercial | Precargada del FAQ en `config/info_comercial.json`, sin validar |
| Categorías | Propuesta en `jeventas/reglas.py`, para validar con Alberto |

## El panel

Una página para ver cada consulta como un chat, qué leyó el sistema, qué sugiere y para marcar si está bien.

```bash
python scripts/abrir_panel.py
```

Se abre en `http://127.0.0.1:8765` y funciona solo en esta computadora. Tiene tres secciones:

- **Consultas:** lista filtrable, el chat y, al costado, la clasificación, los cuatro datos para cotizar (zona, qué guarda, cuándo, para qué), la sugerencia y "Tu revisión". En el chat, lo que pasó después de cada sugerencia se ve atenuado: el sistema no lo veía. Las flechas ↑ ↓ mueven entre consultas.
- **Resumen:** coincidencia con Ventas, dónde se equivoca, qué sugirió y cuántos alquilaron según cómo empezaron.
- **Importar:** arrastrar chats de WhatsApp (.txt) o CSV exportados. Borra teléfonos, emails y nombres, analiza y crea un lote nuevo.

### Probar con conversaciones viejas cuyo resultado ya se conoce

1. Exportar los chats de WhatsApp (uno por archivo .txt) o el CSV de mensajes de Atom.
2. Armar un `resultados.csv` con las columnas `archivo` (nombre del .txt) y `resultado` (`alquiló`, `no alquiló` o `desconocido`). Opcional: `zona_formulario`, `campania`.
3. En el panel, Importar: subir los .txt y el CSV juntos y elegir Jev simulado para una primera prueba. Usar Jev real solo con aprobación de Don Box.
4. Alberto revisa en Consultas; el Resumen muestra los resultados.

Esto se hace **solo en el panel local**: las conversaciones reales nunca van a la demo pública.

### Demo en Netlify

`panel/static/` también funciona como sitio estático: si no encuentra el servidor, lee los lotes de `panel/static/datos/` y guarda las revisiones en el navegador. `netlify.toml` ya publica esa carpeta, sin paso de build. Para actualizarla:

```bash
python scripts/exportar_demo.py jev_real_20 demo
```

El script se niega a exportar lotes con conversaciones que no sean inventadas.

## Uso por línea de comandos

Requiere Python 3.10+. Sin dependencias para el modo local; `anthropic` solo para borradores con Claude.

```bash
# 1. Generar consultas de prueba
python scripts/generar_dataset.py --n 500

# 2. Correr la prueba retrospectiva, todo local
python scripts/correr_piloto.py --entrada data/sinteticas/consultas_500.jsonl --simular-plantillas --salida out/demo

# 3. Tests
python -m pytest -q
```

Con datos reales (cuando lleguen y con aprobación):

```bash
python scripts/importar.py csv --mensajes export/mensajes.csv --consultas export/consultas.csv --salida data/reales/consultas.jsonl
python scripts/correr_piloto.py --entrada data/reales/consultas.jsonl --jev api --envio-externo-aprobado --limite 20
```

`--jev api` usa `TYPESAFE_API_KEY`; `--redactor claude` usa las credenciales de Anthropic del entorno.

## Qué produce cada corrida (`out/<carpeta>/`)

| Archivo | Para quién | Contenido |
|---|---|---|
| `informe.md` | Equipo | Acuerdo con Ventas, matriz de confusión, acciones, plantillas, resultado por segmento |
| `revision_ventas.csv` | Alberto / Ventas | Una fila por recomendación, con columnas `REV_…` para calificar segmento, borrador y plantilla |
| `recomendaciones.jsonl` | Análisis | Salida completa: clasificación, señales con probabilidad, acción, datos usados, lo que pasó después |
| `payloads/` | Auditoría | State y respuestas de Jev de cada llamada, para repetirla |
| `metricas.json` | Análisis | Métricas en crudo |

> Los resultados con Jev simulado y datos sintéticos solo prueban que el circuito funciona. No dicen nada sobre la calidad de Jev.

## Estructura

```
config/       info_comercial.json, plantillas.json
data/         FORMATO_DE_ENTRADA.md, sinteticas/ (reales/ no se versiona)
docs/         DISENO_PILOTO.md, PRUEBA_JEV_2026-11-05.md
jeventas/     modelo, importar, ventana, estado, preguntas, jev, reglas, redactor, plantillas, pipeline, corrida, evaluacion
panel/        servidor.py (local) y static/ (la página; también es la demo de Netlify)
scripts/      generar_dataset, importar, correr_piloto, abrir_panel, exportar_demo
tests/
```

Dónde cambiar cada cosa: preguntas a Jev → `jeventas/preguntas.py` (subir `VERSION_PREGUNTAS`); categorías y umbrales → `jeventas/reglas.py`; plantillas → `config/plantillas.json`; info para borradores → `config/info_comercial.json`.
