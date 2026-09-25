"""Normalização de texto e de valores para comparação justa entre estratégias."""

from __future__ import annotations

import re
import unicodedata

from .validators import format_cnj, only_digits


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def clean_text(text: str) -> str:
    """Maiúsculas, sem acentos, espaços colapsados — mantém quebras de linha."""
    text = strip_accents(text).upper().replace("\r", "")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def norm_name(value: str | None) -> str | None:
    if not value:
        return None
    value = strip_accents(value).upper()
    value = re.sub(r"[^A-Z0-9/ ]", " ", value)
    value = re.sub(r"\b(S A|SA|S/A|LTDA|ME|EIRELI)\b", lambda m: m.group(0).replace(" ", ""), value)
    return re.sub(r"\s+", " ", value).strip() or None


def norm_value(field: str, value):
    """Forma canônica usada tanto na saída quanto na comparação do benchmark."""
    if value is None or value == "":
        return None
    if field == "numero_processo":
        return format_cnj(value) or str(value).strip()
    if field in ("autor_documento", "reu_documento"):
        return only_digits(value) or None
    if field == "valor_causa":
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None
    if field == "justica_gratuita":
        return bool(value)
    if field in ("uf", "hora_audiencia", "data_audiencia", "advogado_oab"):
        return str(value).strip().upper()
    return norm_name(str(value))


def parse_brl(raw: str) -> float | None:
    """'15.000,00' -> 15000.0"""
    raw = re.sub(r"[^\d,.]", "", raw).rstrip(".,")
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        return round(float(raw), 2)
    except ValueError:
        return None
