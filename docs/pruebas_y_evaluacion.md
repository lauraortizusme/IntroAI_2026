# Pruebas y evaluación: detalle

## Pruebas automatizadas (no requieren clave ni red)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

**115 pruebas, todas pasan** (última ejecución: 2026-11-12). Cubren: filtros y su verificación, orden por relevancia
de etiquetas con la popularidad como desempate, búsqueda semántica con filtros obligatorios, fichas, totales (incluidos
títulos inexistentes y aritmética en centavos), validación de argumentos y errores controlados, ciclo del agente con un
modelo simulado (traza, argumentos inválidos, límite de cinco llamadas, llamadas en paralelo que lo exceden, errores de
red), formato exacto de las peticiones de embeddings a NVIDIA NIM, integridad del índice, preparación de datos con un
archivo crudo sintético de 41 columnas (incluida la recuperación de etiquetas desde `games.csv` con su cabecera
desalineada, también para archivos locales, y la conservación de apóstrofos como en *Beat 'em up*), la interfaz
Gradio, el script de evaluación (incluidos el recálculo de chequeos sin llamar a la API, la línea base sin herramientas con un modelo simulado y las métricas comparables) y el notebook de Colab
(sincronizado con su generador, celdas de código sintácticamente válidas y sin descargas por defecto).

**Qué NO demuestran:** el comportamiento del modelo de lenguaje real. Con un modelo simulado se comprueba que la
aplicación ejecuta y registra correctamente lo que el modelo pide, no que el modelo elija bien las herramientas.
Eso lo mide la evaluación manual siguiente.

## Evaluación manual con el modelo real

La evaluación es manual. En cada caso se comparó la respuesta con el catálogo y con los resultados de las
herramientas: si la herramienta seleccionada fue adecuada, si sus argumentos representan la solicitud y si la
respuesta final coincide con los datos devueltos.

| # | Categoría | Solicitud | Resultado esperado |
|---|---|---|---|
| 1 | Habitual: filtros | «Un shooter cooperativo por menos de 10 USD» | Los resultados cumplen los filtros disponibles en el catálogo. |
| 2 | Habitual: semántica | «Quiero algo para relajarme» | Las recomendaciones son coherentes con la descripción y aparecen en los resultados de la herramienta. |
| 3 | Habitual: combinada | «Recomiéndame tres juegos de granja y dime cuánto cuestan juntos» | Se identifican los juegos y el total coincide con la suma de sus precios en el catálogo. |
| 4 | Consulta que requiere herramienta | «¿En qué sistemas operativos funciona [juego del catálogo] y cuánto cuesta?» | La ficha coincide con los datos del catálogo. |
| 5 | Caso límite | «¿Cuánto cuesta [título que no está en el catálogo]?» | El agente reconoce que no encuentra el título y no inventa información. |
| 6 | Prueba adicional: límite de llamadas | Solicitud que provoque más de cinco llamadas | El agente responde con lo reunido e informa que la búsqueda quedó incompleta. |

Para ejecutarlos todos con el agente real y guardar la evidencia:

```bash
python scripts/run_evaluation.py              # o: --only 3,5
python scripts/run_evaluation.py --recheck results/evaluacion_<fecha>.json   # recalcula chequeos, sin API
```

El script sustituye los marcadores (caso 4: el juego con más reseñas del catálogo; caso 5: un título inventado que
verifica que no exista; caso 6: pedir siete fichas por separado), guarda la traza completa en
`results/evaluacion_<fecha>.json` y genera `results/evaluacion_<fecha>.md` con la respuesta, las herramientas
llamadas, sus argumentos y unos chequeos objetivos de apoyo (títulos mencionados sin respaldo en las herramientas,
coincidencia del total, etc.). **La valoración queda en blanco para completarla a mano.**

Para cada caso se registran la respuesta obtenida, las herramientas llamadas con sus argumentos y una valoración
(**correcto, parcial o incorrecto**) con su justificación. La traza completa (incluidos los resultados de cada
llamada) se incluye para los casos 3 y 6 en el anexo enlazado abajo.

### Resultados (2026-11-11 · `mistralai/mistral-large-4-1t-a52b` · catálogo real de 1.000 juegos · máximo 5 llamadas)

Evidencia: [`results/evaluacion_20261111_172348.md`](../results/evaluacion_20261111_172348.md) (los seis casos),
[`results/evaluacion_20261111_173037.md`](../results/evaluacion_20261111_173037.md) y
[`results/evaluacion_20261111_174341.md`](../results/evaluacion_20261111_174341.md) (casos 1 y 3 repetidos con el código
final, tras la mejora descrita en el análisis; la ejecución de los seis casos queda como evidencia «antes») y
[`results/evaluacion_20261111_173115.md`](../results/evaluacion_20261111_173115.md) (caso 6 con `MAX_TOOL_CALLS=2`).
**Trazas completas** (herramienta, argumentos y resultado de cada llamada) del caso 3 (antes y después) y del caso 6:
[`results/anexo_trazas_casos_3_y_6.md`](../results/anexo_trazas_casos_3_y_6.md). Cada respuesta se contrastó con los
resultados de las herramientas y con `data/catalog.csv`. Los chequeos automáticos se recalcularon tras corregir dos
falsos positivos del script (un título contenido en otro más largo, «Counter-Strike» dentro de «Counter-Strike 2», y
un título que es una palabra común, «UNO» en «cada uno»); los chequeos originales se conservan en el JSON.

| # | Herramientas (argumentos) → respuesta | Valoración | Justificación |
|---|---|---|---|
| 1 | `buscar_juegos {tags: [Shooter, Co-op], precio_max: 10, limite: 10}` → 10 de 125 coincidencias. Responde con los 10: Left 4 Dead 2, PAYDAY 2, Rainbow Six Siege X, Counter-Strike 2, Team Fortress 2, PUBG, Apex Legends, Warframe, Garry's Mod y GTA V Legacy. | **Correcto** | Los 10 títulos están en el resultado de la herramienta y cumplen los filtros; precios y sistemas coinciden con el catálogo. El modelo separó por su cuenta los tres «con modo cooperativo real». Citó «Left 4 Dead» (como ejemplo de estilo) **sin respaldo en las herramientas**. GTA V Legacy aparece «Gratis» porque el dataset le asigna precio 0 (posible error de datos de la fuente). Ver el análisis (antes y después). |
| 2 | `buscar_similares {descripcion: "relaxing cozy peaceful game to unwind and de-stress, calm atmosphere, no pressure, soothing gameplay", k: 8}` → recomienda Tiny Glade, Dorfromantik, Journey, Unpacking, PowerWash Simulator y Spiritfarer. | **Correcto** | Los seis están entre los ocho resultados, con precio y sistemas exactos. Redactó la consulta en inglés, como indica el esquema. Advirtió que dos resultados no encajaban: MiSide (terror psicológico) y Leaf Blower Revolution (idle). |
| 3 (antes) | `buscar_juegos {tags: [Farming Sim], limite: 3}` → `buscar_juegos {tags: [Farming Sim, Agriculture], limite: 10}` → `calcular_total {nombres: [Stardew Valley, Farm Together, Fields of Mistria]}` → total 26,17 USD. | **Correcto** | 8,99 + 5,99 + 11,19 = 26,17 USD, igual en la herramienta, la respuesta y el catálogo. Los detalles de cada juego están respaldados por sus etiquetas (p. ej., *Early Access* y *Dating Sim* en Fields of Mistria). Hizo una búsqueda de más: la primera devolvió DAVE THE DIVER entre los tres primeros (orden solo por popularidad) y el modelo buscó otra vez. Traza completa en el anexo. |
| 3 (después) | `buscar_juegos {tags: [Farming Sim], limite: 3}` → `calcular_total {nombres: [Stardew Valley, Farming Simulator 22, Farming Simulator 19]}` → total 46,97 USD. | **Correcto** | Con el orden nuevo, los tres primeros de los 23 juegos con *Farming Sim* tienen la etiqueta en la 1.ª o 2.ª posición; el modelo los usó directamente (2 llamadas en lugar de 3). 8,99 + 19,99 + 17,99 = 46,97 USD coincide con la herramienta, la respuesta y el catálogo, al igual que los sistemas operativos. Dos de los tres son de la misma saga (*Farming Simulator*), lo que da poca diversidad a la recomendación; no se considera un error, porque los tres cumplen lo pedido. Traza completa en el anexo. |
| 4 | `detalle_juego {nombre: "Counter-Strike 2"}` → 0 USD (gratuito); Windows y Linux, sin macOS. | **Correcto** | Coincide con la ficha del catálogo, incluidos la fecha (2012-08-21) y el 86,7 % de reseñas positivas. |
| 5 | `detalle_juego {nombre: "Zorblax Prime Odyssey"}` → «no está en el catálogo… no puedo darte su precio». | **Correcto** | La herramienta no lo encontró y el agente no inventó precio ni datos; ofreció buscar alternativas. |
| 6 | `detalle_juego` × 5 (Counter-Strike 2, Dota 2, GTA V Legacy, PUBG, Terraria) → sistemas de los cinco y «⚠️ Búsqueda incompleta» con los dos títulos no consultados. | **Correcto** (con matiz) | Los cinco resultados son correctos y nombra los pendientes (Rainbow Six Siege X y Garry's Mod) sin dar datos de ellos. **Matiz: el límite de la aplicación no se activó con el modelo real** (`limite_alcanzado: false`): el modelo, informado del máximo en el prompt, se detuvo en la quinta llamada sin pedir una sexta, de modo que el rechazo de la llamada excedente y la consulta final sin herramientas no llegaron a ejecutarse. Con `MAX_TOOL_CALLS=2` ocurrió lo mismo (dos llamadas, cinco títulos pendientes). Ese mecanismo solo está verificado con el modelo simulado. Traza completa en el anexo. |

## Análisis de resultados

**Limitación observada (caso 1): el orden por popularidad favorecía etiquetas poco representativas.** En el dataset,
cada juego tiene hasta 20 etiquetas ordenadas por votos de los usuarios. `buscar_juegos` aceptaba una etiqueta en
cualquier posición y ordenaba solo por reseñas, así que de los 10 juegos devueltos para «shooter cooperativo», **8 tenían
`Co-op` entre las posiciones 11 y 15** (Counter-Strike 2, PUBG, Apex Legends, Team Fortress 2, Warframe…): shooters
competitivos gratuitos muy populares. Solo Left 4 Dead 2 (2.ª) y PAYDAY 2 (1.ª) son cooperativos en sentido estricto.
El efecto fue una recomendación técnicamente correcta (todos cumplen los filtros) pero poco útil; el modelo lo compensó
separando por su cuenta los «cooperativos reales», algo que no se puede garantizar en otras consultas.

**Mejora aplicada:** ordenar primero por relevancia de las etiquetas pedidas (todas entre las 5 más votadas, luego entre
las 10, luego el resto) y usar la popularidad solo como desempate (`Catalog.tag_tier`, con 3 pruebas nuevas). Al repetir
el caso 1 ([evidencia](../results/evaluacion_20261111_173037.md)), los 10 resultados tienen `Co-op` entre las posiciones 1 y
6: Left 4 Dead 2, Borderlands 2, Ghost Recon Wildlands, Verdun, Sven Co-op, Ghost Recon Breakpoint, Borderlands GOTY,
Aliens: Fireteam Elite, PAYDAY 2 y Unturned, todos con precio y sistemas correctos y sin títulos sin respaldo.
En el caso 3, la primera búsqueda ya devolvió tres juegos de granja propiamente dichos (antes aparecía DAVE THE DIVER,
con *Farming Sim* lejos de las primeras etiquetas) y el agente resolvió la tarea con una llamada menos.
Queda como limitación que los umbrales (5 y 10) son arbitrarios y que el modelo presentó la lista como «los mejor
valorados», aunque el orden ya no es solo por valoración. Una mejora adicional sería usar la categoría oficial de Steam
(columna `categories`: *Co-op*, *Online Co-op*), que no depende de los votos de los usuarios.

**Otra observación:** en el caso 6, el modelo respeta el límite por planificación propia (ver el matiz de la tabla), por
lo que la protección de la aplicación no se ejercitó con el modelo real.

## Limitaciones y mejoras posibles

| Limitación | Mejora posible |
|---|---|
| Las descripciones están en inglés y las solicitudes pueden estar en español. | Mitigado: el modelo redacta la consulta semántica en inglés (así lo hizo en el caso 2). En una prueba directa, la consulta en español «un juego de granja tranquilo para jugar con amigos» devolvió cinco juegos de granja, pero las consultas vagas («algo relajante para desconectar») dieron similitudes bajas (≈0,19) y algún resultado poco afín. Mejora: traducir la consulta antes de buscar o indexar descripciones traducidas. |
| Las etiquetas de Steam no siempre representan las preferencias expresadas por el usuario. | Combinar filtros con búsqueda semántica y normalizar etiquetas. |
| El modelo puede seleccionar una herramienta poco adecuada. | Mejorar las descripciones de las funciones e incorporar ejemplos al prompt. |
| El catálogo contiene un número limitado de juegos. | Ampliar el conjunto de datos o utilizar una fuente actualizable. |
| Los datos corresponden a una captura fija. | Actualizar periódicamente el catálogo. |
| Los títulos se buscan por coincidencia exacta; una errata obliga a una segunda llamada (con sugerencias). | Aceptar coincidencias aproximadas solo cuando sean únicas y muy cercanas. |
| El índice de muestra usa un sustituto léxico (no semántico). | Regenerarlo con NVIDIA NIM (`scripts/build_embeddings.py`). |
| Los modelos del catálogo gratuito de NVIDIA pueden retirarse sin aviso: ya ocurrió con los dos modelos previstos (`410 Gone` para `meta/llama-3.3-70b-instruct` y `nvidia/llama-3.2-nv-embedqa-1b-v2`), y otros 8 modelos probados no estaban disponibles para la cuenta (404). | Los modelos se configuran con `NVIDIA_LLM_MODEL` / `NVIDIA_EMBED_MODEL` sin tocar código; antes de cada entrega, verificar con `python scripts/run_evaluation.py --only 1`. Si cambia el modelo de embeddings, hay que regenerar el índice. |
| El precio es el de la fecha de recolección, con el descuento vigente entonces, y hay valores dudosos en la fuente (GTA V Legacy a 0 USD). | El agente ya advierte que los precios pueden diferir de los actuales; actualizar el catálogo periódicamente. |
| El modelo respeta el límite de llamadas por planificación propia, así que el mecanismo de corte de la aplicación no se ejercitó con el modelo real. | Añadir un caso de evaluación que obligue a exceder el límite en una sola respuesta (llamadas en paralelo) o quitar el máximo del prompt en esa prueba. |

[← Volver al README](../README.md)
