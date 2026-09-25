"""Benchmark contínuo: mede regras, IA pura e híbrido contra o gabarito sintético.

Gera `results/latest.json`, anexa ao histórico, desenha `results/benchmark.svg`
e reescreve o bloco entre os marcadores <!-- BENCH:START/END --> do README.
Roda toda semana no GitHub Actions — o README se atualiza sozinho.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from . import hybrid, llm, rules, synth
from .normalize import norm_value
from .schema import FIELDS

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DATASET = ROOT / "data" / "synthetic.jsonl"
README = ROOT / "README.md"

LABELS = {"regras": "Só regras (regex)", "ia": "Só IA (Claude)", "hibrido": "Híbrido JurisLens"}


def score(pred: dict, truth: dict) -> dict[str, bool]:
    return {f: norm_value(f, pred.get(f)) == norm_value(f, truth.get(f)) for f in FIELDS}


def run_strategy(name: str, cases: list[synth.SyntheticCase]) -> dict:
    per_field = {f: 0 for f in FIELDS}
    by_layout: dict[str, list[float]] = {}
    perfect = 0
    cost = 0.0
    latencies = []
    llm_calls = 0
    errors = 0
    for c in cases:
        t0 = time.perf_counter()
        if name == "regras":
            pred = rules.extract(c.text)
        elif name == "ia":
            r = llm.extract(c.text)
            pred, cost = r.data, cost + r.cost_usd
            llm_calls += 1
            errors += bool(r.error)
        else:
            r = hybrid.extract(c.text, use_llm=llm.available())
            pred, cost = r.data, cost + r.cost_usd
            llm_calls += bool(r.llm_fields)
            errors += bool(r.llm_error)
        latencies.append(time.perf_counter() - t0)
        s = score(pred, c.truth)
        for f, ok in s.items():
            per_field[f] += ok
        acc = sum(s.values()) / len(FIELDS)
        by_layout.setdefault(c.layout, []).append(acc)
        perfect += acc == 1.0
    n = len(cases)
    return {
        "strategy": name,
        "n": n,
        "field_accuracy": round(sum(per_field.values()) / (n * len(FIELDS)), 4),
        "perfect_docs": round(perfect / n, 4),
        "per_field": {f: round(v / n, 4) for f, v in per_field.items()},
        "by_layout": {k: round(statistics.mean(v), 4) for k, v in sorted(by_layout.items())},
        "cost_per_1k_docs_usd": round(cost / n * 1000, 2),
        "llm_call_rate": round(llm_calls / n, 4),
        "llm_errors": errors,
        "p50_latency_s": round(statistics.median(latencies), 3),
    }


def run(n: int = 90, llm_sample: int = 30, seed: int = 2026) -> dict:
    cases = synth.load(DATASET) if DATASET.exists() else synth.generate(n, seed)
    cases = cases[:n]
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "dataset": {"n": len(cases), "seed": seed, "layouts": sorted({c.layout for c in cases})},
        "model": llm.DEFAULT_MODEL if llm.available() else None,
        "results": [run_strategy("regras", cases)],
    }
    if llm.available():
        # Mesma amostra para IA pura e híbrido, para a comparação ser justa.
        sample = cases[:llm_sample]
        report["llm_sample"] = len(sample)
        report["results"] += [run_strategy("ia", sample), run_strategy("hibrido", sample)]
    return report


# ---------- saída ----------

def svg_chart(report: dict) -> str:
    rows = report["results"]
    fields = FIELDS
    colors = {"regras": "#94a3b8", "ia": "#a78bfa", "hibrido": "#22c55e"}
    w, row_h, left = 760, 22, 170
    h = 70 + len(fields) * row_h + 40
    bar_w = (w - left - 30) / 1.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
             'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="12">',
             f'<rect width="{w}" height="{h}" rx="12" fill="#0f172a"/>',
             '<text x="20" y="30" fill="#f8fafc" font-size="16" font-weight="600">'
             'Acurácia por campo — processos sintéticos</text>']
    lx = 20
    for r in rows:
        c = colors[r["strategy"]]
        parts.append(f'<rect x="{lx}" y="44" width="10" height="10" rx="2" fill="{c}"/>'
                     f'<text x="{lx + 15}" y="53" fill="#cbd5e1">{LABELS[r["strategy"]]} '
                     f'({r["field_accuracy"]:.0%})</text>')
        lx += 210
    sub_h = (row_h - 6) / max(len(rows), 1)
    for i, f in enumerate(fields):
        y = 70 + i * row_h
        parts.append(f'<text x="{left - 8}" y="{y + row_h / 2 + 2}" fill="#cbd5e1" text-anchor="end">{f}</text>')
        parts.append(f'<rect x="{left}" y="{y + 2}" width="{bar_w}" height="{row_h - 4}" fill="#1e293b" rx="3"/>')
        for j, r in enumerate(rows):
            v = r["per_field"][f]
            parts.append(f'<rect x="{left}" y="{y + 3 + j * sub_h:.1f}" width="{bar_w * v:.1f}" '
                         f'height="{sub_h:.1f}" fill="{colors[r["strategy"]]}" rx="2"/>')
    parts.append(f'<text x="20" y="{h - 14}" fill="#64748b">Atualizado automaticamente em '
                 f'{report["generated_at"]} · n={report["dataset"]["n"]}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def markdown(report: dict) -> str:
    lines = [
        f"_Última execução: **{report['generated_at']}** · {report['dataset']['n']} processos sintéticos "
        f"· layouts: {', '.join(report['dataset']['layouts'])}_",
        "",
        "| Estratégia | Acurácia por campo | Documentos 100% corretos | Chamadas à IA | Custo / 1 mil docs |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in report["results"]:
        lines.append(f"| {LABELS[r['strategy']]} | **{r['field_accuracy']:.1%}** | {r['perfect_docs']:.1%} "
                     f"| {r['llm_call_rate']:.0%} | US$ {r['cost_per_1k_docs_usd']:.2f} |")
    if not report.get("model"):
        lines += ["", "> As linhas de IA aparecem quando o secret `ANTHROPIC_API_KEY` está configurado "
                      "no repositório — o workflow semanal preenche sozinho."]
    else:
        lines += ["", f"> IA e híbrido medidos numa amostra de {report.get('llm_sample')} documentos "
                      f"com `{report['model']}`."]
    lines += ["", "![benchmark](results/benchmark.svg)"]
    return "\n".join(lines)


def write(report: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    history_path = RESULTS / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as f:
        slim = {"at": report["generated_at"], "model": report["model"],
                **{r["strategy"]: r["field_accuracy"] for r in report["results"]},
                **{f"{r['strategy']}_cost_1k": r["cost_per_1k_docs_usd"] for r in report["results"]}}
        f.write(json.dumps(slim, ensure_ascii=False) + "\n")
    (RESULTS / "benchmark.svg").write_text(svg_chart(report), encoding="utf-8")
    site_data = ROOT / "site" / "data"
    if site_data.parent.exists():
        site_data.mkdir(exist_ok=True)
        (site_data / "latest.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    if README.exists():
        text = README.read_text(encoding="utf-8")
        start, end = "<!-- BENCH:START -->", "<!-- BENCH:END -->"
        if start in text and end in text:
            head, rest = text.split(start, 1)
            _, tail = rest.split(end, 1)
            README.write_text(f"{head}{start}\n{markdown(report)}\n{end}{tail}", encoding="utf-8")
