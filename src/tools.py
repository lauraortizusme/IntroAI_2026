"""Las cuatro herramientas del agente y sus esquemas de function calling.

Principios de diseño (ver README, secciones 6 y 7):

* Cada herramienta valida sus argumentos y SIEMPRE devuelve un dict serializable a JSON.
  Los errores no son excepciones: son resultados controlados (``ok: False`` + ``tipo_error``)
  que el modelo puede leer y corregir.
* Los filtros obligatorios (precio máximo, plataforma, género, etiquetas) se aplican ANTES de
  ordenar por similitud y se vuelven a verificar fila a fila sobre lo que se devuelve.
* ``calcular_total`` solo recibe títulos y toma los precios del catálogo; el modelo nunca
  aporta cifras ni expresiones.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable

import numpy as np

from catalog import Catalog, PLATFORM_LABELS, normalize_platform
from embeddings import Embedder, EmbeddingIndex, IndexError_, load_index

log = logging.getLogger(__name__)

MAX_RESULTS = 20
MAX_TITLES = 20
MAX_QUERY_CHARS = 500


class ArgError(ValueError):
    """Argumento inválido; se comunica al modelo como resultado controlado."""


# ------------------------------------------------------------------ validadores
def _opt_text(value: Any, name: str, max_len: int = 120) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ArgError(f"'{name}' debe ser texto.")
    value = value.strip()
    if len(value) > max_len:
        raise ArgError(f"'{name}' es demasiado largo (máximo {max_len} caracteres).")
    return value


def _req_text(value: Any, name: str, max_len: int = MAX_QUERY_CHARS) -> str:
    text = _opt_text(value, name, max_len)
    if text is None:
        raise ArgError(f"'{name}' es obligatorio y no puede estar vacío.")
    return text


def _opt_price(value: Any, name: str = "precio_max") -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ArgError(f"'{name}' debe ser un número.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ArgError(f"'{name}' debe ser un número en USD (recibido: {value!r}).") from None
    if number != number or number in (float("inf"), float("-inf")) or number < 0:
        raise ArgError(f"'{name}' debe ser un número mayor o igual a 0.")
    return round(number, 2)


def _int_in_range(value: Any, name: str, default: int, lo: int, hi: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ArgError(f"'{name}' debe ser un entero.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ArgError(f"'{name}' debe ser un entero entre {lo} y {hi}.") from None
    if number != int(number):
        raise ArgError(f"'{name}' debe ser un entero entre {lo} y {hi}.")
    number = int(number)
    if not lo <= number <= hi:
        raise ArgError(f"'{name}' debe estar entre {lo} y {hi} (recibido: {number}).")
    return number


def _opt_text_list(value: Any, name: str, max_items: int = 8) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v for v in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise ArgError(f"'{name}' debe ser una lista de textos.")
    out: list[str] = []
    for item in value:
        text = _opt_text(item, name)
        if text and text not in out:
            out.append(text)
    if len(out) > max_items:
        raise ArgError(f"'{name}' admite como máximo {max_items} elementos.")
    return out


def _opt_platform(value: Any) -> str | None:
    text = _opt_text(value, "plataforma", 40)
    if text is None:
        return None
    platform = normalize_platform(text)
    if platform is None:
        raise ArgError(
            f"'plataforma' no reconocida ({text!r}). Valores válidos: windows, mac, linux."
        )
    return platform


def _error(tipo: str, mensaje: str, **extra: Any) -> dict:
    return {"ok": False, "tipo_error": tipo, "mensaje": mensaje, **extra}


# ------------------------------------------------------------------ herramientas
class GameTools:
    """Herramientas del agente sobre un catálogo (y, opcionalmente, un índice de embeddings)."""

    def __init__(
        self,
        catalog: Catalog,
        index: EmbeddingIndex | None = None,
        embedder: Embedder | None = None,
    ):
        self.catalog = catalog
        self._index = index
        self._embedder = embedder
        self._index_error: str | None = None
        self._registry: dict[str, Callable[..., dict]] = {
            "buscar_juegos": self.buscar_juegos,
            "buscar_similares": self.buscar_similares,
            "detalle_juego": self.detalle_juego,
            "calcular_total": self.calcular_total,
        }

    # -- utilidades internas ---------------------------------------------------
    def _resolve_filters(
        self, genero: Any, tags: Any, precio_max: Any, plataforma: Any
    ) -> tuple[dict, dict]:
        """Valida los filtros. Devuelve (filtros normalizados, avisos sobre vocabulario)."""
        filtros = {
            "genero": _opt_text(genero, "genero", 60),
            "tags": _opt_text_list(tags, "tags"),
            "precio_max": _opt_price(precio_max),
            "plataforma": _opt_platform(plataforma),
        }
        avisos: dict[str, Any] = {}
        if filtros["genero"] and not self.catalog.has_genre(filtros["genero"]):
            avisos["genero_desconocido"] = filtros["genero"]
            avisos["generos_validos"] = self.catalog.genres_vocab
        unknown_tags = [t for t in filtros["tags"] if not self.catalog.has_tag(t)]
        if unknown_tags:
            avisos["tags_desconocidos"] = unknown_tags
            avisos["tags_frecuentes"] = self.catalog.tags_vocab[:40]
        return filtros, avisos

    def _mask(self, filtros: dict):
        return self.catalog.filter_mask(
            genero=filtros["genero"],
            tags=filtros["tags"],
            precio_max=filtros["precio_max"],
            plataforma=filtros["plataforma"],
        )

    def _verify(self, rows, filtros: dict) -> bool:
        """Comprobación independiente: todo lo que se devuelve cumple los filtros."""
        return all(
            Catalog.row_satisfies(
                row,
                genero=filtros["genero"],
                tags=filtros["tags"],
                precio_max=filtros["precio_max"],
                plataforma=filtros["plataforma"],
            )
            for row in rows
        )

    @staticmethod
    def _filtros_report(filtros: dict) -> dict:
        return {k: v for k, v in filtros.items() if v not in (None, [], "")}

    def _ensure_index(self) -> bool:
        if self._index is not None and self._embedder is not None:
            return True
        if self._index_error is not None:
            return False
        try:
            self._index, self._embedder = load_index(self.catalog)
            return True
        except IndexError_ as exc:
            self._index_error = str(exc)
            return False

    # -- 1. buscar_juegos --------------------------------------------------------
    def buscar_juegos(
        self,
        genero: Any = None,
        tags: Any = None,
        precio_max: Any = None,
        plataforma: Any = None,
        limite: Any = 10,
    ) -> dict:
        limite = _int_in_range(limite, "limite", 10, 1, MAX_RESULTS)
        filtros, avisos = self._resolve_filters(genero, tags, precio_max, plataforma)
        mask = self._mask(filtros)
        found = self.catalog.df[mask].copy()
        # Relevancia de etiquetas primero (posición en la lista votada de Steam); popularidad como desempate.
        found["_tier"] = found["tags"].map(lambda ts: Catalog.tag_tier(ts, filtros["tags"]))
        found = found.sort_values(["_tier", "positive", "name"], ascending=[True, False, True])
        top = found.head(limite)
        orden = "por número de reseñas positivas (de mayor a menor)"
        if filtros["tags"]:
            orden = (
                "primero los juegos donde las etiquetas pedidas están entre las 5 más votadas, luego entre "
                "las 10 más votadas, luego el resto; dentro de cada grupo, por reseñas positivas"
            )
        result: dict[str, Any] = {
            "ok": True,
            "filtros_aplicados": self._filtros_report(filtros),
            "total_coincidencias": int(len(found)),
            "devueltos": int(len(top)),
            "orden": orden,
            "juegos": [self.catalog.summary(r) for _, r in top.iterrows()],
        }
        result.update(avisos)
        if found.empty:
            result["aviso"] = (
                "Ningún juego del catálogo cumple todos los filtros. "
                "Puedes relajar un filtro (precio, plataforma o etiquetas) y volver a buscar."
            )
        return result

    # -- 2. buscar_similares -----------------------------------------------------
    def buscar_similares(
        self,
        descripcion: Any,
        k: Any = 5,
        genero: Any = None,
        tags: Any = None,
        precio_max: Any = None,
        plataforma: Any = None,
    ) -> dict:
        descripcion = _req_text(descripcion, "descripcion")
        k = _int_in_range(k, "k", 5, 1, 10)
        filtros, avisos = self._resolve_filters(genero, tags, precio_max, plataforma)

        if not self._ensure_index():
            return _error("indice_no_disponible", self._index_error or "Índice no disponible.")

        mask = self._mask(filtros)  # los filtros se aplican ANTES de ordenar por similitud
        rows = np.flatnonzero(mask.to_numpy())
        base: dict[str, Any] = {
            "ok": True,
            "consulta": descripcion,
            "filtros_aplicados": self._filtros_report(filtros),
            "candidatos_tras_filtros": int(len(rows)),
        }
        base.update(avisos)
        if len(rows) == 0:
            base.update(juegos=[], devueltos=0, aviso=(
                "Ningún juego del catálogo cumple los filtros indicados, así que no hay nada que comparar."
            ))
            return base

        try:
            qvec = self._embedder.embed_query(descripcion)
        except Exception as exc:  # fallo de red/API: se informa al modelo, no se rompe el ciclo
            log.warning("Falló el embedding de la consulta: %s", exc)
            return _error("error_embeddings", f"No se pudo calcular la similitud: {type(exc).__name__}: {exc}")

        sims = self._index.similarities(qvec, rows)
        order = np.argsort(-sims, kind="stable")[:k]
        picked = [(int(rows[i]), float(sims[i])) for i in order]
        picked_rows = [self.catalog.df.iloc[i] for i, _ in picked]

        verified = self._verify(picked_rows, filtros)
        juegos = []
        for row, (_, score) in zip(picked_rows, picked):
            if not verified and not Catalog.row_satisfies(
                row, filtros["genero"], filtros["tags"], filtros["precio_max"], filtros["plataforma"]
            ):
                continue  # nunca devolver un juego que incumple un filtro
            item = self.catalog.summary(row)
            item["similitud"] = round(score, 3)
            juegos.append(item)
        base.update(
            devueltos=len(juegos),
            juegos=juegos,
            verificacion_filtros="ok" if verified else "se descartaron resultados que incumplían los filtros",
            orden="por similitud con la consulta (de mayor a menor)",
        )
        return base

    # -- 3. detalle_juego --------------------------------------------------------
    def detalle_juego(self, nombre: Any) -> dict:
        nombre = _req_text(nombre, "nombre", 200)
        row = self.catalog.find_by_name(nombre)
        if row is None:
            return {
                "ok": True,
                "encontrado": False,
                "nombre_buscado": nombre,
                "aviso": (
                    "Ese título no está en el catálogo. No se debe inventar su información. "
                    "Si el usuario quiso decir uno de los títulos sugeridos, vuelve a consultar con el nombre exacto."
                ),
                "sugerencias": self.catalog.suggest_names(nombre),
            }
        return {"ok": True, "encontrado": True, "juego": self.catalog.detail(row)}

    # -- 4. calcular_total -------------------------------------------------------
    def calcular_total(self, nombres: Any) -> dict:
        if isinstance(nombres, str):
            nombres = [n for n in nombres.split(",")]
        if not isinstance(nombres, (list, tuple)) or not nombres:
            raise ArgError("'nombres' debe ser una lista con al menos un título.")
        if len(nombres) > MAX_TITLES:
            raise ArgError(f"'nombres' admite como máximo {MAX_TITLES} títulos.")
        titles = [_req_text(n, "nombres", 200) for n in nombres]

        found: list[tuple[str, int]] = []  # (título del catálogo, precio en centavos)
        not_found: list[dict] = []
        no_price: list[str] = []
        duplicados: list[str] = []
        seen: set[str] = set()
        for title in titles:
            row = self.catalog.find_by_name(title)
            if row is None:
                not_found.append({"nombre_buscado": title, "sugerencias": self.catalog.suggest_names(title)})
                continue
            canonical = row["name"]
            if canonical in seen:
                duplicados.append(canonical)
                continue
            seen.add(canonical)
            if row["price"] != row["price"]:  # NaN
                no_price.append(canonical)
                continue
            found.append((canonical, int(round(float(row["price"]) * 100))))

        total_cents = sum(c for _, c in found)  # aritmética en centavos: sin errores de coma flotante
        result: dict[str, Any] = {
            "ok": True,
            "completo": not not_found and not no_price,
            "juegos": [{"nombre": n, "precio_usd": c / 100} for n, c in found],
            "cantidad_encontrados": len(found),
            "total_usd": round(total_cents / 100, 2) if found else None,
            "promedio_usd": round(total_cents / len(found) / 100, 2) if found else None,
            "moneda": "USD",
        }
        if not_found:
            result["no_encontrados"] = not_found
            result["aviso"] = (
                "El total solo incluye los juegos encontrados en el catálogo; "
                "los no encontrados no tienen precio conocido."
            )
        if no_price:
            result["sin_precio_en_catalogo"] = no_price
        if duplicados:
            result["duplicados_ignorados"] = duplicados
        if not found:
            result["aviso"] = "Ninguno de los títulos está en el catálogo, no se puede calcular un total."
        return result

    # -- ejecución segura --------------------------------------------------------
    def execute(self, name: str, arguments: Any) -> dict:
        """Ejecuta una herramienta por nombre. Nunca lanza: todo error es un resultado controlado."""
        func = self._registry.get(name)
        if func is None:
            return _error(
                "herramienta_desconocida",
                f"La herramienta {name!r} no existe.",
                herramientas_disponibles=sorted(self._registry),
            )
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                return _error("argumentos_invalidos", f"Los argumentos no son JSON válido: {exc.msg}.")
        if not isinstance(arguments, dict):
            return _error("argumentos_invalidos", "Los argumentos deben ser un objeto JSON.")
        allowed = set(inspect.signature(func).parameters)
        extra = sorted(set(arguments) - allowed)
        if extra:
            return _error(
                "argumentos_invalidos",
                f"Argumentos no reconocidos: {extra}.",
                argumentos_permitidos=sorted(allowed),
            )
        try:
            return func(**arguments)
        except TypeError as exc:  # p. ej. falta un argumento obligatorio
            return _error("argumentos_invalidos", str(exc))
        except ArgError as exc:
            return _error("argumentos_invalidos", str(exc))
        except Exception as exc:  # defensa final: el ciclo del agente no debe romperse
            log.exception("Error inesperado en la herramienta %s", name)
            return _error("error_interno", f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ esquemas
_FILTER_PROPS = {
    "genero": {
        "type": "string",
        "description": "Un género de Steam, por ejemplo: Action, Adventure, Casual, Indie, RPG, "
        "Simulation, Strategy, Racing, Sports. Géneros como 'shooter' o 'co-op' NO son géneros: van en 'tags'.",
    },
    "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Etiquetas de Steam en inglés que el juego debe tener TODAS, por ejemplo: "
        "Shooter, Co-op, Multiplayer, Singleplayer, Relaxing, Cozy, Farming Sim, Horror, Puzzle.",
    },
    "precio_max": {
        "type": "number",
        "description": "Precio máximo en USD, inclusivo. Usa 0 para juegos gratuitos.",
    },
    "plataforma": {
        "type": "string",
        "enum": ["windows", "mac", "linux"],
        "description": "Sistema operativo de PC que el juego debe soportar.",
    },
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_juegos",
            "description": "Busca en el catálogo aplicando filtros EXACTOS (género, etiquetas, precio máximo, "
            "plataforma). Úsala cuando el usuario indique condiciones verificables. Devuelve los juegos que "
            "cumplen todos los filtros; si se piden etiquetas, primero aquellos en los que esas etiquetas están "
            "entre las más votadas del juego y, a igualdad, por popularidad. Si no hay coincidencias, devuelve una "
            "lista vacía.",
            "parameters": {
                "type": "object",
                "properties": {
                    **_FILTER_PROPS,
                    "limite": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS,
                               "description": "Cantidad máxima de juegos a devolver (por defecto 10)."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_similares",
            "description": "Búsqueda SEMÁNTICA: encuentra los juegos cuya descripción se parece más a lo que el "
            "usuario pide con sus propias palabras (sensaciones, situaciones, 'algo parecido a...'). "
            "Si el usuario también da precio máximo, plataforma, género o etiquetas, pásalos como filtros "
            "obligatorios: se aplican antes de ordenar por similitud. Las descripciones del catálogo están "
            "en INGLÉS: escribe 'descripcion' en inglés aunque el usuario hable en otro idioma.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string",
                                    "description": "Lo que busca el usuario, redactado en inglés, por ejemplo "
                                    "'relaxing cozy game about farming and decorating'."},
                    "k": {"type": "integer", "minimum": 1, "maximum": 10,
                          "description": "Cantidad de juegos a devolver (por defecto 5)."},
                    **_FILTER_PROPS,
                },
                "required": ["descripcion"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detalle_juego",
            "description": "Consulta la ficha de UN juego por su título: descripción, géneros, etiquetas, precio, "
            "sistemas operativos, reseñas y fecha de lanzamiento. Si el título no está en el catálogo lo indica "
            "y sugiere títulos parecidos.",
            "parameters": {
                "type": "object",
                "properties": {"nombre": {"type": "string", "description": "Título del juego."}},
                "required": ["nombre"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calcular_total",
            "description": "Calcula el costo conjunto de varios juegos (precios individuales, suma y promedio en USD) "
            "a partir de sus títulos EXACTOS. Los precios salen del catálogo; nunca calcules sumas tú mismo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombres": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                "maxItems": MAX_TITLES, "description": "Títulos de los juegos."},
                },
                "required": ["nombres"],
                "additionalProperties": False,
            },
        },
    },
]

assert {t["function"]["name"] for t in TOOL_SCHEMAS} == {
    "buscar_juegos", "buscar_similares", "detalle_juego", "calcular_total"
}
assert set(PLATFORM_LABELS) == set(_FILTER_PROPS["plataforma"]["enum"])
