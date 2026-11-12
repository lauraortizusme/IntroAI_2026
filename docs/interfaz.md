# Interfaz

Interfaz web en Gradio (`src/app.py`), ejecutable localmente o en Google Colab. Tiene dos áreas principales:

- **Conversación:** historial de mensajes, campo para escribir solicitudes, botones de envío y de limpieza, y ejemplos de consultas.
- **Traza de herramientas:** lista de llamadas realizadas (desplegables con argumentos y resultados en JSON), estado ✓/✗ de cada una, duración y contador de llamadas respecto al máximo permitido.

La respuesta presenta los juegos recomendados como lista con nombre, precio, sistemas operativos y géneros. La traza permite consultar los argumentos y resultados de cada llamada, sin
ocultar los casos en los que no hubo resultados o se produjo un error, y muestra una advertencia cuando se alcanza el límite. Si falta la clave de la API, la interfaz abre igualmente y avisa en el chat.

## Google Colab

`notebooks/steam_agent_colab.ipynb` (generado por `scripts/make_notebook.py`) instala dependencias, clona la rama `proyecto-final-videojuegos` (o pide un zip si `REPO_URL` está vacía), lee la clave desde los secretos de Colab, usa el catálogo e índice incluidos (regenerarlos es opcional: `PREPARAR_CATALOGO_REAL` y `GENERAR_EMBEDDINGS` valen `False` por defecto), prueba el agente y lanza Gradio.

**Ejecución en Colab (2026-11-12).** Funcionaron:

- la instalación de dependencias;
- la lectura de la clave desde los secretos;
- el clonado de la rama;
- la prueba del agente;
- la interfaz Gradio.

Hubo `APITimeoutError` intermitentes de la API de NVIDIA, en la primera consulta del agente y en una consulta desde
Gradio, y en ambos casos el reintento funcionó. La latencia no se midió.

**No se ejecutaron en Colab:**

- la sección de evaluación;
- la preparación del catálogo (`PREPARAR_CATALOGO_REAL` y `GENERAR_EMBEDDINGS` se dejaron en `False`);
- la subida del zip, porque se usó el clonado.

Además, las pruebas automatizadas comprueban que el notebook está sincronizado con su generador y que sus celdas de
código son sintácticamente válidas.

[← Volver al README](../README.md)
