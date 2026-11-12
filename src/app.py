"""Interfaz web (Gradio): conversación + panel de trazabilidad de las herramientas.

Uso:
    python src/app.py              # local
    python src/app.py --share      # enlace público temporal de Gradio
    python src/app.py --catalog data/catalog.csv
"""
from __future__ import annotations

import argparse
import html
import inspect
import json
import logging
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gradio as gr  # noqa: E402

import config  # noqa: E402
from agent import Agent, AgentResult, build_agent  # noqa: E402
from catalog import Catalog  # noqa: E402

TITLE = "Asistente conversacional para descubrir videojuegos"
LIMIT_NOTICE = "⚠️ *Búsqueda incompleta: se alcanzó el límite de {n} llamadas a herramientas por solicitud.*"

_TRACE_CSS = """
<style>
.tr-box{font-size:14px;line-height:1.45}
.tr-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-weight:600}
.tr-count{padding:2px 10px;border-radius:999px;border:1px solid var(--border-color-primary);background:var(--background-fill-secondary)}
.tr-count.full{border-color:#d97706;color:#d97706}
.tr-warn{margin:6px 0;padding:8px 10px;border-radius:8px;border:1px solid #d97706;color:#d97706}
.tr-call{border:1px solid var(--border-color-primary);border-radius:8px;margin:6px 0;padding:6px 10px;background:var(--background-fill-secondary)}
.tr-call summary{cursor:pointer;font-weight:600}
.tr-ok{color:#16a34a}.tr-err{color:#dc2626}
.tr-sub{font-weight:600;margin:8px 0 2px;font-size:12px;opacity:.8}
.tr-call pre{white-space:pre-wrap;word-break:break-word;max-height:260px;overflow:auto;margin:0;padding:6px;border-radius:6px;background:var(--background-fill-primary);font-size:12px}
.tr-empty{opacity:.7}
</style>
"""


