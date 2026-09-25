"""Extrator determinístico por regras (regex) — evolução da versão Flask original.

Rápido, gratuito e auditável. Acerta muito em layouts estruturados (capa do PJe,
intimações) e sofre em petições escritas em prosa livre. O extrator híbrido
usa essa diferença: regras primeiro, IA só no que as regras não resolveram.
"""

from __future__ import annotations

import re
from typing import Callable

from .normalize import clean_text, norm_value, parse_brl
from .validators import CNJ_RE, UFS, document_is_valid, format_cnj, only_digits

DOC = r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})"
NAME = r"([A-Z][A-Z .'&/-]{3,80}?)"


def _first(patterns: list[str], text: str, flags=0) -> str | None:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip(" .,;:-—")
    return None


def numero_processo(t: str) -> str | None:
    labelled = _first([r"(?:NUMERO|PROCESSO(?: N[O°º]\.?)?)\s*:?\s*(\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4})"], t)
    if labelled:
        return format_cnj(labelled)
    m = CNJ_RE.search(t)
    return format_cnj(m.group(0)) if m else None


def classe(t: str) -> str | None:
    return _first([r"CLASSE\s*:\s*([^\n]+?)(?:\s{2,}|\n|$)"], t)


def orgao_julgador(t: str) -> str | None:
    return _first([
        r"ORGAO JULGADOR\s*:\s*([^\n]+)",
        r"JUIZ\(A\) DE DIREITO DA ([^\n]+?)\s*[–-]\s*[A-Z]{2}\s*\n",
        r"^((?:\d+[ªº°A-Z]*\s+)?(?:VARA|JUIZADO|V DOS FEITOS)[^\n]+)$",
        r"(?:VARA|JUIZO)\s*:\s*([^\n]+)",
    ], t, re.M)


def uf(t: str) -> str | None:
    found = _first([r"\bTJ([A-Z]{2})\b", r"ESTADO\s*(?:DO|DA|DE)?\s*[—-]?\s*([A-Z]{2})\b",
                    r"DE DIREITO DA [^\n]+[–-]\s*([A-Z]{2})\s*\n", r"OAB\s*/?\s*([A-Z]{2})"], t)
    return found if found in UFS else None


def valor_causa(t: str) -> float | None:
    raw = _first([
        r"VALOR DA CAUSA\s*:?\s*R?\$?\s*([\d.,]+)",
        r"DA[-\s]?SE A CAUSA O VALOR DE\s*:?\s*R?\$?\s*([\d.,]+)",
        r"ATRIBUI[-\s]?SE A CAUSA O VALOR DE\s*:?\s*R?\$?\s*([\d.,]+)",
    ], t)
    return parse_brl(raw) if raw else None


def assunto(t: str) -> str | None:
    return _first([r"ASSUNTOS?\s*:\s*([^\n]+)"], t)


def _party(t: str, role_labels: list[str], role_suffix: str) -> tuple[str | None, str | None]:
    name = _first([rf"^{NAME}\s*\({role_suffix}\)"] + [rf"{lab}\s*:\s*{NAME}(?:\s+[—-]|\n|$)" for lab in role_labels],
                  t, re.M)
    doc = None
    doc_ctx = {"AUTOR": [r"AUTOR INSCRITO SOB O N[O°º]\s*" + DOC, r"REQUERENTE:[^\n]*?" + DOC],
               "REU": [r"REU INSCRITO SOB O N[O°º]\s*" + DOC, r"REQUERIDO:[^\n]*?" + DOC]}[role_suffix]
    raw = _first(doc_ctx, t)
    if raw and document_is_valid(raw):
        doc = only_digits(raw)
    return name, doc


def partes(t: str) -> dict:
    autor, autor_doc = _party(t, ["REQUERENTE", "AUTOR", "RECLAMANTE"], "AUTOR")
    reu, reu_doc = _party(t, ["REQUERIDO", "REU", "RECLAMADO"], "REU")
    if not autor:
        # Petição em prosa: "FULANO, brasileiro(a)..., vem ... propor"
        m = re.search(r"\n\s*(?!EM FACE DE)([A-Z][A-Z .]{5,80}),\s*(?:BRASILEIR|PESSOA JURIDICA)", t)
        autor = m.group(1).strip() if m else None
    if not reu:
        m = re.search(r"EM FACE DE\s+([A-Z][A-Z .&/-]{3,80}?),", t)
        reu = m.group(1).strip() if m else None
    if not autor_doc or not reu_doc:
        # Fallback posicional do código original: 1º documento válido = autor, 2º = réu.
        docs = [only_digits(d) for d in re.findall(DOC, t) if document_is_valid(d)]
        docs = list(dict.fromkeys(docs))
        if not autor_doc and docs:
            autor_doc = docs[0]
        if not reu_doc and len(docs) > 1:
            reu_doc = next((d for d in docs if d != autor_doc), None)
    return {"autor_nome": autor, "autor_documento": autor_doc, "reu_nome": reu, "reu_documento": reu_doc}


def advogado(t: str) -> dict:
    nome = _first([
        rf"^{NAME}\s*\(ADVOGADO\)",
        rf"ADVOGADO\(?S?\)?(?: DO (?:AUTOR|RECLAMANTE|REQUERENTE))?\s*:\s*{NAME}\s*\(",
        rf"\n{NAME}\nOAB\s*/",
    ], t, re.M)
    oab = None
    m = (re.search(r"OAB\s*/?\s*([A-Z]{2})\s*([\d.]{3,8})", t)
         or re.search(r"OAB\s*([\d.]{3,8})\s*/\s*([A-Z]{2})", t))
    if m:
        a, b = m.groups()
        uf_, num = (a, b) if a.isalpha() else (b, a)
        oab = f"{uf_}/{only_digits(num)}"
    return {"advogado_nome": nome, "advogado_oab": oab}


def audiencia(t: str) -> dict:
    m = re.search(r"AUDIENCIA[^\n]{0,60}?(\d{2})[/.](\d{2})[/.](\d{4})[^\n]{0,10}?(\d{1,2})[:H](\d{2})", t)
    if m:
        d, mo, y, hh, mm = m.groups()
        return {"data_audiencia": f"{y}-{mo}-{d}", "hora_audiencia": f"{int(hh):02d}:{mm}"}
    # Formas longas como "12 de março de 2025, às 14h30" ficam para a IA.
    return {"data_audiencia": None, "hora_audiencia": None}


def justica_gratuita(t: str) -> bool | None:
    if re.search(r"JUSTICA GRATUITA\?\s*SIM|GRATUIDADE DA JUSTICA\s*:\s*DEFERIDA|CONCESSAO DA GRATUIDADE", t):
        return True
    if re.search(r"JUSTICA GRATUITA\?\s*NAO|CUSTAS\s*:\s*RECOLHIDAS", t):
        return False
    return None


SCALAR: dict[str, Callable[[str], object]] = {
    "numero_processo": numero_processo,
    "classe": classe,
    "orgao_julgador": orgao_julgador,
    "uf": uf,
    "valor_causa": valor_causa,
    "assunto": assunto,
    "justica_gratuita": justica_gratuita,
}


def extract(text: str) -> dict:
    t = clean_text(text)
    out: dict = {}
    for field, fn in SCALAR.items():
        try:
            out[field] = fn(t)
        except Exception:  # uma regra quebrada não derruba o documento inteiro
            out[field] = None
    for group in (partes, advogado, audiencia):
        out.update(group(t))
    return {k: norm_value(k, v) for k, v in out.items()}
