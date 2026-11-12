# Formato de entrada

No sabemos todavía cómo exportan Atom y HubSpot. Por eso el sistema trabaja con **un formato propio** (JSONL, una consulta por línea) y hay adaptadores para convertir lo que llegue. Cuando tengamos un exporte real, se agrega o ajusta un adaptador en `jeventas/importar.py`; el resto no cambia.

## Formato canónico (JSONL)

```json
{
  "id_consulta": "C-3f9a1b2c4d",
  "canal": "whatsapp",
  "origen": {"fuente": "PAID_SOCIAL", "campania": "meta_mudanzas_2026q2"},
  "propiedades": {"zona_formulario": "Palermo", "motivo_formulario": "Mudanza"},
  "mensajes": [
    {"ts": "2026-05-04T10:00:00", "autor": "cliente", "texto": "Hola, me mudo...", "tipo": "texto"},
    {"ts": "2026-05-04T10:20:00", "autor": "ventas",  "texto": "¡Hola! ...",       "tipo": "texto"},
    {"ts": "2026-05-05T12:00:00", "autor": "ventas",  "texto": "Hola, ...",        "tipo": "plantilla", "plantilla_id": "seguimiento_cotizacion_v1"}
  ],
  "resultado": {"estado": "alquilo"},
  "etiqueta_ventas": {"segmento": "alta_intencion", "revisado_por": "Alberto"}
}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `id_consulta` | sí | Código anónimo. Nunca el teléfono. |
| `mensajes[].ts` | sí | Fecha y hora (hora de Argentina). Es la base de la ventana de 24 h. |
| `mensajes[].autor` | sí | `cliente`, `ventas` o `sistema` (respuestas automáticas/bots: **no** renuevan la ventana). |
| `mensajes[].tipo` | no | `texto`, `plantilla`, `audio`, `imagen`, `documento`. |
| `mensajes[].plantilla_id` | si es plantilla | Nombre de la plantilla usada. |
| `propiedades` | no | Solo propiedades de HubSpot **conocidas al primer contacto** (zona, sede, tamaño, motivo, tipo de cliente del formulario). No incluir nombre, teléfono, email ni etapas posteriores del negocio. |
| `origen` | no | Fuente y campaña. |
| `resultado.estado` | no | `alquilo`, `no_alquilo`, `desconocido`. Se usa solo para evaluar, nunca se le muestra a Jev. |
| `etiqueta_ventas.segmento` | para evaluar | Clasificación hecha por Ventas al revisar el primer contacto. |

## Exportes soportados hoy

**1. CSV de mensajes** (una fila por mensaje) + CSV opcional de consultas.

Columnas reconocidas (se acepta cualquiera de los alias):

| Lógico | Alias |
|---|---|
| id de conversación | `id_consulta`, `conversation_id`, `chat_id`, `ticket_id`, `id` |
| fecha/hora | `fecha_hora`, `timestamp`, `fecha`, `created_at`, `sent_at` |
| autor | `autor`, `direction` (`inbound`/`outbound`), `sender_type`, `remitente` |
| texto | `texto`, `mensaje`, `message`, `body`, `text` |
| plantilla | `plantilla_id`, `template_name`, `template` |

CSV de consultas: `id_consulta` + propiedades + `resultado` (+ `fuente`, `campania`). Las columnas `nombre`, `telefono`, `email`, `dni`, `cuit` se descartan.

```bash
python scripts/importar.py csv --mensajes export/mensajes.csv --consultas export/consultas.csv --salida data/reales/consultas.jsonl
```

**2. Chats de WhatsApp exportados (.txt)**, uno por archivo, formato Android o iPhone:

```bash
python scripts/importar.py whatsapp --carpeta export/chats --ventas "Don Box" "Don Box Ventas" --salida data/reales/whatsapp.jsonl
```

En ambos casos se anonimiza por defecto: teléfonos, emails, DNI/CUIT y nombres del contacto se reemplazan; el id se convierte en un código (`C-…`) con una "sal" que hay que guardar aparte si se quiere volver a vincular con HubSpot.

## Qué hay que pedir a Marketing/Operación

1. Un exporte de solo lectura de 100–200 conversaciones antiguas (mezcla de casos que alquilaron y que no), con **todos** los mensajes y su fecha/hora, incluidos los de Ventas y las plantillas.
2. Para cada conversación: zona/sede y propiedades del formulario **tal como estaban al primer contacto**, y el resultado conocido.
3. El listado de plantillas aprobadas en Meta: nombre, texto, estado, fecha de aprobación/vigencia y uso previsto.
4. Una muestra de 5 conversaciones crudas tal como salen de Atom, para escribir el adaptador exacto.