def _pretty(obj) -> str:
    return html.escape(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def render_trace(result: AgentResult | None, pending: bool = False, max_calls: int | None = None) -> str:
    """HTML del panel de trazabilidad para la última solicitud."""
    limit = max_calls if max_calls is not None else (result.max_tool_calls if result else config.MAX_TOOL_CALLS)
    used = result.tool_calls_used if result else 0
    full = "full" if used >= limit else ""
    parts = [
        _TRACE_CSS,
        '<div class="tr-box">',
        f'<div class="tr-head"><span>Traza de herramientas</span>'
        f'<span class="tr-count {full}">Llamadas: {used} / {limit}</span></div>',
    ]
    if pending:
        parts.append('<div class="tr-empty">Consultando al modelo…</div>')
    elif result is None:
        parts.append('<div class="tr-empty">Aquí aparecerán las herramientas que use el agente, '
                     'con sus argumentos y resultados.</div>')
    else:
        if result.error:
            parts.append(f'<div class="tr-warn">Error de comunicación con el modelo: {html.escape(result.error)}</div>')
        if result.limit_reached:
            parts.append(f'<div class="tr-warn">Se alcanzó el límite de {limit} llamadas: '
                         "el modelo respondió con la información reunida (búsqueda incompleta).</div>")
        if not result.trace and not result.error:
            parts.append('<div class="tr-empty">El modelo respondió sin usar herramientas.</div>')
        for rec in result.trace:
            status = '<span class="tr-ok">✓ ok</span>' if rec.ok else '<span class="tr-err">✗ error</span>'
            extra = ""
            res = rec.result
            if rec.ok and isinstance(res.get("total_coincidencias"), int):
                extra = f" · {res['total_coincidencias']} coincidencias"
            elif rec.ok and res.get("encontrado") is False:
                extra = " · no encontrado"
            elif not rec.ok:
                extra = f" · {html.escape(str(res.get('tipo_error', '')))}"
            parts.append(
                '<details class="tr-call">'
                f"<summary>#{rec.n} {html.escape(rec.name)} — {status}{extra} · {rec.duration_ms} ms</summary>"
                '<div class="tr-sub">Argumentos</div>'
                f"<pre>{_pretty(rec.arguments)}</pre>"
                '<div class="tr-sub">Resultado</div>'
                f"<pre>{_pretty(rec.result)}</pre>"
                "</details>"
            )
    parts.append("</div>")
    return "".join(parts)


def create_demo(
    agent_provider: Callable[[], Agent],
    info: str = "",
    example_game: str | None = None,
) -> gr.Blocks:
    """Construye la interfaz. ``agent_provider`` puede lanzar ConfigError (p. ej., sin clave de API)."""
    game = example_game or "[nombre de un juego del catálogo]"
    examples = [
        "Un shooter cooperativo por menos de 10 USD",
        "Quiero algo para relajarme",
        "Recomiéndame tres juegos de granja y dime cuánto cuestan juntos",
        "Busca juegos relajantes por menos de 15 USD en Mac y calcula cuánto cuestan los dos primeros",
        f"¿En qué sistemas operativos funciona {game} y cuánto cuesta?",
    ]
    max_calls = config.MAX_TOOL_CALLS

    def respond(message: str, history: list[dict]):
        message = (message or "").strip()
        history = list(history or [])
        if not message:
            yield "", history, render_trace(None, max_calls=max_calls)
            return
        previous = list(history)
        history.append({"role": "user", "content": message})
        yield "", history, render_trace(None, pending=True, max_calls=max_calls)
        try:
            agent = agent_provider()
        except config.ConfigError as exc:
            history.append({"role": "assistant", "content": f"⚠️ {exc}"})
            yield "", history, render_trace(None, max_calls=max_calls)
            return
        result = agent.run(message, previous)
        answer = result.answer
        if result.limit_reached and "incompleta" not in answer.lower():
            answer += "\n\n" + LIMIT_NOTICE.format(n=result.max_tool_calls)
        history.append({"role": "assistant", "content": answer})
        yield "", history, render_trace(result)

    chatbot_kwargs = dict(label="Conversación", height=480)
    if "type" in inspect.signature(gr.Chatbot.__init__).parameters:  # Gradio < 6 requiere type="messages"
        chatbot_kwargs["type"] = "messages"

    with gr.Blocks(title=TITLE) as demo:
        gr.Markdown(f"## 🎮 {TITLE}\n{info}")
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(**chatbot_kwargs)
                box = gr.Textbox(
                    placeholder="Cuéntame qué tipo de juego buscas…", show_label=False, lines=1, max_lines=4
                )
                with gr.Row():
                    send = gr.Button("Enviar", variant="primary")
                    clear = gr.Button("Limpiar conversación")
                gr.Examples(examples=examples, inputs=box, label="Ejemplos de consultas")
            with gr.Column(scale=2):
                trace = gr.HTML(render_trace(None, max_calls=max_calls))
        outputs = [box, chatbot, trace]
        box.submit(respond, [box, chatbot], outputs)
        send.click(respond, [box, chatbot], outputs)
        clear.click(lambda: ("", [], render_trace(None, max_calls=max_calls)), None, outputs)
    return demo


def build_demo(catalog_path: str | Path | None = None) -> gr.Blocks:
    """Demo lista para lanzar con el catálogo indicado (o el predeterminado) y NVIDIA NIM."""
    path = Path(catalog_path) if catalog_path else config.default_catalog_path()
    catalog = Catalog.load(path)
    top = catalog.df.sort_values("positive", ascending=False).iloc[0]["name"]
    is_sample = path.name == "sample_games.csv"
    info = (
        f"Catálogo: `{path.name}` ({len(catalog)} juegos) · Modelo: `{config.LLM_MODEL}` · "
        f"Máximo {config.MAX_TOOL_CALLS} llamadas a herramientas por solicitud."
    )
    if is_sample:
        info += "\n\n> ⚠️ Catálogo de **muestra con juegos ficticios**: sirve para probar, no son datos de Steam."
    cache: dict[str, Agent] = {}

    def provider() -> Agent:
        if "agent" not in cache:
            cache["agent"] = build_agent(path)
        return cache["agent"]

    return create_demo(provider, info=info, example_game=top)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--share", action="store_true", help="crear enlace público temporal de Gradio")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    try:
        config.get_api_key()
    except config.ConfigError as exc:
        print(f"AVISO: {exc}\nLa interfaz se abrirá, pero no podrá responder hasta configurar la clave.\n")
    build_demo(args.catalog).launch(share=args.share, server_port=args.port)


if __name__ == "__main__":
    main()
