"""Pruebas de la interfaz: se invoca el manejador real de Gradio con un agente simulado."""
from __future__ import annotations

import json

import pytest

import config
from agent import Agent
from app import create_demo, render_trace
from conftest import FakeClient, llm_message, tool_call


def _respond_fn(demo):
    # El primer evento del textbox es el manejador `respond`
    return next(f for f in demo.fns.values() if getattr(f.fn, "__name__", "") == "respond").fn


def _run(fn, message, history=None):
    return list(fn(message, history or []))


def test_render_trace_vacio_y_con_llamadas(tools):
    assert "0 / 5" in render_trace(None)
    script = [llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "<b>Hexa</b>"}, "i")]), llm_message("ok")]
    result = Agent(FakeClient(script), tools).run("x")
    html = render_trace(result)
    assert "1 / 5" in html and "detalle_juego" in html and "no encontrado" in html
    assert "<b>Hexa</b>" not in html and "&lt;b&gt;Hexa&lt;/b&gt;" in html  # el contenido se escapa


def test_flujo_completo_actualiza_chat_y_traza(tools):
    script = [
        llm_message(tool_calls=[tool_call("buscar_juegos", {"precio_max": 5}, "a")]),
        llm_message("Hay varias opciones baratas."),
    ]
    demo = create_demo(lambda: Agent(FakeClient(script), tools))
    steps = _run(_respond_fn(demo), "algo barato")
    assert len(steps) == 2  # estado "pendiente" y resultado final
    assert "Consultando" in steps[0][2]
    box, history, trace = steps[-1]
    assert box == "" and [m["role"] for m in history] == ["user", "assistant"]
    assert history[-1]["content"] == "Hay varias opciones baratas."
    assert "buscar_juegos" in trace and "1 / 5" in trace


def test_sin_clave_se_muestra_mensaje_claro_en_el_chat():
    def sin_clave():
        raise config.ConfigError("Falta NVIDIA_API_KEY.")

    steps = _run(_respond_fn(create_demo(sin_clave)), "hola")
    assert "Falta NVIDIA_API_KEY" in steps[-1][1][-1]["content"]


def test_mensaje_vacio_no_llama_al_agente():
    def no_deberia_llamarse():
        raise AssertionError("no debe construir el agente")

    steps = _run(_respond_fn(create_demo(no_deberia_llamarse)), "   ")
    assert steps[-1][1] == []


def test_aviso_de_limite_visible_si_el_modelo_no_lo_menciona(tools):
    def script(kwargs, n):
        if "tools" in kwargs:
            return llm_message(tool_calls=[tool_call("detalle_juego", {"nombre": "Hexa Wars"}, f"c{n}")])
        return llm_message("Aquí tienes lo que encontré.")

    agent = Agent(FakeClient(script), tools, max_tool_calls=2)
    steps = _run(_respond_fn(create_demo(lambda: agent)), "x")
    assert "Búsqueda incompleta" in steps[-1][1][-1]["content"]
    assert "2 / 5" not in steps[-1][2]  # el contador usa el máximo del resultado
    assert "2 / 2" in steps[-1][2] and "límite" in steps[-1][2]


def test_la_demo_se_construye_y_sirve_la_pagina(tools):
    demo = create_demo(lambda: Agent(FakeClient([llm_message("hola")]), tools), info="prueba")
    app, url, _ = demo.launch(prevent_thread_lock=True, quiet=True, server_port=None)
    try:
        import urllib.request

        body = urllib.request.urlopen(url, timeout=10).read().decode()
        assert "gradio" in body.lower()
    finally:
        demo.close()
