"""El notebook de Colab se genera con scripts/make_notebook.py: comprueba que está sincronizado con su
generador, que sus celdas de código son Python válido y que no gasta créditos ni descarga datos por defecto.

No ejecuta el notebook (requiere Colab, sus secretos y la API de NVIDIA)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import nbformat

import make_notebook

NB = Path(__file__).resolve().parent.parent / "notebooks" / "steam_agent_colab.ipynb"


def code_cells() -> list[str]:
    return [c.source for c in nbformat.read(NB, as_version=4).cells if c.cell_type == "code"]


def test_notebook_sincronizado_con_su_generador():
    esperado = [src for kind, src in make_notebook.CELLS if kind == "code"]
    assert code_cells() == esperado, "Ejecuta: python scripts/make_notebook.py"


def test_celdas_de_codigo_son_python_valido():
    for src in code_cells():
        # Las «magics» de IPython (%pip, !cmd) no son Python: se sustituyen por `pass` con la misma sangría.
        py = re.sub(r"^(\s*)[%!].*$", r"\1pass", src, flags=re.M)
        ast.parse(py)


def test_por_defecto_no_descarga_datos_ni_regenera_embeddings():
    datos = next(src for src in code_cells() if "PREPARAR_CATALOGO_REAL" in src)
    assert re.search(r"^PREPARAR_CATALOGO_REAL = False", datos, flags=re.M)
    assert re.search(r"^GENERAR_EMBEDDINGS = False", datos, flags=re.M)
    assert "requirements-data.txt" in datos  # datasets + pyarrow, igual que en local


def test_clona_la_rama_del_proyecto_o_pide_el_zip():
    celda = next(src for src in code_cells() if "REPO_URL" in src)
    assert re.search(r'^REPO_BRANCH = "proyecto-final-videojuegos"$', celda, flags=re.M)
    assert '["git", "clone", "-b", REPO_BRANCH, REPO_URL, str(PROJECT_DIR)]' in celda
    # Sin REPO_URL se mantiene la alternativa de subir el zip.
    assert re.search(r"if REPO_URL:.*else:.*files\.upload\(\)", celda, flags=re.S)


def test_la_clave_no_se_escribe_en_el_notebook():
    assert "nvapi-" not in NB.read_text(encoding="utf-8")
    assert any('userdata.get("NVIDIA_API_KEY")' in src for src in code_cells())  # la clave sale de los secretos
