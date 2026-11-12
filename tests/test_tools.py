"""Pruebas de las cuatro herramientas sobre el catálogo de muestra (sin red ni LLM)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from catalog import Catalog, normalize_platform
from embeddings import HashEmbedder, EmbeddingIndex
from tools import GameTools, TOOL_SCHEMAS


def names(result: dict) -> list[str]:
    return [g["nombre"] for g in result["juegos"]]


# ------------------------------------------------------------- buscar_juegos
def test_filtros_combinados_cumplen_todas_las_condiciones(tools, catalog):
    r = tools.execute("buscar_juegos", {"tags": ["Shooter", "Co-op"], "precio_max": 10})
    assert r["ok"] and r["total_coincidencias"] == len(r["juegos"]) > 0
    for g in r["juegos"]:
        assert g["precio_usd"] <= 10
        assert {"Shooter", "Co-op"} <= set(catalog.find_by_name(g["nombre"])["tags"])


def test_precio_maximo_es_inclusivo_y_los_gratis_cuentan(tools):
    r = tools.execute("buscar_juegos", {"precio_max": 0, "limite": 20})
    assert r["juegos"] and all(g["precio_usd"] == 0 for g in r["juegos"])
    exacto = tools.execute("buscar_juegos", {"precio_max": 9.99, "tags": ["Farming Sim"]})
    assert "Turnip Hollow" in names(exacto)  # cuesta exactamente 9.99


def test_plataforma_acepta_sinonimos(tools):
    a = tools.execute("buscar_juegos", {"plataforma": "macOS", "limite": 20})
    b = tools.execute("buscar_juegos", {"plataforma": "mac", "limite": 20})
    assert names(a) == names(b)
    assert all("macOS" in g["plataformas"] for g in a["juegos"])
    assert normalize_platform("OS X") == "mac" and normalize_platform("amiga") is None


def test_argumentos_numericos_como_texto_se_aceptan(tools):
    r = tools.execute("buscar_juegos", {"precio_max": "5", "limite": "3"})
    assert r["ok"] and len(r["juegos"]) <= 3 and all(g["precio_usd"] <= 5 for g in r["juegos"])


def test_sin_coincidencias_es_resultado_controlado(tools):
    r = tools.execute("buscar_juegos", {"tags": ["Horror", "Farming Sim"]})
    assert r["ok"] and r["juegos"] == [] and "aviso" in r


def test_genero_inexistente_ofrece_vocabulario_valido(tools):
    r = tools.execute("buscar_juegos", {"genero": "shooter"})
    assert r["ok"] and r["juegos"] == []
    assert r["genero_desconocido"] == "shooter" and "Action" in r["generos_validos"]


def test_tag_desconocido_ofrece_tags_frecuentes(tools):
    r = tools.execute("buscar_juegos", {"tags": ["Inexistente"]})
    assert r["tags_desconocidos"] == ["Inexistente"] and r["tags_frecuentes"]


@pytest.mark.parametrize(
    "args",
    [
        {"precio_max": -1},
        {"precio_max": "barato"},
        {"limite": 0},
        {"limite": 99},
        {"limite": 2.5},
        {"plataforma": "amiga"},
        {"tags": 5},
        {"genero": 7},
        {"campo_inventado": 1},
    ],
)
def test_argumentos_invalidos_no_lanzan_excepcion(tools, args):
    r = tools.execute("buscar_juegos", args)
    assert r["ok"] is False and r["tipo_error"] == "argumentos_invalidos" and r["mensaje"]


def test_resultados_ordenados_por_popularidad(tools, catalog):
    r = tools.execute("buscar_juegos", {"limite": 20})
    pos = [catalog.find_by_name(n)["positive"] for n in names(r)]
    assert pos == sorted(pos, reverse=True)


# --------------------------------------------------------- buscar_similares
def test_busqueda_semantica_encuentra_juegos_de_granja(tools):
    r = tools.execute("buscar_similares", {"descripcion": "relaxing farming game", "k": 5})
    assert r["ok"] and len(r["juegos"]) == 5
    farm = {"Willowbrook Farm", "Turnip Hollow", "Sunpatch Valley", "Little Orchard Days", "Pasture & Pie"}
    assert len(farm & set(names(r))) >= 3
    sims = [g["similitud"] for g in r["juegos"]]
    assert sims == sorted(sims, reverse=True)


def test_similares_aplica_y_verifica_filtros_obligatorios(tools, catalog):
    r = tools.execute(
        "buscar_similares",
        {"descripcion": "relaxing cozy game with friends", "k": 10, "plataforma": "mac", "precio_max": 15},
    )
    assert r["ok"] and r["verificacion_filtros"] == "ok" and r["juegos"]
    for g in r["juegos"]:
        assert g["precio_usd"] <= 15 and "macOS" in g["plataformas"]
    assert r["candidatos_tras_filtros"] < len(catalog)


def test_filtros_se_aplican_antes_de_ordenar_no_despues(tools):
    # Con un filtro muy restrictivo debe devolver k resultados válidos aunque los más
    # parecidos globalmente no cumplan el filtro (si filtrara después, sobrarían menos).
    r = tools.execute("buscar_similares", {"descripcion": "farm", "k": 5, "precio_max": 5})
    assert r["devueltos"] == min(5, r["candidatos_tras_filtros"])
    assert all(g["precio_usd"] <= 5 for g in r["juegos"])


def test_similares_sin_candidatos_tras_filtros(tools):
    r = tools.execute("buscar_similares", {"descripcion": "anything", "precio_max": 0, "tags": ["Horror"]})
    assert r["ok"] and r["juegos"] == [] and r["candidatos_tras_filtros"] == 0 and "aviso" in r


@pytest.mark.parametrize("args", [{}, {"descripcion": ""}, {"descripcion": "   "}, {"descripcion": "x" * 600}])
def test_similares_valida_la_descripcion(tools, args):
    r = tools.execute("buscar_similares", args)
    assert r["ok"] is False and r["tipo_error"] == "argumentos_invalidos"


def test_similares_sin_indice_devuelve_error_controlado(catalog):
    sin_indice = GameTools(catalog)  # no hay índice asociado y no se puede cargar
    sin_indice._index_error = "No existe el índice de embeddings."
    r = sin_indice.execute("buscar_similares", {"descripcion": "farm"})
    assert r["ok"] is False and r["tipo_error"] == "indice_no_disponible"


def test_similares_error_de_embeddings_es_controlado(catalog):
    class Roto(HashEmbedder):
        def embed_query(self, text):
            raise ConnectionError("sin red")

    emb = HashEmbedder()
    t = GameTools(catalog, EmbeddingIndex.build(catalog, emb), Roto())
    r = t.execute("buscar_similares", {"descripcion": "farm"})
    assert r["ok"] is False and r["tipo_error"] == "error_embeddings" and "sin red" in r["mensaje"]


# ------------------------------------------------------------- detalle_juego
def test_detalle_encuentra_sin_distinguir_mayusculas_ni_signos(tools):
    for nombre in ("Turnip Hollow", "turnip hollow", "  TURNIP   HOLLOW "):
        r = tools.execute("detalle_juego", {"nombre": nombre})
        assert r["encontrado"] and r["juego"]["precio_usd"] == 9.99
    assert set(r["juego"]["plataformas"]) == {"Windows", "macOS"}


def test_detalle_titulo_inexistente_no_inventa(tools):
    r = tools.execute("detalle_juego", {"nombre": "Zorblax Prime Odyssey"})
    assert r["ok"] and r["encontrado"] is False and "juego" not in r and r["sugerencias"] == []


def test_detalle_sugiere_titulos_reales_si_hay_error_tipografico(tools, catalog):
    r = tools.execute("detalle_juego", {"nombre": "Willowbrok Farm"})
    assert r["encontrado"] is False and r["sugerencias"] == ["Willowbrook Farm"]
    assert all(catalog.find_by_name(s) is not None for s in r["sugerencias"])


def test_detalle_no_acepta_coincidencias_aproximadas_como_si_fueran_exactas(tools):
    assert tools.execute("detalle_juego", {"nombre": "Farm"})["encontrado"] is False


def test_detalle_exige_nombre(tools):
    assert tools.execute("detalle_juego", {})["tipo_error"] == "argumentos_invalidos"
    assert tools.execute("detalle_juego", {"nombre": ""})["tipo_error"] == "argumentos_invalidos"


# ------------------------------------------------------------ calcular_total
def test_total_suma_precios_del_catalogo(tools):
    r = tools.execute("calcular_total", {"nombres": ["Willowbrook Farm", "Turnip Hollow", "Beehive Buddies"]})
    assert r["total_usd"] == 30.97 and r["promedio_usd"] == 10.32 and r["completo"] is True
    assert [g["precio_usd"] for g in r["juegos"]] == [14.99, 9.99, 5.99]


def test_total_sin_errores_de_coma_flotante():
    df = pd.DataFrame({
        "app_id": [1, 2, 3], "name": ["A", "B", "C"], "description": ["a", "b", "c"],
        "genres": ["Indie"] * 3, "tags": ["Indie"] * 3, "price": [0.1, 0.2, 0.3],
        "windows": [True] * 3, "mac": [False] * 3, "linux": [False] * 3,
        "positive": [1, 1, 1], "negative": [0, 0, 0], "release_date": ["2020-01-01"] * 3,
    })
    r = GameTools(Catalog(df)).execute("calcular_total", {"nombres": ["A", "B", "C"]})
    assert r["total_usd"] == 0.6  # 0.1 + 0.2 + 0.3 en flotante sería 0.6000000000000001


def test_total_con_titulos_no_encontrados_es_parcial_y_lo_indica(tools):
    r = tools.execute("calcular_total", {"nombres": ["Hexa Wars", "Juego Que No Existe"]})
    assert r["total_usd"] == 4.99 and r["completo"] is False
    assert r["no_encontrados"][0]["nombre_buscado"] == "Juego Que No Existe" and "aviso" in r


def test_total_ninguno_encontrado(tools):
    r = tools.execute("calcular_total", {"nombres": ["No Existe 1", "No Existe 2"]})
    assert r["ok"] and r["total_usd"] is None and r["promedio_usd"] is None and r["cantidad_encontrados"] == 0


def test_total_ignora_duplicados_y_lo_informa(tools):
    r = tools.execute("calcular_total", {"nombres": ["Hexa Wars", "hexa wars"]})
    assert r["total_usd"] == 4.99 and r["duplicados_ignorados"] == ["Hexa Wars"]


def test_total_juegos_gratis(tools):
    r = tools.execute("calcular_total", {"nombres": ["Sandcastle Architects"]})
    assert r["total_usd"] == 0.0 and r["completo"] is True


@pytest.mark.parametrize("args", [{}, {"nombres": []}, {"nombres": 5}, {"nombres": ["A"] * 21}, {"nombres": [""]}])
def test_total_valida_argumentos(tools, args):
    r = tools.execute("calcular_total", args)
    assert r["ok"] is False and r["tipo_error"] == "argumentos_invalidos"


def test_total_no_acepta_precios_ni_expresiones_del_modelo(tools):
    r = tools.execute("calcular_total", {"nombres": ["Hexa Wars"], "precios": [1.0]})
    assert r["ok"] is False and "precios" in r["mensaje"]
    r = tools.execute("calcular_total", {"expresion": "4.99 + 9.99"})
    assert r["ok"] is False


# ----------------------------------------------------------------- ejecución
def test_execute_acepta_json_como_texto(tools):
    r = tools.execute("detalle_juego", json.dumps({"nombre": "Hexa Wars"}))
    assert r["encontrado"] is True
    assert tools.execute("detalle_juego", "")["tipo_error"] == "argumentos_invalidos"  # falta 'nombre'


def test_execute_json_invalido_y_herramienta_desconocida(tools):
    assert tools.execute("buscar_juegos", "{no es json")["tipo_error"] == "argumentos_invalidos"
    assert tools.execute("buscar_juegos", "[1, 2]")["tipo_error"] == "argumentos_invalidos"
    r = tools.execute("herramienta_inventada", {})
    assert r["tipo_error"] == "herramienta_desconocida" and "buscar_juegos" in r["herramientas_disponibles"]


def test_execute_nunca_propaga_excepciones_internas(catalog, monkeypatch):
    t = GameTools(catalog)
    monkeypatch.setattr(t.catalog, "find_by_name", lambda n: 1 / 0)
    r = t.execute("detalle_juego", {"nombre": "x"})
    assert r["ok"] is False and r["tipo_error"] == "error_interno"


def test_todos_los_resultados_son_serializables_a_json(tools):
    casos = [
        ("buscar_juegos", {"plataforma": "linux"}),
        ("buscar_similares", {"descripcion": "horror in the dark"}),
        ("detalle_juego", {"nombre": "Hexa Wars"}),
        ("calcular_total", {"nombres": ["Hexa Wars", "Nada"]}),
    ]
    for nombre, args in casos:
        json.dumps(tools.execute(nombre, args))


def test_esquemas_coinciden_con_las_firmas_de_las_herramientas(tools):
    import inspect

    for spec in TOOL_SCHEMAS:
        fn = spec["function"]
        params = set(inspect.signature(tools._registry[fn["name"]]).parameters)
        declared = set(fn["parameters"]["properties"])
        assert declared == params, fn["name"]
        assert set(fn["parameters"].get("required", [])) <= declared


# --------------------------------- orden por relevancia de etiquetas (error real del caso 1)
def _tagged_catalog(rows):
    """rows: (nombre, etiquetas en orden de votos, reseñas positivas)."""
    return Catalog(pd.DataFrame({
        "app_id": range(len(rows)), "name": [r[0] for r in rows], "description": ["x"] * len(rows),
        "genres": ["Action"] * len(rows), "tags": ["|".join(r[1]) for r in rows], "price": [5.0] * len(rows),
        "windows": [True] * len(rows), "mac": [False] * len(rows), "linux": [False] * len(rows),
        "positive": [r[2] for r in rows], "negative": [0] * len(rows), "release_date": ["2020-01-01"] * len(rows),
    }))


RELLENO = [f"T{i}" for i in range(20)]


def test_nivel_de_etiquetas_segun_la_peor_posicion():
    tags = ["Zombies", "Co-op", "FPS", "Multiplayer", "Shooter"] + RELLENO
    assert Catalog.tag_tier(tags, ["Shooter", "Co-op"]) == 0          # posiciones 5 y 2
    assert Catalog.tag_tier(RELLENO[:6] + ["Co-op"], ["co-op"]) == 1  # posición 7, sin distinguir mayúsculas
    assert Catalog.tag_tier(RELLENO[:11] + ["Co-op"], ["Co-op"]) == 2  # posición 12
    assert Catalog.tag_tier(tags, ["No existe"]) == 2
    assert Catalog.tag_tier(tags, []) == 0 and Catalog.tag_tier(tags, None) == 0


def test_etiqueta_relevante_gana_a_popularidad_y_popularidad_desempata():
    # Caso 1 real: CS2 (Co-op en la posición 12, 7,6 M reseñas) salía antes que L4D2 (Co-op 2.ª).
    cat = _tagged_catalog([
        ("Competitivo popular", ["FPS", "Shooter"] + RELLENO[:9] + ["Co-op"], 7_000_000),
        ("Coop clasico", ["Zombies", "Co-op", "FPS", "Multiplayer", "Shooter"], 900_000),
        ("Coop pequeno", ["Co-op", "Shooter"], 30_000),
        ("Coop medio", ["Shooter"] + RELLENO[:5] + ["Co-op"], 500_000),
    ])
    r = GameTools(cat).execute("buscar_juegos", {"tags": ["Shooter", "Co-op"]})
    assert names(r) == ["Coop clasico", "Coop pequeno", "Coop medio", "Competitivo popular"]
    assert r["total_coincidencias"] == 4 and "etiquetas" in r["orden"]


def test_sin_etiquetas_el_orden_sigue_siendo_por_popularidad():
    cat = _tagged_catalog([("A", ["X"], 10), ("B", ["Y"], 30), ("C", ["Z"], 20)])
    r = GameTools(cat).execute("buscar_juegos", {})
    assert names(r) == ["B", "C", "A"] and r["orden"].startswith("por número de reseñas")
