"""Pruebas del índice de embeddings y del formato de las peticiones a NVIDIA NIM (cliente simulado)."""
from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

import config
from catalog import Catalog
from embeddings import (
    EmbeddingIndex, HashEmbedder, IndexError_, NimEmbedder, game_text, load_index, make_embedder_for,
)
from conftest import SAMPLE_CSV


class FakeEmbeddingsClient:
    """Imita ``client.embeddings.create``: registra las peticiones y devuelve vectores deterministas."""

    def __init__(self, dim=8, shuffle=False):
        self.calls: list[dict] = []
        self.dim, self.shuffle = dim, shuffle
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        rng_rows = []
        for i, text in enumerate(kwargs["input"]):
            vec = np.full(self.dim, float(len(text) % 7 + 1)) + np.arange(self.dim)
            rng_rows.append(SimpleNamespace(index=i, embedding=vec.tolist()))
        if self.shuffle:
            rng_rows.reverse()  # el servidor puede devolver los elementos desordenados
        return SimpleNamespace(data=rng_rows)


def test_nim_documentos_usan_input_type_passage_y_lotes():
    client = FakeEmbeddingsClient()
    emb = NimEmbedder(client=client, model="nvidia/nemotron-3.5-embed-1b", batch_size=4)
    out = emb.embed_documents([f"texto {i}" for i in range(10)])
    assert out.shape == (10, 8) and np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-5)
    assert [len(c["input"]) for c in client.calls] == [4, 4, 2]
    for call in client.calls:
        assert call["model"] == "nvidia/nemotron-3.5-embed-1b"
        assert call["extra_body"] == {"input_type": "passage"} and call["encoding_format"] == "float"


def test_nim_consultas_usan_input_type_query():
    client = FakeEmbeddingsClient()
    v = NimEmbedder(client=client).embed_query("relaxing farm")
    assert v.shape == (8,) and client.calls[0]["extra_body"] == {"input_type": "query"}
    assert client.calls[0]["model"] == config.EMBED_MODEL


def test_nim_respeta_el_orden_original_aunque_el_servidor_lo_altere():
    textos = ["a" * n for n in (1, 2, 3, 4)]
    ordenado = NimEmbedder(client=FakeEmbeddingsClient()).embed_documents(textos)
    barajado = NimEmbedder(client=FakeEmbeddingsClient(shuffle=True)).embed_documents(textos)
    assert np.allclose(ordenado, barajado)


def test_nim_recorta_textos_largos():
    client = FakeEmbeddingsClient()
    NimEmbedder(client=client).embed_query("x" * 10_000)
    assert len(client.calls[0]["input"][0]) <= 1500


def test_el_texto_del_juego_incluye_titulo_generos_tags_y_descripcion(catalog):
    texto = game_text(catalog.find_by_name("Turnip Hollow"))
    assert "Turnip Hollow" in texto and "Simulation" in texto and "Farming Sim" in texto and "calm online co-op" in texto


def test_hash_embedder_es_determinista_y_normalizado():
    a, b = HashEmbedder(), HashEmbedder()
    v1, v2 = a.embed_query("relaxing farm game"), b.embed_query("relaxing farm game")
    assert np.array_equal(v1, v2) and abs(np.linalg.norm(v1) - 1) < 1e-5
    assert np.linalg.norm(a.embed_query("the and of")) == 0  # solo palabras vacías → vector nulo, sin NaN


def test_indice_guardar_cargar_y_consultar(tmp_path, catalog):
    csv = tmp_path / "juegos.csv"
    shutil.copy(SAMPLE_CSV, csv)
    cat = Catalog.load(csv)
    emb = HashEmbedder()
    index = EmbeddingIndex.build(cat, emb)
    npy, meta = config.embeddings_paths(csv)
    index.save(npy, meta)
    assert npy.name == "juegos.embeddings.npy" and meta.name == "juegos.embeddings.json"

    loaded, embedder = load_index(cat)
    assert loaded.matrix.shape == (len(cat), 512) and isinstance(embedder, HashEmbedder)
    assert loaded.meta["backend"] == "hash" and loaded.meta["n_items"] == len(cat)
    sims = loaded.similarities(embedder.embed_query("horror hospital"))
    assert cat.df.iloc[int(np.argmax(sims))]["name"] == "Hollow Corridors"


def test_indice_se_rechaza_si_el_catalogo_cambio(tmp_path):
    csv = tmp_path / "juegos.csv"
    shutil.copy(SAMPLE_CSV, csv)
    cat = Catalog.load(csv)
    npy, meta = config.embeddings_paths(csv)
    EmbeddingIndex.build(cat, HashEmbedder()).save(npy, meta)
    csv.write_text(csv.read_text(encoding="utf-8").replace("14.99", "15.99", 1), encoding="utf-8")
    with pytest.raises(IndexError_, match="cambió"):
        load_index(Catalog.load(csv))


def test_indice_se_rechaza_si_no_coincide_el_numero_de_juegos(tmp_path, catalog):
    npy, meta = tmp_path / "x.npy", tmp_path / "x.json"
    np.save(npy, np.zeros((3, 4), dtype=np.float32))
    meta.write_text(json.dumps({"backend": "hash", "dim": 4}), encoding="utf-8")
    with pytest.raises(IndexError_, match="vectores"):
        EmbeddingIndex.load(npy, meta, catalog)


def test_indice_inexistente_da_instrucciones(tmp_path):
    with pytest.raises(IndexError_, match="build_embeddings"):
        EmbeddingIndex.load(tmp_path / "no.npy", tmp_path / "no.json")


def test_las_consultas_usan_el_mismo_backend_que_el_indice():
    assert isinstance(make_embedder_for({"backend": "hash", "dim": 512}), HashEmbedder)
    with pytest.raises(IndexError_):
        make_embedder_for({"backend": "otro"})


def test_el_indice_de_muestra_incluido_en_data_es_valido():
    cat = Catalog.load(SAMPLE_CSV)
    index, embedder = load_index(cat)  # falla si el CSV de muestra y su índice no están sincronizados
    assert index.matrix.shape[0] == len(cat) == 43
