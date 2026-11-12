"""Ciclo del agente: el modelo decide qué herramienta usar y la aplicación la ejecuta.

Flujo (README, sección 6):
  1. Se envía al modelo el mensaje, el historial reciente y los esquemas de las herramientas.
  2. Si el modelo pide herramientas, la aplicación las valida/ejecuta, registra cada llamada
     (nombre, argumentos, resultado) y devuelve los resultados al modelo.
  3. El ciclo termina cuando el modelo responde sin pedir herramientas o cuando pide más llamadas
     de las permitidas. En ese caso se hace una última consulta SIN herramientas para que
     responda con lo reunido y advierta que la búsqueda quedó incompleta.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config
from catalog import Catalog
from tools import GameTools, TOOL_SCHEMAS

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Eres un asistente que ayuda a descubrir videojuegos de un catálogo de Steam. El catálogo es una \
captura fija de datos, no una consulta en tiempo real. Respondes en el idioma del usuario \
(por defecto, español).

Reglas obligatorias:
1. Solo recomiendas, describes o das precios de juegos que las herramientas hayan devuelto en \
esta conversación. Los precios (USD) y los sistemas operativos salen siempre del resultado de \
las herramientas. Nunca completes datos con conocimiento propio sobre un juego.
2. Elige la herramienta según la solicitud:
   - buscar_juegos: condiciones exactas (género, etiquetas, precio máximo, plataforma).
   - buscar_similares: descripciones libres o sensaciones ("relajante", "parecido a un juego de \
granja"). Si el usuario además da precio máximo, sistema operativo, género o etiquetas, pásalos \
como filtros en esa misma llamada. Escribe su argumento 'descripcion' en inglés, porque las \
descripciones del catálogo están en inglés.
   - detalle_juego: ficha de un título concreto (precio, sistemas, géneros, reseñas).
   - calcular_total: costo conjunto de varios juegos. Usa títulos exactos, tomados de resultados \
previos o del usuario. Nunca sumes ni promedies precios tú mismo: usa la herramienta.
3. "Plataforma" significa sistema operativo de PC: Windows, macOS o Linux. El catálogo no incluye \
consolas ni otras tiendas.
4. Si una herramienta no devuelve resultados o informa un error, dilo con claridad y no inventes \
alternativas. Puedes relajar un filtro y reintentar si aún te quedan llamadas, indicándolo. \
Si un título no está en el catálogo, di que no está.
5. Lee los campos 'aviso', 'sugerencias' y 'no_encontrados' de los resultados: si el total no \
incluye algún juego, dilo.
6. Dispones de un máximo de {MAX} llamadas a herramientas por solicitud: planifica pocas llamadas. \
Si no alcanzas a terminar, responde con lo reunido y di explícitamente que la búsqueda quedó incompleta.
7. Sé breve y claro. Por cada juego recomendado indica nombre, precio en USD y sistemas operativos. \
Cuando des precios, añade una sola vez una nota breve: son los del catálogo y pueden diferir de los \
actuales de Steam.
8. No puedes comprar juegos ni consultar precios en tiempo real, reseñas completas o cuentas de \
usuarios. Si te piden algo ajeno a descubrir videojuegos, explica amablemente que no puedes ayudar con eso.
"""


@dataclass
class ToolCallRecord:
    n: int
    id: str
    name: str
    arguments: Any  # dict si el JSON era válido; si no, el texto recibido
    result: dict
    ok: bool
    duration_ms: int

    def to_dict(self) -> dict:
        return {
            "n": self.n, "id": self.id, "name": self.name, "arguments": self.arguments,
            "ok": self.ok, "duration_ms": self.duration_ms, "result": self.result,
        }


@dataclass
class AgentResult:
    answer: str
    trace: list[ToolCallRecord] = field(default_factory=list)
    max_tool_calls: int = config.MAX_TOOL_CALLS
    limit_reached: bool = False
    error: str | None = None

    @property
    def tool_calls_used(self) -> int:
        return len(self.trace)

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "tool_calls_used": self.tool_calls_used,
            "max_tool_calls": self.max_tool_calls,
            "limit_reached": self.limit_reached,
            "error": self.error,
            "trace": [r.to_dict() for r in self.trace],
        }


def _content_to_text(content: Any) -> str:
    """Gradio puede entregar el contenido como texto o como lista de bloques."""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


