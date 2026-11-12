"""Prepara el catálogo real a partir del Steam Games Dataset (FronkonGames, Hugging Face).

Pasos (README, sección 5):
  1. Cargar el dataset (descarga desde Hugging Face o archivo local .csv/.parquet) y registrar
     su versión/fecha de consulta.
  2. Quedarse con juegos con descripción disponible y en inglés.
  3. Normalizar tipos: precio numérico, plataformas booleanas, géneros y etiquetas como listas.
  4. Eliminar duplicados (por título) y registros sin descripción o sin precio.
  5. Priorizar por número de reseñas y conservar los N primeros (por defecto 1000).
  6. Guardar data/catalog.csv y data/catalog_info.json (criterios, conteos, fecha, fuente).

Después de este script, ejecutar:  python scripts/build_embeddings.py

Uso:
    python scripts/prepare_data.py                         # descarga desde Hugging Face
    python scripts/prepare_data.py --source train.parquet --tags-csv games.csv   # archivos locales
    python scripts/prepare_data.py --n 1000 --out data/catalog.csv

Columnas del dataset original usadas (verificadas en la ficha, 2026-11-11):
    appID, name, release_date, price, short_description, detailed_description,
    supported_languages, windows, mac, linux, positive, negative, genres, tags
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from catalog import LIST_SEP, REQUIRED_COLUMNS  # noqa: E402

HF_DATASET_ID = "FronkonGames/steam-games-dataset"
RAW_COLUMNS = [
    "appID", "name", "release_date", "price", "short_description", "detailed_description",
    "supported_languages", "windows", "mac", "linux", "positive", "negative", "genres", "tags",
]
_EN_STOP = frozenset(
    "the and to of a in is you with for your are on as be this that it from or an will can at by "
    "have not all their more".split()
)


# ------------------------------------------------------------------ utilidades
def clean_html(text) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def looks_english(text: str) -> bool:
    """Heurística sin dependencias: mayoría de caracteres ASCII y presencia de palabras funcionales en inglés."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 30:
        return False
    if sum(c.isascii() for c in letters) / len(letters) < 0.95:
        return False
    tokens = re.findall(r"[a-z']+", text.lower())
    return len(tokens) >= 8 and sum(t in _EN_STOP for t in tokens) / len(tokens) >= 0.15


def to_list(value) -> list[str]:
    """Géneros/etiquetas pueden venir como texto separado por comas o como lista/array (parquet)."""
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if hasattr(value, "tolist") and not isinstance(value, str):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        items = value
    else:
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            # Representación de lista ("['Co-op', \"Beat 'em up\"]"): las comillas delimitan elementos.
            try:
                parsed = ast.literal_eval(text)
                items = parsed if isinstance(parsed, (list, tuple)) else [parsed]
            except (ValueError, SyntaxError):
                items = [i.strip().strip("'\"") for i in text[1:-1].split(",")]
        else:
            # Texto separado por comas: los apóstrofos son parte de la etiqueta ("Beat 'em up").
            items = text.split(",")
    return [str(i).strip() for i in items if str(i).strip()]


def to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value) and not (isinstance(value, float) and pd.isna(value))


