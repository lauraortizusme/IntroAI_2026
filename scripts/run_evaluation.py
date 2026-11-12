"""Ejecuta los 6 casos de prueba del README (sección 11) con el agente real y guarda la evidencia.

Requiere NVIDIA_API_KEY. Para cada caso guarda: respuesta, herramientas llamadas, argumentos y
resultados (traza completa) y unos chequeos objetivos. La valoración final (correcto / parcial /
incorrecto) y su justificación son MANUALES: el informe queda con esos campos en blanco.

Uso:
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --only 3,5 --catalog data/catalog.csv

Salida: results/evaluacion_<fecha>.json y results/evaluacion_<fecha>.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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


def run_cases(agent: Agent, catalog: Catalog, only: set[int] | None = None) -> list[dict]:
    rows = []
    for case in build_cases(catalog):
        if only and case.n not in only:
            continue
        print(f"[{case.n}] {case.solicitud[:90]}")
        result = agent.run(case.solicitud)
        rows.append({
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
    args = parser.parse_args()

    catalog_path = args.catalog or config.default_catalog_path()
    catalog = Catalog.load(catalog_path)
    if args.recheck:
        print(f"Chequeos recalculados: {recheck(args.recheck, catalog)}")
        return
    try:
        agent = build_agent(catalog_path)
    except config.ConfigError as exc:
        sys.exit(f"ERROR: {exc}")
    only = {int(x) for x in args.only.split(",") if x.strip()} or None
    rows = run_cases(agent, catalog, only)

    meta = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "catalogo": catalog_path.name,
        "n_juegos": len(catalog), "modelo": agent.model, "max_llamadas": agent.max_tool_calls,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (args.out / f"evaluacion_{stamp}.json").write_text(
        json.dumps({"meta": meta, "casos": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out / f"evaluacion_{stamp}.md").write_text(to_markdown(rows, meta), encoding="utf-8")
    print(f"\nEvidencia guardada en {args.out}/evaluacion_{stamp}.(json|md)")


if __name__ == "__main__":
    main()
