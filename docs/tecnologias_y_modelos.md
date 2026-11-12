# Tecnologías y elección de modelos

| Tecnología | Uso |
|---|---|
| Python | Implementación del agente y las herramientas |
| NVIDIA NIM | Modelo de lenguaje con function calling: `mistralai/mistral-large-4-1t-a52b` (Mistral Large 4; usado en toda la evaluación, probado el 2026-11-11; configurable con `NVIDIA_LLM_MODEL`) |
| NVIDIA NIM — embeddings | Representación vectorial de descripciones: `nvidia/nemotron-3.5-embed-1b` (2048 dimensiones; índice generado el 2026-11-11; configurable con `NVIDIA_EMBED_MODEL`). Requiere `input_type`: `passage` para el catálogo y `query` para las consultas |
| Cliente `openai` | Comunicación con la API compatible de NVIDIA NIM (`https://integrate.api.nvidia.com/v1`) |
| pandas / numpy | Lectura, limpieza y filtrado del catálogo; similitud coseno |
| Gradio | Interfaz conversacional y panel de trazabilidad |
| python-dotenv | Lectura de variables de entorno |
| Steam Games Dataset | Fuente del catálogo |

> **Elección de modelos (2026-11-11).** Los modelos previstos inicialmente ya no están disponibles: la API
> responde `410 Gone` con *"`meta/llama-3.3-70b-instruct` has reached its end of life on 2026-08-26"* y
> *"`nvidia/llama-3.2-nv-embedqa-1b-v2` … on 2026-05-18"*. Con la cuenta gratuita se probaron 16 modelos de
> lenguaje con una petición de function calling; 8 no están disponibles para la cuenta (404) y varios tardaron más
> de 60 s. Tres respondieron en ~3 s con una llamada válida y resolvieron el caso 1 completo con el catálogo de
> muestra (4/4 juegos correctos): `mistralai/mistral-large-4-1t-a52b` (elegido: respuesta más completa y sin
> afirmaciones sin respaldo), `nvidia/nemotron-3-ultra-550b-a55b` y `nvidia/nemotron-3.5-lightning-30b-a3b`. Para
> embeddings se eligió `nvidia/nemotron-3.5-embed-1b`. Cambiar de modelo solo requiere `NVIDIA_LLM_MODEL` /
> `NVIDIA_EMBED_MODEL` (al cambiar el de embeddings hay que regenerar el índice).

> Nota (2026-11-12): las cifras del sondeo de modelos (16 probados, 8 con 404, tiempos) se obtuvieron en ejecuciones reales durante el desarrollo, pero **sus salidas no se guardaron en `results/`**; por eso no se presentan como resultado comparativo en el README.

[← Volver al README](../README.md)