def supports_english(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if hasattr(value, "tolist") and not isinstance(value, str):
        value = value.tolist()
    return "english" in str(value).lower()


# ------------------------------------------------------------------ etiquetas (tags)
# En la versión parquet del dataset (la que carga `datasets`), la columna `tags` llega con tipo
# List(null) y VACÍA en todas las filas: en games.json las etiquetas son un diccionario
# {etiqueta: votos} que la conversión a parquet no conserva. games.csv, del mismo repositorio,
# sí las trae (texto separado por comas, en orden de votos), pero su cabecera fusiona dos
# columnas ("DiscountDLC count"): 39 nombres para 40 valores por fila.
HF_TAGS_FILE = "games.csv"
_MERGED_HEADER = "DiscountDLC count"


def fixed_csv_header(header: list[str]) -> list[str]:
    """Separa la cabecera fusionada 'DiscountDLC count' en 'Discount' y 'DLC count'."""
    if _MERGED_HEADER not in header:
        return list(header)
    i = header.index(_MERGED_HEADER)
    return header[:i] + ["Discount", "DLC count"] + header[i + 1:]


def tags_all_empty(series: pd.Series) -> bool:
    return not series.map(lambda v: bool(to_list(v))).any()


def read_tags_from_games_csv(path: str | Path) -> pd.Series:
    """Lee AppID → etiquetas (texto 'a,b,c') de games.csv corrigiendo la cabecera desalineada."""
    header = pd.read_csv(path, nrows=0).columns.tolist()
    names = fixed_csv_header(header)
    if "AppID" not in names or "Tags" not in names:
        raise ValueError(f"{Path(path).name} no tiene las columnas AppID y Tags: {names[:10]}…")
    df = pd.read_csv(path, header=None, skiprows=1, names=names, usecols=["AppID", "Tags"],
                     dtype={"AppID": "string", "Tags": "string"}, keep_default_na=False)
    df["AppID"] = pd.to_numeric(df["AppID"], errors="coerce")
    df = df.dropna(subset=["AppID"]).drop_duplicates("AppID")
    return pd.Series(df["Tags"].to_numpy(), index=df["AppID"].astype("int64"), name="tags")


def fill_tags(raw: pd.DataFrame, tags_by_app: pd.Series) -> tuple[pd.DataFrame, int]:
    """Completa `tags` por appID solo en las filas donde está vacía. Devuelve (df, filas completadas)."""
    df = raw.copy()
    app = pd.to_numeric(df["appID"], errors="coerce")
    empty = ~df["tags"].map(lambda v: bool(to_list(v)))
    new = app.map(tags_by_app)
    use = empty & new.notna() & (new.astype("string").str.strip() != "")
    df["tags"] = df["tags"].astype(object)
    df.loc[use, "tags"] = new[use]
    return df, int(use.sum())


# ------------------------------------------------------------------ carga
def load_raw(source: str | Path | None, tags_csv: str | Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Carga el dataset crudo y devuelve (DataFrame, metadatos de procedencia).

    ``tags_csv``: games.csv del mismo dataset para completar las etiquetas de una fuente LOCAL cuya columna
    ``tags`` venga vacía (como el parquet de Hugging Face). Con la descarga ('hf') se obtiene automáticamente.
    """
    info: dict = {"dataset": HF_DATASET_ID, "consulted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if source in (None, "", "hf"):
        from datasets import load_dataset

        revision = None
        try:
            from huggingface_hub import HfApi

            revision = HfApi().dataset_info(HF_DATASET_ID).sha
            info["revision_sha"] = revision
        except Exception as exc:  # la revisión es informativa; no debe impedir la preparación
            info["revision_sha"] = f"no disponible ({type(exc).__name__})"
        ds = load_dataset(HF_DATASET_ID, split="train", revision=revision)
        df = ds.to_pandas()
        info["origin"] = "huggingface"
        info["tags_source"] = "columna tags del parquet"
        if "tags" in df.columns and tags_all_empty(df["tags"]):
            from huggingface_hub import hf_hub_download

            print(f"La columna 'tags' del parquet está vacía en todas las filas; se completa desde {HF_TAGS_FILE}…")
            csv_path = hf_hub_download(HF_DATASET_ID, HF_TAGS_FILE, repo_type="dataset", revision=revision)
            df, filled = fill_tags(df, read_tags_from_games_csv(csv_path))
            info["tags_source"] = (
                f"{HF_TAGS_FILE} de la misma revisión (la columna tags del parquet viene vacía); "
                f"cruce por appID, {filled} filas completadas"
            )
        return df, info
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo {path}")
    df = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
    info["origin"] = f"archivo local: {path.name}"
    info["tags_source"] = "columna tags del archivo local"
    if "tags" in df.columns and tags_all_empty(df["tags"]):
        if tags_csv:
            df, filled = fill_tags(df, read_tags_from_games_csv(tags_csv))
            info["tags_source"] = f"{Path(tags_csv).name} (cruce por appID, {filled} filas completadas)"
        else:
            print("AVISO: la columna 'tags' está vacía en todas las filas y no se indicó --tags-csv; "
                  "el catálogo quedará sin etiquetas (buscar_juegos no podrá filtrar por ellas).")
            info["tags_source"] = "vacía (no se indicó --tags-csv)"
    return df, info


# ------------------------------------------------------------------ selección
def select_catalog(raw: pd.DataFrame, n: int = 1000, min_description_chars: int = 60) -> tuple[pd.DataFrame, dict]:
    """Aplica los criterios de selección. Devuelve (catálogo procesado, conteos por paso)."""
    missing = [c for c in RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(
            f"Al dataset le faltan columnas esperadas: {missing}. "
            f"Columnas presentes: {list(raw.columns)[:15]}…"
        )
    df = raw[RAW_COLUMNS].copy()
    stats = {"registros_originales": int(len(df))}

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    if df["price"].isna().mean() > 0.2:
        raise ValueError(
            "Más del 20 % de los precios no son numéricos: las columnas del archivo parecen desalineadas. "
            "Usa la versión de Hugging Face (--source hf) o revisa el archivo."
        )
    df["name"] = df["name"].map(lambda s: "" if pd.isna(s) else str(s).strip())
    df = df[df["name"] != ""]
    stats["con_titulo"] = int(len(df))

    df = df[df["price"].notna() & (df["price"] >= 0)]
    stats["con_precio_valido"] = int(len(df))

    df = df[df["supported_languages"].map(supports_english)]
    stats["con_ingles_soportado"] = int(len(df))

    short = df["short_description"].map(clean_html)
    detailed = df["detailed_description"].map(clean_html)
    df["description"] = [s if len(s) >= min_description_chars else d[:800] for s, d in zip(short, detailed)]
    df = df[df["description"].str.len() >= min_description_chars]
    stats["con_descripcion"] = int(len(df))

    df = df[df["description"].map(looks_english)]
    stats["descripcion_en_ingles"] = int(len(df))

    df["positive"] = pd.to_numeric(df["positive"], errors="coerce").fillna(0).astype(int)
    df["negative"] = pd.to_numeric(df["negative"], errors="coerce").fillna(0).astype(int)
    df["_reviews"] = df["positive"] + df["negative"]
    df["_key"] = df["name"].str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    df = df.sort_values("_reviews", ascending=False).drop_duplicates("_key", keep="first")
    stats["sin_duplicados"] = int(len(df))

    df = df.head(n).copy()
    stats["catalogo_final"] = int(len(df))

    out = pd.DataFrame({
        "app_id": df["appID"],
        "name": df["name"],
        "description": df["description"],
        "genres": df["genres"].map(lambda v: LIST_SEP.join(to_list(v))),
        "tags": df["tags"].map(lambda v: LIST_SEP.join(to_list(v))),
        "price": df["price"].round(2),
        "windows": df["windows"].map(to_bool),
        "mac": df["mac"].map(to_bool),
        "linux": df["linux"].map(to_bool),
        "positive": df["positive"],
        "negative": df["negative"],
        "release_date": pd.to_datetime(df["release_date"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d").fillna(""),
    })[REQUIRED_COLUMNS].reset_index(drop=True)
    stats["catalogo_con_tags"] = int((out["tags"] != "").sum())
    return out, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="hf",
                        help="'hf' (descarga) o ruta a un .csv/.parquet local con el esquema del parquet (snake_case)")
    parser.add_argument("--tags-csv", default=None,
                        help="games.csv del dataset para completar etiquetas vacías de una fuente local")
    parser.add_argument("--n", type=int, default=1000, help="tamaño del catálogo (por defecto 1000)")
    parser.add_argument("--out", type=Path, default=Path("data/catalog.csv"))
    args = parser.parse_args()

    raw, origin = load_raw(args.source, tags_csv=args.tags_csv)
    print(f"Dataset cargado: {len(raw):,} registros")
    catalog, stats = select_catalog(raw, n=args.n)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(args.out, index=False)
    info = {
        **origin,
        "license_note": (
            "Los metadatos de la ficha de Hugging Face declaran 'license: mit'; el texto de la ficha indica que MIT "
            "corresponde al código de recolección (Steam-Games-Scraper) y no fija términos adicionales para los datos. "
            "Se conserva la atribución a FronkonGames."
        ),
        "criteria": {
            "idioma": "inglés soportado y descripción en inglés (heurística)",
            "descripcion": "short_description (>=60 caracteres) o detailed_description sin HTML (<=800)",
            "precio": "numérico y >= 0 (USD)",
            "duplicados": "se conserva el título con más reseñas",
            "orden": "positive + negative, de mayor a menor",
            "tamano_objetivo": args.n,
        },
        "counts": stats,
        "output_file": args.out.name,
    }
    info_path = args.out.with_name("catalog_info.json")
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Conteos por paso:")
    for k, v in stats.items():
        print(f"  {k:<24}{v:>10,}")
    print(f"\nCatálogo guardado: {args.out} ({len(catalog)} juegos)\nInformación de procedencia: {info_path}")
    print("Siguiente paso: python scripts/build_embeddings.py")


if __name__ == "__main__":
    main()
