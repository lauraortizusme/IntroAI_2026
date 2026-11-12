"""Genera notebooks/steam_agent_colab.ipynb (ejecutar solo si se quiere modificar el notebook)."""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

OUT = Path(__file__).resolve().parent.parent / "notebooks" / "steam_agent_colab.ipynb"

CELLS: list[tuple[str, str]] = [
    ("md", """# Asistente conversacional para descubrir videojuegos (Colab)

Agente con herramientas sobre un catálogo de Steam. Este notebook instala las dependencias, configura
la clave de NVIDIA NIM desde los **secretos de Colab**, prueba el agente y abre la interfaz Gradio.

**Antes de empezar:** en Colab abre el panel de *Secretos* (icono de llave), crea `NVIDIA_API_KEY` con tu clave
y activa *Acceso desde el notebook*. **No pegues la clave en el código ni en las celdas.**"""),

    ("md", "## 1. Dependencias"),
    ("code", "%pip install -q \"openai>=1.40\" \"pandas>=2.0\" \"numpy>=1.24\" \"gradio>=4.44\" \"python-dotenv>=1.0\""),

    ("md", """## 2. Obtener el código del proyecto
Opción A: pon la URL de tu repositorio en `REPO_URL`. Opción B: déjala vacía y sube `steam-game-agent.zip` cuando se pida."""),
    ("code", '''import pathlib
import subprocess
import sys

REPO_URL = ""  # ← p. ej. "https://github.com/usuario/steam-game-agent"
PROJECT_DIR = pathlib.Path("/content/steam-game-agent")

if not PROJECT_DIR.exists():
    if REPO_URL:
        subprocess.run(["git", "clone", REPO_URL, str(PROJECT_DIR)], check=True)
    else:
        from google.colab import files

        print("Sube el archivo steam-game-agent.zip")
        uploaded = files.upload()
        zip_name = next(iter(uploaded))
        subprocess.run(["unzip", "-q", "-o", zip_name, "-d", "/content"], check=True)
        if not PROJECT_DIR.exists():
            raise FileNotFoundError("El zip debe contener la carpeta steam-game-agent/")

sys.path.insert(0, str(PROJECT_DIR / "src"))
print("Proyecto listo en", PROJECT_DIR)'''),

    ("md", "## 3. Clave de la API (secretos de Colab)"),
    ("code", '''import os

from google.colab import userdata

try:
    os.environ["NVIDIA_API_KEY"] = userdata.get("NVIDIA_API_KEY")
    print("Clave cargada desde los secretos de Colab.")
except Exception as exc:  # secreto inexistente o sin acceso desde el notebook
    raise RuntimeError("Crea el secreto NVIDIA_API_KEY y activa el acceso desde el notebook.") from exc'''),

    ("md", """## 4. Datos y embeddings

El repositorio **ya incluye** el catálogo real procesado (`data/catalog.csv`, 1.000 juegos) y su índice de
embeddings (`data/catalog.embeddings.npy` / `.json`, modelo `nvidia/nemotron-3.5-embed-1b`). Por eso las dos
opciones siguientes vienen en `False` y no hace falta descargar nada ni gastar créditos de NVIDIA.

**Cuándo poner `PREPARAR_CATALOGO_REAL = True`:** solo si quieres regenerar el catálogo desde el dataset
(p. ej., otra cantidad de juegos o una revisión nueva). `scripts/prepare_data.py` descarga el parquet de Hugging Face
(≈190 MB) y, como su columna `tags` viene vacía, también `games.csv` de la misma revisión (≈400 MB) para completar las
etiquetas. Tarda varios minutos. Un catálogo nuevo invalida el índice (que guarda el hash del CSV), así que esta
celda activa también `GENERAR_EMBEDDINGS`.

**Cuándo poner `GENERAR_EMBEDDINGS = True`:** si regeneraste el catálogo, si cambiaste `NVIDIA_EMBED_MODEL`, o si
usas el catálogo de muestra y quieres búsqueda semántica real (su índice incluido es un sustituto léxico). Usa la API
de NVIDIA NIM: unas 32 peticiones para 1.000 juegos."""),
    ("code", """PREPARAR_CATALOGO_REAL = False  # True = descargar y procesar Steam Games Dataset (parquet + games.csv)
GENERAR_EMBEDDINGS = False      # True = (re)calcular embeddings con NVIDIA NIM para el catálogo en uso

def run(*args):
    result = subprocess.run([sys.executable, *args], cwd=PROJECT_DIR, capture_output=True, text=True)
    print(result.stdout[-3000:])
    if result.returncode != 0:
        print(result.stderr[-3000:])
        raise RuntimeError("El comando falló; revisa el mensaje anterior.")

if PREPARAR_CATALOGO_REAL:
    run("-m", "pip", "install", "-q", "-r", "requirements-data.txt")
    run("scripts/prepare_data.py", "--n", "1000")
    if not GENERAR_EMBEDDINGS:
        print("El catálogo cambió: se regeneran también los embeddings (el índice anterior ya no coincide).")
        GENERAR_EMBEDDINGS = True

if GENERAR_EMBEDDINGS:
    run("scripts/build_embeddings.py", "--backend", "nim")

import json as _json

import config

catalogo = config.default_catalog_path()
_, meta_path = config.embeddings_paths(catalogo)
print("Catálogo en uso:", catalogo.name)
print("Modelo de lenguaje:", config.LLM_MODEL)
if meta_path.exists():
    meta = _json.loads(meta_path.read_text(encoding="utf-8"))
    print(f"Índice de embeddings: {meta['backend']} · {meta['model']} · {meta['n_items']} juegos")
else:
    print("No hay índice de embeddings para este catálogo: pon GENERAR_EMBEDDINGS = True.")"""),

    ("md", "## 5. Probar el agente sin interfaz (con traza)"),
    ("code", '''import json
from agent import build_agent

agent = build_agent()

def preguntar(texto):
    r = agent.run(texto)
    print(f"Respuesta:\\n{r.answer}\\n")
    print(f"Llamadas a herramientas: {r.tool_calls_used}/{r.max_tool_calls}" + ("  (límite alcanzado)" if r.limit_reached else ""))
    for t in r.trace:
        print(f"  #{t.n} {t.name} {'ok' if t.ok else 'ERROR'}  args={json.dumps(t.arguments, ensure_ascii=False)}")
    return r

_ = preguntar("Busca juegos relajantes por menos de 15 USD en Mac y calcula cuánto cuestan los dos primeros")'''),

    ("md", "## 6. Interfaz Gradio (conversación + traza de herramientas)"),
    ("code", '''from app import build_demo

demo = build_demo()
demo.launch(debug=True)'''),

    ("md", """## 7. Evaluación manual (opcional)
Ejecuta los 6 casos del README con el agente real y guarda la traza en `results/`. La valoración
(correcto / parcial / incorrecto) se completa a mano en el informe `.md` generado.

**Consume créditos de NVIDIA** (unas 15 peticiones). Con la cuenta gratuita, si aparece un error 429, espera un
minuto o ejecuta los casos por partes, p. ej. `run("scripts/run_evaluation.py", "--only", "1,2")`."""),
    ("code", '''run("scripts/run_evaluation.py")
print(sorted(p.name for p in (PROJECT_DIR / "results").glob("evaluacion_*")))'''),
]


def main() -> None:
    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "colab": {"provenance": []},
    }
    nb.cells = [
        nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src) for kind, src in CELLS
    ]
    nbf.validate(nb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, OUT)
    print(f"Notebook escrito en {OUT}")


if __name__ == "__main__":
    main()
