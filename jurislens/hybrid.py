"""Orquestrador híbrido: regras -> validação -> IA só onde precisa -> checagem anti-alucinação.

1. Regras extraem tudo que conseguem (custo zero).
2. Cada valor passa por validação formal (dígito verificador de CPF/CNPJ/CNJ, UF, datas…).
3. Só os campos vazios ou inválidos vão para o Claude, num prompt focado.
4. A resposta da IA também é validada e "ancorada": o valor precisa aparecer no documento.
   Valor que não passa é descartado — preferimos null a um dado inventado.
5. Se a IA já foi acionada, ela também audita textos livres que a regra truncou.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import llm, rules
from .normalize import clean_text
from .schema import FIELDS
from .validators import field_is_valid, only_digits

# Campos de texto livre: a regra pode capturar um valor truncado por quebra de linha do PDF.
FREE_TEXT = {"classe", "assunto", "orgao_julgador", "autor_nome", "reu_nome", "advogado_nome"}

# Campos que podem legitimamente não existir no documento (audiência ainda não marcada).
OPTIONAL = {"data_audiencia", "hora_audiencia"}


@dataclass
class HybridResult:
    data: dict
    source: dict  # campo -> "regra" | "ia" | "descartado" | "ausente"
    llm_fields: list[str] = field(default_factory=list)
    rejected: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    seconds: float = 0.0
    llm_error: str | None = None


def grounded(field_name: str, value, text: str) -> bool:
    """O valor proposto pela IA aparece de fato no texto? (evita alucinação)"""
    if value is None or isinstance(value, bool):
        return True
    t = clean_text(text)
    digits = only_digits(t)
    if field_name in ("numero_processo", "autor_documento", "reu_documento"):
        return only_digits(str(value)) in digits
    if field_name == "advogado_oab":
        return only_digits(str(value)) in digits
    if field_name == "valor_causa":
        cents = f"{value:.2f}".replace(".", "")
        return cents in digits or str(int(value)) in digits
    if field_name == "data_audiencia":
        y, m, d = str(value).split("-")
        return y in t and (f"{d}/{m}" in t or f"{d}.{m}" in t or re.search(rf"\b{int(d)} DE ", t) is not None)
    if field_name == "hora_audiencia":
        hh, mm = str(value).split(":")
        return re.search(rf"\b{int(hh)}\s*[:H]\s*{mm}" if mm != "00" else rf"\b{int(hh)}\s*[:H]", t) is not None
    joined = t.replace("\n", "")  # PDFs quebram palavras no meio: "PROCEDIME\nNTO"
    words = [w for w in re.split(r"\W+", clean_text(str(value))) if len(w) > 2]
    return bool(words) and sum(w in t or w in joined for w in words) / len(words) >= 0.8


def extract(text: str, use_llm: bool | None = None, client=None) -> HybridResult:
    start = time.perf_counter()
    base = rules.extract(text)
    source = {}
    pending = []
    for f in FIELDS:
        v = base.get(f)
        if field_is_valid(f, v):
            source[f] = "regra"
        else:
            base[f] = None
            pending.append(f)

    # Audiência ausente nos dois campos costuma ser "ainda não designada": só pergunta à IA se houver pista.
    if {"data_audiencia", "hora_audiencia"} <= set(pending) and "AUDIENCIA" not in clean_text(text).replace("\n", ""):
        pending = [f for f in pending if f not in OPTIONAL]
        source.update({f: "ausente" for f in OPTIONAL})

    result = HybridResult(data=base, source=source)
    use_llm = llm.available() if use_llm is None else use_llm
    if pending and use_llm:
        r = llm.extract(text, only_fields=pending, client=client)
        result.llm_fields = pending
        result.cost_usd = r.cost_usd
        result.llm_error = r.error
        # A IA já foi chamada: aproveita para auditar textos livres que a regra pode ter cortado.
        for f in FREE_TEXT - set(pending):
            v, mine = r.data.get(f), base.get(f)
            if v and mine and v != mine and mine in v and grounded(f, v, text):
                base[f] = v
                source[f] = "regra+ia"
        for f in pending:
            v = r.data.get(f)
            if v is None:
                source[f] = "ausente"
            elif field_is_valid(f, v) and grounded(f, v, text):
                base[f] = v
                source[f] = "ia"
            else:
                result.rejected[f] = v
                source[f] = "descartado"
    for f in pending:
        source.setdefault(f, "ausente")
    result.source = {f: source[f] for f in FIELDS}
    result.data = {f: base.get(f) for f in FIELDS}
    result.seconds = time.perf_counter() - start
    return result
