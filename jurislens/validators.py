"""Validação matemática de identificadores brasileiros.

A IA pode "inventar" um CPF plausível; um dígito verificador não mente.
Todos os valores extraídos passam por aqui antes de serem aceitos.
"""

from __future__ import annotations

import re

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def cpf_is_valid(value: str | None) -> bool:
    d = only_digits(value)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d[i]) * (size + 1 - i) for i in range(size))
        check = (total * 10) % 11 % 10
        if check != int(d[size]):
            return False
    return True


def cnpj_is_valid(value: str | None) -> bool:
    d = only_digits(value)
    if len(d) != 14 or d == d[0] * 14:
        return False
    weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for size in (12, 13):
        total = sum(int(d[i]) * weights[i + 13 - size] for i in range(size))
        check = 11 - total % 11
        check = 0 if check >= 10 else check
        if check != int(d[size]):
            return False
    return True


def document_is_valid(value: str | None) -> bool:
    d = only_digits(value)
    return cpf_is_valid(d) if len(d) == 11 else cnpj_is_valid(d)


def cnj_check_digits(sequencial: str, ano: str, segmento: str, tribunal: str, origem: str) -> str:
    """Dígitos verificadores do número CNJ (Resolução 65/2008, ISO 7064 MOD 97-10)."""
    base = int(f"{sequencial}{ano}{segmento}{tribunal}{origem}00")
    return f"{98 - base % 97:02d}"


CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")


def cnj_is_valid(value: str | None) -> bool:
    m = CNJ_RE.fullmatch((value or "").strip())
    if not m:
        return False
    seq, dv, ano, seg, trib, orig = m.groups()
    return cnj_check_digits(seq, ano, seg, trib, orig) == dv


def format_cnj(value: str | None) -> str | None:
    d = only_digits(value)
    if len(d) != 20:
        return None
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


def oab_is_valid(value: str | None) -> bool:
    m = re.fullmatch(r"([A-Z]{2})/(\d{3,6}[A-Z]?)", value or "")
    return bool(m) and m.group(1) in UFS


# Qual validador protege cada campo (None = sem checagem formal).
FIELD_VALIDATORS = {
    "numero_processo": cnj_is_valid,
    "autor_documento": document_is_valid,
    "reu_documento": document_is_valid,
    "advogado_oab": oab_is_valid,
    "uf": lambda v: v in UFS,
    "hora_audiencia": lambda v: bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v or "")),
    "data_audiencia": lambda v: bool(re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", v or "")),
    "valor_causa": lambda v: isinstance(v, (int, float)) and 0 < v < 1e10,
}


def field_is_valid(field: str, value) -> bool:
    if value is None:
        return False
    check = FIELD_VALIDATORS.get(field)
    return True if check is None else bool(check(value))
