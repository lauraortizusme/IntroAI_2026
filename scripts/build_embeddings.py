"""Genera UNA sola vez los embeddings de las descripciones y los guarda para reutilizarlos.

Uso:
    python scripts/build_embeddings.py                      # catálogo por defecto, NVIDIA NIM
    python scripts/build_embeddings.py --catalog data/catalog.csv
    python scripts/build_embeddings.py --backend hash       # sin red: solo para pruebas locales

Salida (junto al catálogo): <catalogo>.embeddings.npy y <catalogo>.embeddings.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
from catalog import Catalog  # noqa: E402
from embeddings import EmbeddingIndex, HashEmbedder, NimEmbedder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=None, help="CSV del catálogo procesado")
    parser.add_argument("--backend", choices=["nim", "hash"], default="nim",
                        help="nim = NVIDIA NIM (entrega); hash = doble de pruebas sin red")
    args = parser.parse_args()

    catalog_path = args.catalog or config.default_catalog_path()
    catalog = Catalog.load(catalog_path)
    print(f"Catálogo: {catalog_path} ({len(catalog)} juegos)")

    if args.backend == "nim":
        try:
            embedder = NimEmbedder()
        except config.ConfigError as exc:
            sys.exit(f"ERROR: {exc}")
        print(f"Calculando embeddings con NVIDIA NIM: {embedder.model} …")
    else:
        embedder = HashEmbedder()
        print("AVISO: backend 'hash' = doble de pruebas, NO es similitud semántica real.")

    index = EmbeddingIndex.build(catalog, embedder)
    npy, meta = config.embeddings_paths(catalog_path)
    index.save(npy, meta)
    print(f"Índice guardado: {npy.name} {tuple(index.matrix.shape)} y {meta.name}")


if __name__ == "__main__":
    main()
