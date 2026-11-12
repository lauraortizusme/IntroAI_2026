"""Pruebas del ciclo del agente con un LLM simulado (no usa red ni claves)."""
from __future__ import annotations

import json

from agent import Agent
from conftest import FakeClient, llm_message, tool_call


def make_agent(tools, script, **kw) -> tuple[Agent, FakeClient]:
    client = FakeClient(script)
    return Agent(client, tools, model="modelo-simulado", **kw), client


def tool_messages(request: dict) -> list[dict]:
    return [m for m in request["messages"] if m["role"] == "tool"]


def test_respuesta_directa_sin_herramientas(tools):
    agent, client = make_agent(tools, [llm_message("Hola, cuéntame qué tipo de juego buscas.")])
    r = agent.run("hola")
    assert r.answer.startswith("Hola") and r.trace == [] and not r.limit_reached and r.error is None
    assert client.requests[0]["tool_choice"] == "auto" and len(client.requests[0]["tools"]) == 4


def test_una_herramienta_y_respuesta_final_con_traza(tools):
    script = [
        llm_message(tool_calls=[tool_call("buscar_juegos", {"tags": ["Shooter", "Co-op"], "precio_max": 10}, "c1")]),
        llm_message("Te recomiendo Ashfall Squad (7.99 USD)."),
    ]
    agent, client = make_agent(tools, script)
    r = agent.run("Un shooter cooperativo por menos de 10 USD")
    assert r.answer.startswith("Te recomiendo") and r.tool_calls_used == 1
    rec = r.trace[0]
    assert rec.name == "buscar_juegos" and rec.arguments == {"tags": ["Shooter", "Co-op"], "precio_max": 10}
    assert rec.ok and rec.result["total_coincidencias"] > 0 and rec.id == "c1"
    # El modelo recibió el resultado real de la herramienta, asociado al id correcto
    segunda = client.requests[1]["messages"]
    assert segunda[-2]["role"] == "assistant" and segunda[-2]["tool_calls"][0]["id"] == "c1"
    assert segunda[-1]["role"] == "tool" and segunda[-1]["tool_call_id"] == "c1"
    assert "Ashfall Squad" in segunda[-1]["content"]


def test_solicitud_combinada_encadena_herramientas(tools):
    def script(kwargs, n):
        if n == 0:
            return llm_message(tool_calls=[tool_call("buscar_similares", {
                "descripcion": "relaxing game", "k": 2, "plataforma": "mac", "precio_max": 15}, "a")])
        if n == 1:
            res = json.loads(tool_messages(kwargs)[-1]["content"])
            nombres = [g["nombre"] for g in res["juegos"][:2]]
            return llm_message(tool_calls=[tool_call("calcular_total", {"nombres": nombres}, "b")])
        return llm_message("Listo.")

    agent, _ = make_agent(tools, script)
    r = agent.run("Busca juegos relajantes por menos de 15 USD en Mac y calcula cuánto cuestan los dos primeros")
    assert [t.name for t in r.trace] == ["buscar_similares", "calcular_total"]
    precios = [g["precio_usd"] for g in r.trace[0].result["juegos"][:2]]
    assert r.trace[1].result["total_usd"] == round(sum(precios), 2)  # el total proviene de la herramienta
    assert r.trace[1].result["cantidad_encontrados"] == 2


def test_argumentos_json_invalidos_vuelven_al_modelo_como_error_controlado(tools):
    script = [
        llm_message(tool_calls=[tool_call("detalle_juego", "{nombre: Hexa Wars", "x")]),
        llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, "y")]),
        llm_message("Hexa Wars cuesta 4.99 USD."),
    ]
    agent, _ = make_agent(tools, script)
    r = agent.run("precio de Hexa Wars")
    assert [t.ok for t in r.trace] == [False, True]
    assert r.trace[0].arguments == "{nombre: Hexa Wars"  # se conserva el texto recibido para la traza
    assert r.trace[0].result["tipo_error"] == "argumentos_invalidos"
    assert "4.99" in r.answer and not r.limit_reached


def test_titulo_inexistente_se_comunica_y_se_registra(tools):
    script = [
        llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Zorblax Prime Odyssey"}, "z")]),
        llm_message("Ese título no está en el catálogo."),
    ]
    agent, _ = make_agent(tools, script)
    r = agent.run("¿Cuánto cuesta Zorblax Prime Odyssey?")
    assert r.trace[0].result["encontrado"] is False and "no está" in r.answer


