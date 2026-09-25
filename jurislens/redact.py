"""Anonimização LGPD: mascara CPF/CNPJ em textos e saídas antes de publicá-los."""

from __future__ import annotations

import re

from .validators import document_is_valid, only_digits

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def mask_doc(value: str | None) -> str | None:
    d = only_digits(value)
    if len(d) == 11:
        return f"***.{d[3:6]}.***-**"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.***/****-**"  # raiz do CNPJ é pública; o resto não precisa aparecer
    return value


def mask_text(text: str) -> str:
    def sub(m: re.Match) -> str:
        return mask_doc(m.group(0)) if document_is_valid(m.group(0)) else m.group(0)
    return _CNPJ.sub(sub, _CPF.sub(sub, text))


def mask_output(data: dict) -> dict:
    return {k: mask_doc(v) if k.endswith("_documento") and v else v for k, v in data.items()}
