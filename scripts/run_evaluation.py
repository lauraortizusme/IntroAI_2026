"""Ejecuta los 6 casos de prueba del README (sección 6, detalle en docs/pruebas_y_evaluacion.md) con el agente real y guarda la evidencia.

Requiere NVIDIA_API_KEY. Para cada caso guarda: respuesta, herramientas llamadas, argumentos y
resultados (traza completa) y unos chequeos objetivos. La valoración final (correcto / parcial /
incorrecto) y su justificación son MANUALES: el informe queda con esos campos en blanco.

Uso:
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --only 3,5 --catalog data/catalog.csv
    python scripts/run_evaluation.py --baseline          # mismas solicitudes, mismo modelo, SIN herramientas
    python scripts/run_evaluation.py --metrics results/a.json results/b.json   # tabla de métricas, sin API

Salida: results/evaluacion_<fecha>.json/.md, results/linea_base_<fecha>.json/.md y
results/metricas_<fecha>.md (con --metrics).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
from agent import Agent, AgentResult, build_agent  # noqa: E402
from catalog import Catalog, normalize_text  # noqa: E402

ABSENT_TITLE = "Zorblax Prime Odyssey"  # título inventado: no debe existir en el catálogo


@dataclass
class Case:
    n: int
    categoria: str
    solicitud: str
    esperado: str


def build_cases(catalog: Catalog) -> list[Case]:
    top = catalog.df.sort_values("positive", ascending=False)["name"].tolist()
    if catalog.find_by_name(ABSENT_TITLE) is not None:
        raise ValueError(f"'{ABSENT_TITLE}' existe en el catálogo; elige otro título ausente para el caso 5.")
    siete = ", ".join(top[:7])
    return [
        Case(1, "Habitual: filtros", "Un shooter cooperativo por menos de 10 USD",
             "Los resultados cumplen los filtros disponibles en el catálogo."),
        Case(2, "Habitual: semántica", "Quiero algo para relajarme",
             "Las recomendaciones son coherentes con la descripción y aparecen en los resultados de la herramienta."),
        Case(3, "Habitual: combinada", "Recomiéndame tres juegos de granja y dime cuánto cuestan juntos",
             "Se identifican los juegos y el total coincide con la suma de sus precios en el catálogo."),
        Case(4, "Consulta que requiere herramienta", f"¿En qué sistemas operativos funciona {top[0]} y cuánto cuesta?",
             "La ficha coincide con los datos del catálogo."),
        Case(5, "Caso límite", f"¿Cuánto cuesta {ABSENT_TITLE}?",
             "El agente reconoce que no encuentra el título y no inventa información."),
        Case(6, "Prueba adicional: límite de llamadas",
             f"Consulta por separado la ficha de cada uno de estos siete juegos y dime los sistemas operativos de cada uno: {siete}",
             "El agente responde con lo reunido e informa que la búsqueda quedó incompleta."),
    ]


def titles_in_results(trace) -> set[str]:
    """Títulos del catálogo que aparecieron en algún resultado de herramienta (traza como dicts)."""
    found: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            for key in ("nombre", "nombre_buscado"):
                if isinstance(obj.get(key), str):
                    found.add(obj[key])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for rec in trace:
        walk(rec["result"] if isinstance(rec, dict) else rec.result)
    return found


def mentioned_titles(answer: str, catalog: Catalog) -> list[str]:
    """Títulos del catálogo mencionados en la respuesta.

    Evita dos falsos positivos observados en la evaluación real (2026-11-11):
    - un título contenido dentro de otro más largo también mencionado ("Counter-Strike" dentro de
      "Counter-Strike 2") solo cuenta si aparece además por separado;
    - un título de una sola palabra debe coincidir con sus mayúsculas exactas ("UNO" no es "cada uno").
    """
    norm = " " + normalize_text(answer) + " "
    spans: dict[str, list[tuple[int, int]]] = {}
    for name in catalog.df["name"]:
        t = normalize_text(name)
        if not t:
            continue
        if " " not in t and not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", answer):
            continue
        needle, start, hits = f" {t} ", 0, []
        while (i := norm.find(needle, start)) != -1:
            hits.append((i + 1, i + len(needle) - 1))
            start = i + 1
        if hits:
            spans[name] = hits
    mentioned = []
    for name, hits in spans.items():
        others = [s for other, ss in spans.items() if other != name for s in ss]
        if any(not any(o[0] <= a and b <= o[1] and (o[1] - o[0]) > (b - a) for o in others) for a, b in hits):
            mentioned.append(name)
    return mentioned


def objective_checks(case: Case | int, result: AgentResult | dict, catalog: Catalog) -> dict:
    """Ayudas automáticas para la valoración; NO reemplazan la revisión manual.

    Acepta el resultado del agente o su versión guardada en JSON (``AgentResult.to_dict()``).
    """
    n = case if isinstance(case, int) else case.n
    res = result.to_dict() if isinstance(result, AgentResult) else result
    answer, trace = res["answer"], res["trace"]
    mentioned = mentioned_titles(answer, catalog)
    returned = {normalize_text(t) for t in titles_in_results(trace)}
    checks: dict = {
        "titulos_del_catalogo_mencionados": mentioned,
        "mencionados_sin_respaldo_en_herramientas": [m for m in mentioned if normalize_text(m) not in returned],
        "herramientas_llamadas": [r["name"] for r in trace],
        "llamadas_con_error": [r["n"] for r in trace if not r["ok"]],
        "limite_alcanzado": res["limit_reached"],
    }
    totals = [r["result"].get("total_usd") for r in trace if r["name"] == "calcular_total" and r["ok"]]
    if totals and totals[-1] is not None:
        total = float(totals[-1])
        variants = {f"{total:.2f}", f"{total:.2f}".replace(".", ","), f"{total:g}"}
        checks["total_de_la_herramienta_usd"] = total
        checks["total_aparece_en_la_respuesta"] = any(v in answer for v in variants)
    if n == 5:
        checks["el_titulo_ausente_no_esta_en_el_catalogo"] = catalog.find_by_name(ABSENT_TITLE) is None
        checks["la_herramienta_no_lo_encontro"] = any(
            r["name"] in ("detalle_juego", "calcular_total") and (
                r["result"].get("encontrado") is False or r["result"].get("no_encontrados")) for r in trace
        )
    if n == 6:
        checks["se_ejecutaron_exactamente_el_maximo_de_llamadas"] = res["tool_calls_used"] == res["max_tool_calls"]
        checks["respuesta_menciona_que_quedo_incompleta"] = "incomplet" in answer.lower()
    return checks


def recheck(json_path: Path, catalog: Catalog) -> Path:
    """Recalcula los chequeos objetivos de una evaluación guardada, SIN llamar a la API.

    Conserva los chequeos anteriores en ``chequeos_originales`` y regenera el .md hermano.
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for row in data["casos"]:
        row.setdefault("chequeos_originales", row["chequeos"])
        row["chequeos"] = objective_checks(row["caso"], row["resultado"], catalog)
    data["meta"]["chequeos_recalculados"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path = json_path.with_suffix(".md")
    md_path.write_text(to_markdown(data["casos"], data["meta"]), encoding="utf-8")
    return md_path


# ----------------------------------------------------------------- métricas comparables
BASELINE_PROMPT = (
    "Eres un asistente que recomienda videojuegos de Steam. Respondes en el idioma del usuario "
    "(por defecto, español). Sé breve y claro. Por cada juego recomendado indica nombre, precio en USD "
    "y sistemas operativos."
)

_AMOUNT = re.compile(
    r"(?:US\$|\$|USD)\s?(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s?(?:USD|US\$|\$|d[oó]lares)", re.I)
# Negrita al inicio de un elemento de lista, de una fila de tabla o de un encabezado numerado:
# así enumeran los juegos los modelos ("- **Stardew Valley** — 8.99 USD", "| **Journey** | ...").
_LISTED = re.compile(r"^\s*(?:[-*•]|\d+[.)]|\||#{1,6}\s*\d+[.)])\s*\*\*(.+?)\*\*", re.M)


def amounts(text: str) -> list[float]:
    """Importes en USD escritos en el texto ("1.99 USD", "$11.24", "8,99 USD"...)."""
    return [float((a or b).replace(",", ".")) for a, b in _AMOUNT.findall(text)]


def proposed_titles(answer: str) -> list[str]:
    """Juegos que la respuesta enumera: texto en negrita al inicio de un elemento de lista, una fila
    de tabla o un encabezado numerado. Se descartan rótulos ("Total:", "Juego") e importes. Es una
    heurística: la lista se guarda para revisarla a mano."""
    out: list[str] = []
    for raw in _LISTED.findall(answer):
        s = raw.strip(" -–—*_")
        if (not s or s.endswith((":", "?")) or amounts(s) or len(s.split()) > 8
                or s.lower() in ("total", "nota", "juego", "precio")):
            continue
        if s not in out:
            out.append(s)
    return out


def in_catalog(title: str, catalog: Catalog) -> bool:
    """El título existe en el catálogo: coincidencia exacta normalizada, o es el comienzo de un título
    del catálogo seguido de un subtítulo ("Leaf Blower Revolution" → "Leaf Blower Revolution - Idle Game")."""
    if catalog.find_by_name(title) is not None:
        return True
    norm = normalize_text(title)
    return bool(norm) and catalog.df["_name_norm"].str.startswith(norm + " ").any()


def answer_metrics(answer: str, request: str, catalog: Catalog, tool_totals: tuple = ()) -> dict:
    """Métricas que se calculan igual para el agente y para la línea base sin herramientas.

    - títulos propuestos que no existen en el catálogo (coincidencia exacta normalizada);
    - importes en USD que no coinciden con el catálogo: cada línea con un importe debe nombrar un
      juego del catálogo con ese precio, o el importe debe ser la suma o el promedio de los precios
      del catálogo de los juegos mencionados (o el total / promedio de calcular_total), o repetir un
      importe de la propia solicitud ("menos de 10 USD").
    """
    propuestos = proposed_titles(answer)
    fuera = [s for s in propuestos if not in_catalog(s, catalog)]
    mencionados = mentioned_titles(answer, catalog)
    price = {n: float(catalog.find_by_name(n)["price"]) for n in mencionados}
    totales = {round(sum(price.values()), 2)} if price else set()
    if price:
        totales.add(round(sum(price.values()) / len(price), 2))  # promedio
    totales |= {round(float(v), 2) for v in tool_totals if v is not None}
    de_la_solicitud = set(amounts(request))
    revisados, sin_respaldo = 0, []
    for line in answer.splitlines():
        found = amounts(line)
        if not found:
            continue
        en_linea = {round(price[n], 2) for n in mentioned_titles(line, catalog) if n in price}
        for a in found:
            revisados += 1
            if not (round(a, 2) in en_linea or round(a, 2) in totales or a in de_la_solicitud):
                sin_respaldo.append({"importe": a, "linea": line.strip()[:160]})
    return {
        "titulos_propuestos": propuestos,
        "titulos_fuera_del_catalogo": fuera,
        "titulos_del_catalogo_mencionados": mencionados,
        "importes_revisados": revisados,
        "importes_que_no_coinciden_con_el_catalogo": sin_respaldo,
    }


def run_baseline(client, model: str, catalog: Catalog, only: set[int] | None = None,
                 temperature: float = 0.2, max_tokens: int = 1024, stop_after_timeouts: int = 2) -> list[dict]:
    """Línea base: las mismas solicitudes al mismo modelo, sin herramientas ni catálogo.

    Si los ``stop_after_timeouts`` primeros casos agotan el tiempo de espera, se detiene (no gasta más
    peticiones en una API que no responde) y lo registra en las filas."""
    rows = []
    for case in build_cases(catalog):
        if only and case.n not in only:
            continue
        if stop_after_timeouts and len(rows) >= stop_after_timeouts and all(
                "Timeout" in (r["error"] or "") for r in rows[:stop_after_timeouts]):
            print(f"Los {stop_after_timeouts} primeros casos agotaron el tiempo: se detiene la línea base.")
            break
        print(f"[base {case.n}] {case.solicitud[:90]}")
        started = time.perf_counter()
        error = finish = None
        try:
            choice = client.chat.completions.create(
                model=model, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": BASELINE_PROMPT}, {"role": "user", "content": case.solicitud}],
            ).choices[0]
            finish = getattr(choice, "finish_reason", None)
            answer = (getattr(choice.message, "content", "") or "").strip()
        except Exception as exc:  # se registra; no se reintenta en bucle
            answer, error = "", f"{type(exc).__name__}: {exc}"
        rows.append({
            "caso": case.n, "categoria": case.categoria, "solicitud": case.solicitud, "respuesta": answer,
            "error": error, "finish_reason": finish, "segundos": round(time.perf_counter() - started, 1),
            "metricas": answer_metrics(answer, case.solicitud, catalog),
        })
    return rows


def baseline_markdown(rows: list[dict], meta: dict) -> str:
    out = ["# Línea base sin herramientas", "",
           f"- Fecha: {meta['fecha']} · Modelo: `{meta['modelo']}` (el mismo del agente, temperatura {meta['temperatura']})",
           f"- Catálogo de referencia para las métricas: `{meta['catalogo']}` ({meta['n_juegos']} juegos)",
           "- Las mismas solicitudes que el agente, sin herramientas ni acceso al catálogo.", "",
           f"**Prompt de sistema:** {BASELINE_PROMPT}", ""]
    for r in rows:
        out += [f"## Caso {r['caso']} — {r['categoria']}", "", f"**Solicitud:** {r['solicitud']}", "",
                f"**Tiempo de respuesta:** {r['segundos']} s" + (f" · **Error:** {r['error']}" if r["error"] else ""), "",
                "**Respuesta:**", "", *[f"> {line}" for line in r["respuesta"].splitlines() or [""]], "",
                "**Métricas automáticas** (heurísticas; revisar a mano):", "", "```json",
                json.dumps(r["metricas"], ensure_ascii=False, indent=2), "```", "", "---", ""]
    return "\n".join(out)


def tool_totals_of(trace: list[dict]) -> tuple:
    return tuple(r["result"].get(k) for r in trace if r["name"] == "calcular_total" and r["ok"]
                 for k in ("total_usd", "promedio_usd"))


def metrics_table(paths: list[Path], catalog: Catalog) -> str:
    """Tabla de métricas por caso de evaluaciones del agente y líneas base guardadas (sin API)."""
    out = ["| Archivo | Caso | Llamadas | Títulos propuestos | Fuera del catálogo | Sin respaldo en herramientas |"
           " Importes revisados | Importes que no coinciden |", "|---|---|---|---|---|---|---|---|"]
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data["casos"]:
            if "resultado" in row:  # evaluación del agente
                res = row["resultado"]
                m = answer_metrics(res["answer"], row["solicitud"], catalog, tool_totals_of(res["trace"]))
                llamadas = str(res["tool_calls_used"])
                sin_resp = str(len(objective_checks(row["caso"], res, catalog)["mencionados_sin_respaldo_en_herramientas"]))
            else:  # línea base
                if not row["respuesta"].strip():
                    motivo = row.get("error") or f"respuesta vacía (finish_reason={row.get('finish_reason')})"
                    out.append(f"| `{path.name}` | {row['caso']} | 0 | sin respuesta: {motivo.split(':')[0]} | — | — | — | — |")
                    continue
                m = answer_metrics(row["respuesta"], row["solicitud"], catalog)
                llamadas, sin_resp = "0", "—"
            out.append(f"| `{path.name}` | {row['caso']} | {llamadas} | {len(m['titulos_propuestos'])} | "
                       f"{len(m['titulos_fuera_del_catalogo'])} | {sin_resp} | {m['importes_revisados']} | "
                       f"{len(m['importes_que_no_coinciden_con_el_catalogo'])} |")
    return "\n".join(out)


def run_cases(agent: Agent, catalog: Catalog, only: set[int] | None = None) -> list[dict]:
    rows = []
    for case in build_cases(catalog):
        if only and case.n not in only:
            continue
        print(f"[{case.n}] {case.solicitud[:90]}")
        started = time.perf_counter()
        result = agent.run(case.solicitud)
        rows.append({
            "segundos": round(time.perf_counter() - started, 1),
            "caso": case.n, "categoria": case.categoria, "solicitud": case.solicitud, "esperado": case.esperado,
            "resultado": result.to_dict(), "chequeos": objective_checks(case, result, catalog),
            "valoracion": "", "justificacion": "",
        })
        print(f"     {result.tool_calls_used} llamadas, límite={result.limit_reached}, error={result.error}")
    return rows


def to_markdown(rows: list[dict], meta: dict) -> str:
    out = [
        "# Evidencia de la evaluación manual", "",
        f"- Fecha: {meta['fecha']}", f"- Catálogo: `{meta['catalogo']}` ({meta['n_juegos']} juegos)",
        f"- Modelo: `{meta['modelo']}` · Máximo de llamadas: {meta['max_llamadas']}",
        *([f"- Chequeos objetivos recalculados sin llamar a la API: {meta['chequeos_recalculados']}"]
          if meta.get("chequeos_recalculados") else []), "",
        "> Los chequeos objetivos son una ayuda; la valoración final es manual.", "",
    ]
    for r in rows:
        res = r["resultado"]
        out += [
            f"## Caso {r['caso']} — {r['categoria']}", "", f"**Solicitud:** {r['solicitud']}", "",
            f"**Resultado esperado:** {r['esperado']}", "",
            f"**Llamadas a herramientas ({res['tool_calls_used']}/{res['max_tool_calls']}):**", "",
        ]
        if not res["trace"]:
            out.append("- (ninguna)")
        for t in res["trace"]:
            out.append(f"- #{t['n']} `{t['name']}` {'✓' if t['ok'] else '✗'} — argumentos: `{json.dumps(t['arguments'], ensure_ascii=False)}`")
        out += ["", "**Respuesta del agente:**", "", *[f"> {line}" for line in res["answer"].splitlines() or [""]], "",
                "**Chequeos objetivos:**", "", "```json", json.dumps(r["chequeos"], ensure_ascii=False, indent=2), "```", "",
                "**Valoración:** ☐ correcto ☐ parcial ☐ incorrecto", "", "**Justificación:** _(completar)_", "", "---", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--only", default="", help="números de caso separados por comas, p. ej. 3,5")
    parser.add_argument("--out", type=Path, default=config.ROOT / "results")
    parser.add_argument("--recheck", type=Path, default=None,
                        help="recalcula los chequeos de un results/evaluacion_*.json existente (sin API)")
    parser.add_argument("--baseline", action="store_true",
                        help="ejecuta las mismas solicitudes con el mismo modelo pero SIN herramientas (línea base)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="segundos por petición en --baseline (el cliente reintenta hasta 3 veces)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="reintentos del cliente por petición en --baseline")
    parser.add_argument("--metrics", type=Path, nargs="+", default=None,
                        help="tabla de métricas de evaluaciones / líneas base guardadas (sin API)")
    args = parser.parse_args()

    catalog_path = args.catalog or config.default_catalog_path()
    catalog = Catalog.load(catalog_path)
    if args.recheck:
        print(f"Chequeos recalculados: {recheck(args.recheck, catalog)}")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.metrics:
        table = metrics_table(args.metrics, catalog)
        args.out.mkdir(parents=True, exist_ok=True)
        out = args.out / f"metricas_{stamp}.md"
        out.write_text(f"# Métricas comparables (generado {stamp}, sin API)\n\nCatálogo: `{catalog_path.name}`\n\n"
                       f"{table}\n", encoding="utf-8")
        print(table, f"Guardado en {out}", sep="\n")
        return
    only = {int(x) for x in args.only.split(",") if x.strip()} or None
    if args.baseline:
        from openai import OpenAI

        try:
            client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=config.get_api_key(),
                            max_retries=args.max_retries, timeout=args.timeout)
        except config.ConfigError as exc:
            sys.exit(f"ERROR: {exc}")
        rows = run_baseline(client, config.LLM_MODEL, catalog, only)
        meta = {"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "catalogo": catalog_path.name,
                "n_juegos": len(catalog), "modelo": config.LLM_MODEL, "temperatura": 0.2,
                "timeout_s": args.timeout, "max_retries": args.max_retries}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"linea_base_{stamp}.json").write_text(
            json.dumps({"meta": meta, "casos": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
        (args.out / f"linea_base_{stamp}.md").write_text(baseline_markdown(rows, meta), encoding="utf-8")
        print(f"Línea base guardada en {args.out}/linea_base_{stamp}.(json|md)")
        return
    try:
        agent = build_agent(catalog_path)
    except config.ConfigError as exc:
        sys.exit(f"ERROR: {exc}")
    rows = run_cases(agent, catalog, only)

    meta = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "catalogo": catalog_path.name,
        "n_juegos": len(catalog), "modelo": agent.model, "max_llamadas": agent.max_tool_calls,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"evaluacion_{stamp}.json").write_text(
        json.dumps({"meta": meta, "casos": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out / f"evaluacion_{stamp}.md").write_text(to_markdown(rows, meta), encoding="utf-8")
    print(f"\nEvidencia guardada en {args.out}/evaluacion_{stamp}.(json|md)")


if __name__ == "__main__":
    main()
