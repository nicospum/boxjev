# Primera prueba con Jev real — 05/11/2026

**Qué se probó:** 20 consultas sintéticas (inventadas, sin datos personales) de `data/sinteticas/consultas_500.jsonl`, 46 momentos de decisión, modelo `jev-1.14.0`, preguntas versión `2026-11-05.1`. Redactor offline, plantillas simuladas. Salida completa en `out/jev_real_20/`.

## Resultado técnico

- 46 llamadas, 0 errores. El formato de request/response funciona tal como está en `jeventas/jev.py`.
- ~100.500 tokens de entrada en total (~2.200 por llamada con 16 preguntas). Costo aproximado: USD 0,004.

## Calidad (con reservas)

- Coincidencia con la etiqueta simulada: 19/20 en primer contacto. El único desacuerdo (SIM-0013) es uno de los errores que el generador mete a propósito en las etiquetas; ahí Jev tiene razón según la definición.
- **Esto no mide la calidad real:** los mensajes sintéticos son prolijos y armados con frases fijas. Las conversaciones reales (audios, faltas de ortografía, mensajes cortados) van a ser más difíciles.

Lo que sí se ve:
- Entiende bien español rioplatense con preguntas en inglés.
- Asigna bien barrios a sedes: Munro → Saavedra, Devoto → Agronomía, Olivos y Belgrano → Núñez, San Fernando → Tigre, Caballito y Boedo → Almagro.
- Usa bien los datos del formulario (zona elegida) para "menciona ubicación".
- Urgencia: "mañana" ≈ 3, "semana que viene" ≈ 2,2, "fin de mes" ≈ 1,9, "dos meses" ≈ 1, sin fecha ≈ 0.
- En reactivaciones distingue "ya lo resolví" (desistió 0,9) de "sigo interesado" (desistió 0,02).

## Hallazgos y cambios

1. **Urgencia con dos picos (cambiado en código).** En SIM-0011 ("nos mudamos y el depto nuevo no está listo") Jev dio 67 % "inmediato" y 18 % "sin señal": el promedio (2,3) escondía la duda. Ahora `reglas.py` decide "pronto" con la probabilidad de los niveles 2 y 3 (≥ 0,7), no con el promedio. Re-aplicado sobre las respuestas guardadas: no cambia ningún segmento de estas 20.
2. **"Qué guarda" vs. "para qué" (a decidir con Alberto).** "Sería para guardar muebles de un monoambiente" se lee como motivo (0,88–0,92) y como necesidad "espacio extra". ¿Para Ventas eso es un motivo? Si no, aclarar el criterio `false` de `dice_motivo` en `preguntas.py` y medir en casos nuevos.
3. **"Lo pienso y te aviso" (a decidir con Alberto).** Hoy, al cerrar la ventana se recomienda la plantilla "retomar más adelante" a las 24 h. Probablemente convenga esperar unos días. Definir cuántos.
4. Las preguntas sobre la conversación miran todo el historial: en SIM-0002 "pidió tiempo" sigue alto (0,85) después de "ya lo resolví". No es un problema porque las reglas evalúan "desistió" primero, pero hay que tenerlo en cuenta si se cambia el orden.

## Próximo paso

Repetir con conversaciones reales anonimizadas y etiquetas de Alberto, guardando un 30 % sin mirar para medir.
