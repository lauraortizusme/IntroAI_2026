"""Configuración central: rutas, modelos de NVIDIA NIM y límites del agente."""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv es opcional en entornos donde la clave ya está en el entorno
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODEL = os.getenv("NVIDIA_LLM_MODEL", "mistralai/mistral-large-4-1t-a52b")
EMBED_MODEL = os.getenv("NVIDIA_EMBED_MODEL", "nvidia/nemotron-3.5-embed-1b")

# Máximo de llamadas a herramientas por solicitud del usuario (ver README, sección 6).
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "5"))
# Turnos previos (usuario+asistente) que se reenvían al modelo como contexto.
MAX_HISTORY_TURNS = 6


class ConfigError(RuntimeError):
    """Falta alguna configuración necesaria (por ejemplo, la clave de la API)."""


def get_api_key() -> str:
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key or key == "tu_clave_aqui":
        raise ConfigError(
            "Falta NVIDIA_API_KEY. Crea un archivo .env a partir de .env.example "
            "(o, en Google Colab, agrega el secreto NVIDIA_API_KEY)."
        )
    return key


def default_catalog_path() -> Path:
    """Catálogo a usar: CATALOG_PATH > data/catalog.csv > data/sample_games.csv."""
    env = os.getenv("CATALOG_PATH")
    if env:
        return Path(env)
    full = DATA_DIR / "catalog.csv"
    return full if full.exists() else DATA_DIR / "sample_games.csv"


def embeddings_paths(catalog_path: Path) -> tuple[Path, Path]:
    """Archivos del índice de embeddings asociados a un catálogo."""
    stem = catalog_path.with_suffix("")
    return Path(f"{stem}.embeddings.npy"), Path(f"{stem}.embeddings.json")