class Agent:
    def __init__(
        self,
        client: Any,
        tools: GameTools,
        model: str | None = None,
        max_tool_calls: int | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ):
        self.client = client
        self.tools = tools
        self.model = model or config.LLM_MODEL
        self.max_tool_calls = config.MAX_TOOL_CALLS if max_tool_calls is None else max_tool_calls
        self.temperature = temperature
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------ internos
    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT.replace("{MAX}", str(self.max_tool_calls))

    @staticmethod
    def _history_messages(history: list[dict] | None) -> list[dict]:
        """Solo texto de usuario/asistente: las llamadas a herramientas de turnos previos no se reenvían."""
        out: list[dict] = []
        for m in history or []:
            role = m.get("role")
            text = _content_to_text(m.get("content")).strip()
            if role in ("user", "assistant") and text:
                out.append({"role": role, "content": text})
        return out[-2 * config.MAX_HISTORY_TURNS :]

    def _chat(self, messages: list[dict], with_tools: bool = True, tool_choice: str = "auto") -> Any:
        kwargs: dict[str, Any] = dict(
            model=self.model, messages=messages, temperature=self.temperature, max_tokens=self.max_tokens
        )
        if with_tools:
            kwargs.update(tools=TOOL_SCHEMAS, tool_choice=tool_choice)
        return self.client.chat.completions.create(**kwargs).choices[0].message

    def _final_without_tools(self, messages: list[dict]) -> str:
        """Última consulta con las herramientas deshabilitadas (se alcanzó el límite)."""
        try:
            msg = self._chat(messages, with_tools=False)
        except Exception as exc:
            # Algunos servidores exigen 'tools' si el historial contiene llamadas a herramientas.
            log.info("Reintentando la respuesta final con tool_choice='none' (%s)", exc)
            msg = self._chat(messages, with_tools=True, tool_choice="none")
        return (getattr(msg, "content", "") or "").strip()

    def _limit_message(self) -> str:
        return json.dumps(
            {
                "ok": False,
                "tipo_error": "limite_de_llamadas",
                "mensaje": f"Se alcanzó el máximo de {self.max_tool_calls} llamadas a herramientas "
                "para esta solicitud; esta llamada NO se ejecutó.",
                "instruccion": "Responde ahora con la información reunida hasta aquí e indica "
                "explícitamente al usuario que la búsqueda quedó incompleta.",
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------ ciclo
    def run(self, user_message: str, history: list[dict] | None = None) -> AgentResult:
        messages: list[dict] = [{"role": "system", "content": self._system_prompt()}]
        messages += self._history_messages(history)
        messages.append({"role": "user", "content": user_message})
        trace: list[ToolCallRecord] = []
        limit_reached = False

        def result_with(answer: str, error: str | None = None) -> AgentResult:
            return AgentResult(answer, trace, self.max_tool_calls, limit_reached, error)

        try:
            while True:
                msg = self._chat(messages)
                raw_calls = list(getattr(msg, "tool_calls", None) or [])
                if not raw_calls:
                    answer = (getattr(msg, "content", "") or "").strip()
                    return result_with(answer or "El modelo no devolvió una respuesta. Intenta reformular tu solicitud.")

                calls = []
                for i, call in enumerate(raw_calls, start=1):
                    calls.append((
                        call.id or f"call_{len(trace) + i}",
                        call.function.name,
                        call.function.arguments if call.function.arguments is not None else "{}",
                    ))
                messages.append({
                    "role": "assistant",
                    "content": getattr(msg, "content", None) or "",
                    "tool_calls": [
                        {"id": cid, "type": "function",
                         "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}
                        for cid, name, args in calls
                    ],
                })

                for cid, name, raw_args in calls:
                    if len(trace) >= self.max_tool_calls:
                        limit_reached = True  # el modelo pidió más llamadas de las permitidas
                        content = self._limit_message()
                    else:
                        started = time.perf_counter()
                        result = self.tools.execute(name, raw_args)
                        elapsed = int((time.perf_counter() - started) * 1000)
                        try:
                            parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError:
                            parsed = raw_args
                        trace.append(ToolCallRecord(
                            n=len(trace) + 1, id=cid, name=name, arguments=parsed,
                            result=result, ok=bool(result.get("ok")), duration_ms=elapsed,
                        ))
                        content = json.dumps(result, ensure_ascii=False)
                        if len(content) > 20000:  # protección del contexto (no ocurre con los límites actuales)
                            content = content[:20000] + " …[resultado truncado]"
                    messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": content})

                if limit_reached:
                    return result_with(self._final_without_tools(messages))
        except Exception as exc:  # error de red/API: se informa, no se propaga
            log.exception("Fallo en el ciclo del agente")
            return result_with(
                f"No pude completar la solicitud por un error al comunicarme con el modelo "
                f"({type(exc).__name__}). Inténtalo de nuevo en unos segundos.",
                error=f"{type(exc).__name__}: {exc}",
            )


def build_agent(catalog_path: str | Path | None = None, client: Any = None) -> Agent:
    """Crea el agente con el catálogo por defecto y el cliente de NVIDIA NIM."""
    catalog = Catalog.load(catalog_path or config.default_catalog_path())
    tools = GameTools(catalog)
    if client is None:
        from openai import OpenAI

        client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=config.get_api_key(), max_retries=3, timeout=60)
    return Agent(client, tools)
