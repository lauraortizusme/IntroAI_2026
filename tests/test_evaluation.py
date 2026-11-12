"""Verifica que el script de evaluación funcione de punta a punta con un LLM simulado.

Esto NO evalúa al modelo real: solo comprueba que los casos se construyen, se ejecutan y
que los chequeos objetivos y el informe se generan correctamente.
"""
from __future__ import annotations

import json

import run_evaluation as ev
from agent import Agent
from conftest import FakeClient, llm_message, tool_call


def test_los_seis_casos_se_construyen_con_titulos_reales_del_catalogo(catalog):
    casos = ev.build_cases(catalog)
    assert [c.n for c in casos] == [1, 2, 3, 4, 5, 6]
    top = catalog.df.sort_values("positive", ascending=False)["name"].iloc[0]
    assert top in casos[3].solicitud and ev.ABSENT_TITLE in casos[4].solicitud
    assert catalog.find_by_name(ev.ABSENT_TITLE) is None
    assert sum(n in casos[5].solicitud for n in catalog.df["name"]) >= 7


def test_ejecucion_completa_con_llm_simulado_y_chequeos(tools, catalog):
    def script(kwargs, n):
        user = next(m["content"] for m in reversed(kwargs["messages"]) if m["role"] == "user")
        pendiente = kwargs["messages"][-1]["role"] != "tool"
        if "tools" not in kwargs:
            return llm_message("Resultado parcial. La búsqueda quedó incompleta.")
        if "siete juegos" in user:  # caso 6: pide una ficha tras otra hasta agotar el límite
            return llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, f"s{n}")])
        if "Zorblax" in user and pendiente:
            return llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": ev.ABSENT_TITLE}, "z")])
        if "Zorblax" in user:
            return llm_message("Ese título no está en el catálogo.")
        if "granja" in user and pendiente:
            return llm_message(tool_calls=[tool_call("calcular_total", {"nombres": ["Willowbrook Farm", "Turnip Hollow"]}, "g")])
        if "granja" in user:
            return llm_message("Willowbrook Farm y Turnip Hollow cuestan 24.98 USD en total.")
        return llm_message("Hola.")

    agent = Agent(FakeClient(script), tools)
    rows = ev.run_cases(agent, catalog)
    por_caso = {r["caso"]: r for r in rows}
    assert len(rows) == 6

    c3 = por_caso[3]["chequeos"]
    assert c3["total_de_la_herramienta_usd"] == 24.98 and c3["total_aparece_en_la_respuesta"] is True
    assert c3["mencionados_sin_respaldo_en_herramientas"] == []

    c5 = por_caso[5]["chequeos"]
    assert c5["la_herramienta_no_lo_encontro"] and c5["el_titulo_ausente_no_esta_en_el_catalogo"]

    c6 = por_caso[6]["chequeos"]
    assert c6["se_ejecutaron_exactamente_el_maximo_de_llamadas"] and c6["limite_alcanzado"]
    assert c6["respuesta_menciona_que_quedo_incompleta"]

    meta = {"fecha": "hoy", "catalogo": "sample", "n_juegos": 43, "modelo": "sim", "max_llamadas": 5}
    md = ev.to_markdown(rows, meta)
    assert md.count("## Caso") == 6 and "☐ correcto ☐ parcial ☐ incorrecto" in md
    json.dumps(rows)


def test_detecta_titulos_recomendados_sin_respaldo_en_las_herramientas(tools, catalog):
    # El modelo recomienda "Hexa Wars" sin haber llamado a ninguna herramienta
    agent = Agent(FakeClient([llm_message("Te recomiendo Hexa Wars por 4.99 USD.")]), tools)
    rows = ev.run_cases(agent, catalog, only={2})
    assert rows[0]["chequeos"]["mencionados_sin_respaldo_en_herramientas"] == ["Hexa Wars"]


# --- Falsos positivos reales del chequeo "sin respaldo" (evaluación con el catálogo real, 2026-11-11)
def _cat(names):
    import pandas as pd
    from catalog import Catalog
    k = len(names)
    return Catalog(pd.DataFrame({
        "app_id": range(k), "name": names, "description": ["x"] * k, "genres": ["Action"] * k,
        "tags": ["Co-op"] * k, "price": [1.0] * k, "windows": [True] * k, "mac": [False] * k,
        "linux": [False] * k, "positive": [1] * k, "negative": [0] * k, "release_date": ["2020-01-01"] * k,
    }))


def test_titulo_contenido_en_otro_mas_largo_no_cuenta_salvo_que_aparezca_solo():
    cat = _cat(["Counter-Strike", "Counter-Strike 2", "Left 4 Dead", "Left 4 Dead 2"])
    assert ev.mentioned_titles("Counter-Strike 2 es gratis.", cat) == ["Counter-Strike 2"]
    # "Left 4 Dead" aparece también por separado: SÍ cuenta (caso 1 real)
    got = ev.mentioned_titles("Left 4 Dead 2 cuesta 1.99. Si buscas algo como Left 4 Dead, dime.", cat)
    assert sorted(got) == ["Left 4 Dead", "Left 4 Dead 2"]


def test_titulo_de_una_palabra_exige_mayusculas_exactas():
    cat = _cat(["UNO", "Journey", "Stardew Valley"])
    assert ev.mentioned_titles("Un poco de cada uno: Stardew Valley.", cat) == ["Stardew Valley"]
    assert sorted(ev.mentioned_titles("Prueba Journey o UNO.", cat)) == ["Journey", "UNO"]


def test_recheck_recalcula_desde_el_json_sin_api(tmp_path, catalog):
    res = {"answer": "Hexa Wars cuesta 4.99 USD; un poco de cada uno.", "tool_calls_used": 1, "max_tool_calls": 5,
           "limit_reached": False, "error": None,
           "trace": [{"n": 1, "id": "a", "name": "detalle_juego", "arguments": {"nombre": "Hexa Wars"}, "ok": True,
                      "duration_ms": 1, "result": {"ok": True, "encontrado": True, "juego": {"nombre": "Hexa Wars"}}}]}
    path = tmp_path / "evaluacion_x.json"
    viejo = {"mencionados_sin_respaldo_en_herramientas": ["dato viejo"]}
    path.write_text(json.dumps({"meta": {"fecha": "f", "catalogo": "c", "n_juegos": 1, "modelo": "m", "max_llamadas": 5},
                                "casos": [{"caso": 4, "categoria": "x", "solicitud": "s", "esperado": "e",
                                           "resultado": res, "chequeos": viejo}]}), encoding="utf-8")
    md = ev.recheck(path, catalog)
    data = json.loads(path.read_text(encoding="utf-8"))
    row = data["casos"][0]
    assert row["chequeos_originales"] == viejo
    assert row["chequeos"]["mencionados_sin_respaldo_en_herramientas"] == []
    assert row["chequeos"]["titulos_del_catalogo_mencionados"] == ["Hexa Wars"]
    assert "recalculados" in md.read_text(encoding="utf-8")