def test_limite_de_cinco_llamadas_y_respuesta_final_sin_herramientas(tools):
    n_final = {}

    def script(kwargs, n):
        if "tools" in kwargs:  # el modelo insiste en pedir herramientas mientras pueda
            return llm_message(tool_calls=[tool_call("buscar_juegos", {"limite": 1, "genero": "Action"}, f"id{n}")])
        n_final["n"] = n
        return llm_message("Con lo reunido te sugiero Ashfall Squad. La búsqueda quedó incompleta.")

    agent, client = make_agent(tools, script)
    r = agent.run("Dame un juego de cada género con precios")
    assert r.tool_calls_used == 5 and r.limit_reached and r.error is None
    assert "incompleta" in r.answer
    # 5 llamadas ejecutadas + 1 petición que pidió la sexta + 1 consulta final sin herramientas
    assert len(client.requests) == 7 and n_final["n"] == 6
    ultima = client.requests[-1]
    assert "tools" not in ultima and "tool_choice" not in ultima
    # la sexta llamada NO se ejecutó: el modelo recibió el aviso de límite
    aviso = json.loads(tool_messages(ultima)[-1]["content"])
    assert aviso["tipo_error"] == "limite_de_llamadas" and "incompleta" in aviso["instruccion"]


def test_llamadas_en_paralelo_que_exceden_el_limite(tools):
    calls = [tool_call("detalle_juego", {"nombre": "Hexa Wars"}, f"p{i}") for i in range(4)]
    script = {0: llm_message(tool_calls=calls), 1: llm_message("Parcial. La búsqueda quedó incompleta.")}
    agent, client = make_agent(tools, lambda kw, n: script[n], max_tool_calls=2)
    r = agent.run("consulta varias veces")
    assert r.tool_calls_used == 2 and r.limit_reached
    ids = [m["tool_call_id"] for m in tool_messages(client.requests[-1])]
    assert ids == ["p0", "p1", "p2", "p3"]  # todas las llamadas del modelo reciben respuesta


def test_exactamente_cinco_llamadas_sin_pedir_mas_no_es_incompleto(tools):
    def script(kwargs, n):
        if n < 5:
            return llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, f"k{n}")])
        return llm_message("Todo resuelto.")

    agent, _ = make_agent(tools, script)
    r = agent.run("x")
    assert r.tool_calls_used == 5 and not r.limit_reached and r.answer == "Todo resuelto."


def test_si_el_servidor_rechaza_la_consulta_final_sin_tools_se_reintenta_con_tool_choice_none(tools):
    def script(kwargs, n):
        if "tools" not in kwargs:
            return RuntimeError("tools requerido")
        if kwargs.get("tool_choice") == "none":
            return llm_message("Respuesta final. Búsqueda incompleta.")
        return llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, f"t{n}")])

    agent, client = make_agent(tools, script, max_tool_calls=1)
    r = agent.run("x")
    assert r.limit_reached and r.error is None and "incompleta" in r.answer
    assert client.requests[-1]["tool_choice"] == "none"


def test_error_del_modelo_no_rompe_la_aplicacion(tools):
    agent, _ = make_agent(tools, [ConnectionError("sin conexión")])
    r = agent.run("hola")
    assert r.error and "ConnectionError" in r.error and "error" in r.answer.lower() and r.trace == []


def test_respuesta_vacia_del_modelo_tiene_mensaje_de_respaldo(tools):
    agent, _ = make_agent(tools, [llm_message("")])
    assert "no devolvió" in agent.run("hola").answer


def test_historial_se_reenvia_solo_como_texto_y_acotado(tools):
    history = []
    for i in range(10):
        history += [{"role": "user", "content": f"pregunta {i}"},
                    {"role": "assistant", "content": [{"type": "text", "text": f"respuesta {i}"}]}]
    history.append({"role": "assistant", "content": "", "metadata": {"title": "vacío"}})
    agent, client = make_agent(tools, [llm_message("ok")])
    agent.run("nueva", history)
    enviados = client.requests[0]["messages"]
    assert enviados[0]["role"] == "system" and enviados[-1] == {"role": "user", "content": "nueva"}
    previos = enviados[1:-1]
    assert len(previos) == 12 and previos[-1]["content"] == "respuesta 9"  # 6 turnos × 2 mensajes
    assert all(isinstance(m["content"], str) and m["content"] for m in previos)


def test_el_prompt_del_sistema_incluye_el_limite_y_las_reglas_clave(tools):
    agent, client = make_agent(tools, [llm_message("ok")], max_tool_calls=5)
    agent.run("hola")
    prompt = client.requests[0]["messages"][0]["content"]
    assert "máximo de 5 llamadas" in prompt and "{MAX}" not in prompt
    assert "inglés" in prompt and "Nunca sumes" in prompt


def test_to_dict_es_serializable(tools):
    script = [llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, "q")]), llm_message("ok")]
    agent, _ = make_agent(tools, script)
    json.dumps(agent.run("x").to_dict())
