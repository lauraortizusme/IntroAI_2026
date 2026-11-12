"""Fixtures compartidas: catálogo de muestra, índice 'hash' y un cliente LLM simulado."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from catalog import Catalog
from embeddings import EmbeddingIndex, HashEmbedder
from tools import GameTools

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_games.csv"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.load(SAMPLE_CSV)


@pytest.fixture(scope="session")
def tools(catalog) -> GameTools:
    embedder = HashEmbedder()
    return GameTools(catalog, EmbeddingIndex.build(catalog, embedder), embedder)


# ------------------------------------------------------------- LLM simulado
def tool_call(name: str, arguments, call_id: str | None = None):
    args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=args))


def llm_message(content: str | None = None, tool_calls: list | None = None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or None)


class FakeClient:
    """Imita ``client.chat.completions.create``: devuelve mensajes preparados, en orden.

    Si ``script`` es una función, se le pasa (kwargs, n_llamada) y devuelve el mensaje.
    Guarda cada petición en ``self.requests`` para inspeccionar lo que recibió el modelo.
    """

    def __init__(self, script):
        self._script = script
        self.requests: list[dict] = []
        self.completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=self.completions)

    def _create(self, **kwargs):
        # copia superficial de la lista de mensajes para que cambios posteriores no alteren el registro
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        n = len(self.requests) - 1
        if callable(self._script):
            msg = self._script(kwargs, n)
        else:
            msg = self._script[n]
        if isinstance(msg, Exception):
            raise msg
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
