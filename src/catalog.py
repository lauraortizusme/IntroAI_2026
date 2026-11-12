"""Carga y consulta del catálogo procesado de videojuegos.

El catálogo es un CSV con las columnas de ``REQUIRED_COLUMNS``. Las listas (géneros y
etiquetas) se guardan separadas por ``|``. Este módulo no conoce el LLM ni los
embeddings: solo expone filtros exactos, búsqueda de títulos y resúmenes de fichas.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = [
    "app_id", "name", "description", "genres", "tags", "price",
    "windows", "mac", "linux", "positive", "negative", "release_date",
]
LIST_SEP = "|"
PLATFORM_LABELS = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}
_PLATFORM_ALIASES = {
    "windows": "windows", "win": "windows", "pc": "windows", "win10": "windows", "win11": "windows",
    "mac": "mac", "macos": "mac", "mac os": "mac", "osx": "mac", "os x": "mac", "macintosh": "mac",
    "linux": "linux", "ubuntu": "linux", "steamos": "linux", "steam os": "linux", "steam deck": "linux",
}


def normalize_text(text: Any) -> str:
    """Minúsculas, sin tildes ni signos: sirve para comparar títulos y etiquetas."""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return s.strip()


def normalize_platform(value: Any) -> str | None:
    """Devuelve 'windows' | 'mac' | 'linux', o None si no se reconoce."""
    return _PLATFORM_ALIASES.get(normalize_text(value))


def _split_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "<na>", "none"}:
            return []
        items = text.split(LIST_SEP)
    return [str(i).strip() for i in items if str(i).strip()]


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "si", "sí"}
    return bool(value) and not (isinstance(value, float) and pd.isna(value))


class CatalogError(ValueError):
    """El archivo del catálogo no existe o no tiene el formato esperado."""


class Catalog:
    def __init__(self, df: pd.DataFrame, path: Path | None = None):
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise CatalogError(f"Al catálogo le faltan columnas: {missing}")
        df = df[REQUIRED_COLUMNS].copy().reset_index(drop=True)
        df["name"] = df["name"].astype(object).map(lambda s: str(s).strip())
        df["description"] = df["description"].astype(object).map(lambda s: "" if pd.isna(s) else str(s))
        df["genres"] = df["genres"].map(_split_list).astype(object)
        df["tags"] = df["tags"].map(_split_list).astype(object)
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        for col in ("windows", "mac", "linux"):
            df[col] = df[col].map(_to_bool)
        for col in ("positive", "negative"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        df["release_date"] = df["release_date"].astype(object).map(lambda s: "" if pd.isna(s) else str(s))
        # Columnas auxiliares para comparar sin distinguir mayúsculas ni tildes
        df["_name_norm"] = df["name"].map(normalize_text)
        df["_genres_norm"] = df["genres"].map(lambda xs: {normalize_text(x) for x in xs})
        df["_tags_norm"] = df["tags"].map(lambda xs: {normalize_text(x) for x in xs})
        self.df = df
        self.path = path

        genre_counter = Counter(g for xs in df["genres"] for g in xs)
        tag_counter = Counter(t for xs in df["tags"] for t in xs)
        self.genres_vocab: list[str] = [g for g, _ in genre_counter.most_common()]
        self.tags_vocab: list[str] = [t for t, _ in tag_counter.most_common()]
        self._genres_norm_vocab = {normalize_text(g) for g in self.genres_vocab}
        self._tags_norm_vocab = {normalize_text(t) for t in self.tags_vocab}

    # ------------------------------------------------------------------ carga
    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        path = Path(path)
        if not path.exists():
            raise CatalogError(
                f"No se encontró el catálogo en {path}. Ejecuta scripts/prepare_data.py "
                "o scripts/make_sample_data.py."
            )
        return cls(pd.read_csv(path), path=path)

    def __len__(self) -> int:
        return len(self.df)

    # ----------------------------------------------------------- vocabularios
    def has_genre(self, genre: str) -> bool:
        return normalize_text(genre) in self._genres_norm_vocab

    def has_tag(self, tag: str) -> bool:
        return normalize_text(tag) in self._tags_norm_vocab

    # ------------------------------------------------------------------ filtros
    def filter_mask(
        self,
        genero: str | None = None,
        tags: list[str] | None = None,
        precio_max: float | None = None,
        plataforma: str | None = None,
    ) -> pd.Series:
        """Máscara booleana de los juegos que cumplen TODOS los filtros dados.

        ``precio_max`` es inclusivo (precio <= precio_max). ``tags`` exige todas las etiquetas.
        ``plataforma`` debe venir ya normalizada ('windows' | 'mac' | 'linux').
        """
        df = self.df
        mask = pd.Series(True, index=df.index)
        if genero:
            g = normalize_text(genero)
            mask &= df["_genres_norm"].map(lambda s: g in s)
        for tag in tags or []:
            t = normalize_text(tag)
            mask &= df["_tags_norm"].map(lambda s, t=t: t in s)
        if precio_max is not None:
            mask &= df["price"].le(precio_max).fillna(False)
        if plataforma:
            mask &= df[plataforma]
        return mask

    # Niveles de relevancia de etiquetas: las etiquetas de Steam vienen ordenadas por votos, así que
    # una etiqueta en las primeras posiciones describe mejor el juego que una en la posición 15.
    TAG_TIERS = (5, 10)  # nivel 0: todas las pedidas entre las 5 primeras; 1: entre las 10; 2: resto

    @classmethod
    def tag_tier(cls, row_tags: list[str], requested: list[str] | None) -> int:
        """Nivel según la PEOR posición (1 = más votada) de las etiquetas pedidas en ``row_tags``.

        Sin etiquetas pedidas, todos los juegos tienen nivel 0 (el orden queda solo por popularidad).
        Una etiqueta pedida que no está en la lista cuenta como el último nivel.
        """
        if not requested:
            return 0
        norm = [normalize_text(t) for t in row_tags]
        worst = 0
        for tag in requested:
            t = normalize_text(tag)
            worst = max(worst, norm.index(t) + 1 if t in norm else 10**6)
        for tier, limit in enumerate(cls.TAG_TIERS):
            if worst <= limit:
                return tier
        return len(cls.TAG_TIERS)

    @staticmethod
    def row_satisfies(
        row: pd.Series,
        genero: str | None = None,
        tags: list[str] | None = None,
        precio_max: float | None = None,
        plataforma: str | None = None,
    ) -> bool:
        """Verificación fila a fila (independiente de ``filter_mask``) para auditar resultados."""
        if genero and normalize_text(genero) not in {normalize_text(g) for g in row["genres"]}:
            return False
        row_tags = {normalize_text(t) for t in row["tags"]}
        if any(normalize_text(t) not in row_tags for t in tags or []):
            return False
        if precio_max is not None and not (pd.notna(row["price"]) and float(row["price"]) <= precio_max):
            return False
        if plataforma and not bool(row[plataforma]):
            return False
        return True

    # ------------------------------------------------------------------ títulos
    def find_by_name(self, name: str) -> pd.Series | None:
        """Coincidencia exacta del título (sin distinguir mayúsculas, tildes ni signos)."""
        norm = normalize_text(name)
        if not norm:
            return None
        hits = self.df[self.df["_name_norm"] == norm]
        if hits.empty:
            return None
        return hits.sort_values("positive", ascending=False).iloc[0]

    def suggest_names(self, name: str, n: int = 3) -> list[str]:
        """Títulos del catálogo parecidos al pedido (nunca inventa: solo devuelve títulos reales)."""
        norm = normalize_text(name)
        if not norm:
            return []
        norms = self.df["_name_norm"].tolist()
        picked: list[str] = []
        for cand in difflib.get_close_matches(norm, norms, n=n, cutoff=0.6):
            picked.append(cand)
        if len(norm) >= 4:
            for cand in norms:
                if (norm in cand or cand in norm) and cand not in picked:
                    picked.append(cand)
        by_norm = dict(zip(self.df["_name_norm"], self.df["name"]))
        out: list[str] = []
        for cand in picked:
            title = by_norm[cand]
            if title not in out:
                out.append(title)
        return out[:n]

    # ----------------------------------------------------------- representaciones
    @staticmethod
    def platforms_of(row: pd.Series) -> list[str]:
        return [label for col, label in PLATFORM_LABELS.items() if bool(row[col])]

    @staticmethod
    def positive_pct(row: pd.Series) -> float | None:
        total = int(row["positive"]) + int(row["negative"])
        return round(100 * int(row["positive"]) / total, 1) if total else None

    @staticmethod
    def _price(row: pd.Series) -> float | None:
        return None if pd.isna(row["price"]) else round(float(row["price"]), 2)

    def summary(self, row: pd.Series) -> dict[str, Any]:
        """Datos breves de un juego para listados."""
        return {
            "nombre": row["name"],
            "precio_usd": self._price(row),
            "plataformas": self.platforms_of(row),
            "generos": list(row["genres"]),
            "tags": list(row["tags"][:8]),
            "valoracion_positiva_pct": self.positive_pct(row),
        }

    def detail(self, row: pd.Series) -> dict[str, Any]:
        """Ficha completa de un juego."""
        return {
            "nombre": row["name"],
            "descripcion": row["description"],
            "generos": list(row["genres"]),
            "tags": list(row["tags"]),
            "precio_usd": self._price(row),
            "plataformas": self.platforms_of(row),
            "resenas_positivas": int(row["positive"]),
            "resenas_negativas": int(row["negative"]),
            "valoracion_positiva_pct": self.positive_pct(row),
            "fecha_lanzamiento": row["release_date"] or None,
        }
