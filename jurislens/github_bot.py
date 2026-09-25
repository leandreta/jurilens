"""Bot de issues: alguém abre uma issue com um processo e o JurisLens responde na hora.

Lê o evento do GitHub Actions ($GITHUB_EVENT_PATH), extrai os dados e escreve o
comentário em Markdown num arquivo — quem publica é o `gh` no workflow. O corpo da
issue nunca é interpolado em shell: só é lido aqui, como dado.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path

from . import hybrid, llm, redact, synth
from .normalize import norm_value
from .schema import FIELDS

MAX_CHARS = 15_000
BADGES = {"regra": "🧮 regra", "ia": "🤖 IA", "regra+ia": "🔗 regra + IA", "descartado": "🚫 descartado",
          "ausente": "➖ ausente"}
LABELS = {
    "numero_processo": "Número CNJ", "classe": "Classe", "orgao_julgador": "Órgão julgador", "uf": "UF",
    "valor_causa": "Valor da causa", "assunto": "Assunto", "autor_nome": "Autor", "autor_documento": "CPF/CNPJ autor",
    "reu_nome": "Réu", "reu_documento": "CPF/CNPJ réu", "advogado_nome": "Advogado(a)", "advogado_oab": "OAB",
    "data_audiencia": "Data da audiência", "hora_audiencia": "Hora da audiência",
    "justica_gratuita": "Justiça gratuita",
}


def parse_issue_body(body: str) -> tuple[str, str]:
    """Retorna (modo, texto). Entende o formulário de issue e texto colado solto."""
    body = body or ""
    wants_sample = bool(re.search(r"gerar um processo sint[eé]tico|/exemplo", body, re.I))
    m = re.search(r"### Texto do processo\s*\n(.*?)(?:\n### |\Z)", body, re.S)
    text = (m.group(1) if m else body).strip()
    text = re.sub(r"^```\w*\n?|\n?```$", "", text).strip()
    if text in ("_No response_", ""):
        text = ""
    if wants_sample or not text:
        return "sintetico", ""
    return "colado", text[:MAX_CHARS]


def fmt(field: str, value) -> str:
    if value is None:
        return "—"
    if field == "valor_causa":
        return f"R$ {synth.fmt_brl(value)}"
    if field == "justica_gratuita":
        return "sim" if value else "não"
    if field.endswith("_documento"):
        return f"`{redact.mask_doc(value)}`"
    return f"`{value}`"


def render(mode: str, text: str, result: hybrid.HybridResult, truth: dict | None) -> str:
    out = ["### 🔎 JurisLens — resultado da extração", ""]
    if mode == "sintetico":
        out += ["Você não colou um texto, então gerei **um processo 100% sintético** (nomes e documentos "
                "fictícios, com dígito verificador válido) e extraí os dados dele. O texto está no fim deste "
                "comentário.", ""]
    header = "| Campo | Valor extraído | Origem |" + (" Gabarito |" if truth else "")
    out += [header, "|---|---|---|" + ("---|" if truth else "")]
    hits = 0
    for f in FIELDS:
        row = f"| {LABELS[f]} | {fmt(f, result.data.get(f))} | {BADGES[result.source.get(f, 'ausente')]} |"
        if truth:
            ok = result.data.get(f) == truth.get(f)
            hits += bool(ok)
            row += " ✅ |" if ok else f" ❌ {fmt(f, truth.get(f))} |"
        out.append(row)
    out.append("")
    ai = llm.available()
    stats = [f"campos resolvidos por regra: **{sum(v == 'regra' for v in result.source.values())}/{len(FIELDS)}**"]
    if result.llm_fields:
        stats.append(f"IA consultada para: `{', '.join(result.llm_fields)}`")
        stats.append(f"custo desta extração: **US$ {result.cost_usd:.4f}**")
    elif ai:
        stats.append("IA **não precisou** ser chamada (custo US$ 0)")
    if truth:
        stats.append(f"acerto vs gabarito: **{hits}/{len(FIELDS)}**")
    out.append(" · ".join(stats))
    if result.rejected:
        out += ["", f"> 🚫 A validação descartou {len(result.rejected)} valor(es) sugerido(s) pela IA que não "
                    "passaram no dígito verificador ou não aparecem no documento: "
                    f"`{', '.join(result.rejected)}`. Melhor vazio do que inventado."]
    if not ai:
        out += ["", "> ℹ️ Rodando em modo **só regras** (o secret `ANTHROPIC_API_KEY` não está configurado)."]
    if result.llm_error:
        out += ["", f"> ⚠️ A chamada à IA falhou (`{result.llm_error[:120]}`); mantive o que as regras acharam."]
    repo = os.getenv("GITHUB_REPOSITORY", "")
    how = f" [Como funciona?](https://github.com/{repo}#como-funciona)" if repo else ""
    out += ["", f"CPFs e CNPJs aparecem mascarados (LGPD).{how}"]
    if mode == "sintetico":
        out += ["", "<details><summary>📄 Texto do processo sintético</summary>", "", "```text", text, "```",
                "", "</details>"]
    return "\n".join(out)


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    mode, text = parse_issue_body(issue.get("body") or "")
    truth = None
    if mode == "sintetico":
        case = synth.generate(1, seed=random.SystemRandom().randint(0, 10**9))[0]
        text, truth = case.text, {k: norm_value(k, v) for k, v in case.truth.items()}
    result = hybrid.extract(text)
    body = render(mode, text, result, truth)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "comment.md")
    out.write_text(body, encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
