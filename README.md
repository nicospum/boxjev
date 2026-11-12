# JeVentas

Asistente interno para el equipo de Ventas de Don Box. Para cada consulta de WhatsApp:

1. **Jev (TypeSafe)** ubica al contacto en una de las **categorías que define Alberto** (primer contacto y después de 24 h) y responde preguntas puntuales: ¿dice la zona? ¿cuándo lo necesita? ¿pidió precio?
2. **El código** cruza las dos cosas: si las preguntas puntuales contradicen la categoría, marca el contacto para revisar. Después decide la acción de la categoría, siempre respetando la **ventana de 24 h**.
3. Con la ventana abierta, un **modelo de IA** (Claude, OpenAI, DeepSeek o Gemini) redacta un borrador; con la ventana cerrada, se recomienda una **plantilla aprobada**.
4. **Una persona revisa y envía.** Nada se envía solo; no se toca HubSpot ni Atom.

Diseño, métricas y riesgos: [docs/DISENO_PILOTO.md](docs/DISENO_PILOTO.md). Primera prueba con Jev real: [docs/PRUEBA_JEV_2026-11-05.md](docs/PRUEBA_JEV_2026-11-05.md). Formato de datos: [data/FORMATO_DE_ENTRADA.md](data/FORMATO_DE_ENTRADA.md).

## Abrir el panel

```bash
python scripts/abrir_panel.py
```

Se abre en `http://127.0.0.1:8765` y corre **solo en esta computadora**: claves y conversaciones reales no salen de acá, salvo lo que se envía (anonimizado) a Jev y al modelo de IA elegido.

### Primera vez: Ajustes

1. Activar **"Don Box aprobó enviar conversaciones anonimizadas"**. Sin esto, Jev real, los borradores con IA y el chat quedan apagados.
2. Clave de **TypeSafe** (si no está en la variable `TYPESAFE_API_KEY`).
3. Claves de los modelos de IA que se quieran usar y cuál usa el chat y cuál los borradores. Se usan **API keys** (pago por uso): las suscripciones como ChatGPT Plus o Claude Pro no se pueden conectar a apps propias.

Todo queda en `config/ajustes.local.json`, que no se sube a git. Las claves nunca vuelven al navegador.

### Secciones

- **Agregar lote** (botón amarillo): pegar conversaciones de 1 a 200 contactos, con «Cliente:» y «Ventas:» o copiadas de WhatsApp. Opcional: nombre a borrar, hace cuántas horas fue el último mensaje y el resultado si se conoce. Jev real o simulado.
- **Consultas:** lista filtrable por categoría, el chat y, al costado, la categoría, por qué, las probabilidades de Jev, los cuatro datos para cotizar, la sugerencia y "Tu revisión". Se puede **cambiar la categoría** a mano.
- **Categorías:** las dos etapas, quién está en cada categoría y su información. **Crear, editar y eliminar.** Al eliminar, Jev sugiere la mejor categoría restante para cada contacto que quedó suelto y Alberto **acepta o elige otra**. "Reclasificar este lote con Jev" vuelve a ubicar a todos después de editar descripciones (los cambios manuales se mantienen).
- **Resumen:** coincidencia con Ventas, distribución por categoría, acciones y cuántos alquilaron según cómo empezaron.
- **Importar:** archivos exportados (.txt de WhatsApp, CSV de mensajes, CSV de resultados con columnas `archivo` y `resultado`).
- **Asistente:** chat que maneja el panel con lenguaje natural: "¿cuántos hay en cada categoría?", "creá una categoría para los que quieren visitar la sede", "mostrame los que quieren reservar", "mové SIM-0003 a Lista para cotizar". Eliminar una categoría siempre pide confirmación con un botón. El asistente nunca escribe a clientes.

### Cómo escribir buenas categorías

Jev clasifica leyendo la descripción. Funciona mejor si cada una describe **una situación observable** ("el prospecto pregunta cómo pagar") y no mezcla dimensiones distintas: "Empresa" (qué necesita) compite con "Alta intención" (qué tan listo está), por eso "es empresa" se muestra como marca y no como categoría. Las condiciones dobles ("dice la zona **y** lo necesita pronto") son las que más confunden; para eso está el control cruzado con las preguntas puntuales.

## Demo en Netlify

`panel/static/` también es un sitio estático de solo lectura con datos inventados (https://boxjev.netlify.app). Para actualizar sus datos:

```bash
python scripts/exportar_demo.py jev_real_20 demo
```

El script se niega a exportar lotes con conversaciones reales.

## Línea de comandos

```bash
python scripts/generar_dataset.py --n 500
python scripts/correr_piloto.py --entrada data/sinteticas/consultas_500.jsonl --simular-plantillas --salida out/demo
python -m pytest -q
```

Con datos reales: `scripts/importar.py` (CSV o WhatsApp) y `scripts/correr_piloto.py --jev api --envio-externo-aprobado`.

## Estructura

```
config/       categorias.json (editable desde el panel), plantillas.json, info_comercial.json, ajustes.local.json (no se versiona)
data/         FORMATO_DE_ENTRADA.md, sinteticas/
docs/         DISENO_PILOTO.md, PRUEBA_JEV_2026-11-05.md
jeventas/     categorias, preguntas, jev, reglas, pipeline, ventana, estado, redactor, proveedores, asistente, ajustes, importar, corrida, evaluacion
panel/        servidor.py, acciones.py (operaciones compartidas por botones y chat), static/ (la página)
scripts/      abrir_panel, correr_piloto, importar, generar_dataset, exportar_demo
tests/
```

Por lote (`out/<lote>/`): `recomendaciones.jsonl` (lo que sugirió el sistema), `asignaciones.json` (cambios de categoría a mano), `reasignaciones.json` (sugerencias pendientes tras eliminar una categoría), `revisiones.json`, `payloads/` (lo que vio Jev, para repetir cualquier llamada).
