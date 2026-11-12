"""Embeddings de las descripciones y búsqueda por similitud (herramienta ``buscar_similares``).

Hay dos implementaciones de ``Embedder``:

* ``NimEmbedder``: usa NVIDIA NIM mediante el cliente ``openai`` (la que se usa en la entrega).
* ``HashEmbedder``: bolsa de palabras con "hashing trick", sin red ni claves. Es un doble de
  pruebas para desarrollar y ejecutar los tests sin API: solo capta coincidencias de palabras,
  NO similitud semántica real. No debe usarse para evaluar el sistema.

El índice guarda junto a la matriz un JSON con el backend, el modelo y un hash del catálogo, y
se rechaza si no coincide con el catálogo cargado: así nunca se mezclan vectores de modelos o
de catálogos distintos.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import numpy as np

import config
from catalog import Catalog

MAX_TEXT_CHARS = 1500  # cada texto se recorta antes de enviarlo al modelo de embeddings


class IndexError_(RuntimeError):
    """El índice de embeddings no existe, está corrupto o no corresponde al catálogo."""


class Embedder(Protocol):
    backend: str
    model: str

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _l2_normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


# ----------------------------------------------------------------------- NVIDIA NIM
class NimEmbedder:
    """Embeddings asimétricos de NVIDIA NIM: 'passage' para documentos y 'query' para consultas."""

    backend = "nim"

    def __init__(self, client=None, model: str | None = None, batch_size: int = 32):
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=config.get_api_key(), max_retries=5)
        self.client = client
        self.model = model or config.EMBED_MODEL
        self.batch_size = batch_size

    def _embed(self, texts: list[str], input_type: str) -> np.ndarray:
        resp = self.client.embeddings.create(
            model=self.model,
            input=[t[:MAX_TEXT_CHARS] for t in texts],
            encoding_format="float",
            extra_body={"input_type": input_type},  # parámetro propio de NIM, no existe en la API de OpenAI
        )
        data = sorted(resp.data, key=lambda d: d.index)
        return np.array([d.embedding for d in data], dtype=np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        parts = []
        for start in range(0, len(texts), self.batch_size):
            parts.append(self._embed(texts[start : start + self.batch_size], "passage"))
            time.sleep(0.2)  # margen frente a límites de tasa
        return _l2_normalize(np.vstack(parts))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2_normalize(self._embed([text], "query"))[0]


# ------------------------------------------------------------------ doble de pruebas
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have in into is it its of on or that the their "
    "this to was were will with you your can all not very more most some any other than then so "
    "up out over just one two three four each every while where when who whom what which also "
    "game games play player players like want looking something".split()
)
_SYNONYMS = {
    "cooperative": "coop", "cooperation": "coop", "friends": "friend", "chill": "relax",
    "calm": "relax", "peaceful": "relax", "soothing": "relax", "tranquil": "relax",
    "cozy": "relax", "cosy": "relax", "relaxed": "relax", "laidback": "relax",
    "gentle": "relax", "zen": "relax", "farm": "farm", "farms": "farm", "crops": "farm",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower().replace("co-op", "coop").replace("co op", "coop")
    out = []
    for tok in re.findall(r"[a-z0-9]+", text):
        if tok in _STOPWORDS:
            continue
        tok = _SYNONYMS.get(tok, tok)
        if len(tok) > 5 and tok.endswith("ing"):
            tok = tok[:-3]
        elif len(tok) > 4 and tok.endswith("es"):
            tok = tok[:-2]
        elif len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        out.append(tok)
    return out


class HashEmbedder:
    backend = "hash"
    model = "hashing-bow-512"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in _tokenize(text):
            b = tok.encode()
            sign = 1.0 if zlib.crc32(b"s:" + b) & 1 else -1.0
            v[zlib.crc32(b) % self.dim] += sign
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _l2_normalize(np.vstack([self._vec(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _l2_normalize(self._vec(text)[None, :])[0]


# ------------------------------------------------------------------------- índice
def game_text(row) -> str:
    """Texto que se convierte en vector: título, géneros, etiquetas y descripción."""
    return (
        f"{row['name']}. Genres: {', '.join(row['genres'])}. "
        f"Tags: {', '.join(row['tags'][:10])}. {row['description']}"
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class EmbeddingIndex:
    matrix: np.ndarray  # (n_juegos, dim), filas normalizadas
    meta: dict

    @classmethod
    def build(cls, catalog: Catalog, embedder: Embedder) -> "EmbeddingIndex":
        if catalog.path is None:
            raise IndexError_("El catálogo debe cargarse desde un archivo para construir el índice.")
        texts = [game_text(row) for _, row in catalog.df.iterrows()]
        matrix = embedder.embed_documents(texts)
        meta = {
            "backend": embedder.backend,
            "model": embedder.model,
            "dim": int(matrix.shape[1]),
            "n_items": int(matrix.shape[0]),
            "catalog_file": catalog.path.name,
            "catalog_sha256": file_sha256(catalog.path),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return cls(matrix, meta)

    def save(self, npy_path: Path, meta_path: Path) -> None:
        np.save(npy_path, self.matrix)
        Path(meta_path).write_text(json.dumps(self.meta, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, npy_path: Path, meta_path: Path, catalog: Catalog | None = None) -> "EmbeddingIndex":
        npy_path, meta_path = Path(npy_path), Path(meta_path)
        if not npy_path.exists() or not meta_path.exists():
            raise IndexError_(
                f"No existe el índice de embeddings ({npy_path.name}). "
                "Genera uno con: python scripts/build_embeddings.py"
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        matrix = np.load(npy_path)
        if catalog is not None:
            if matrix.shape[0] != len(catalog):
                raise IndexError_(
                    f"El índice tiene {matrix.shape[0]} vectores y el catálogo {len(catalog)} juegos. "
                    "Regenera el índice con scripts/build_embeddings.py."
                )
            if catalog.path is not None and meta.get("catalog_sha256") != file_sha256(catalog.path):
                raise IndexError_(
                    "El catálogo cambió desde que se generó el índice. "
                    "Regenera el índice con scripts/build_embeddings.py."
                )
        return cls(matrix, meta)

    def similarities(self, query_vec: np.ndarray, rows: np.ndarray | None = None) -> np.ndarray:
        """Similitud coseno entre la consulta y las filas indicadas (todas si ``rows`` es None)."""
        m = self.matrix if rows is None else self.matrix[rows]
        return m @ np.asarray(query_vec, dtype=np.float32)


def make_embedder_for(meta: dict) -> Embedder:
    """Embedder compatible con el índice: las consultas deben usar el mismo modelo que los documentos."""
    backend = meta.get("backend")
    if backend == "hash":
        return HashEmbedder(dim=int(meta.get("dim", 512)))
    if backend == "nim":
        return NimEmbedder(model=meta.get("model"))
    raise IndexError_(f"Backend de embeddings desconocido en el índice: {backend!r}")


def load_index(catalog: Catalog) -> tuple[EmbeddingIndex, Embedder]:
    """Carga el índice asociado al catálogo y crea el embedder de consultas correspondiente."""
    if catalog.path is None:
        raise IndexError_("El catálogo no tiene ruta de archivo asociada.")
    npy, meta = config.embeddings_paths(catalog.path)
    index = EmbeddingIndex.load(npy, meta, catalog)
    return index, make_embedder_for(index.meta)
