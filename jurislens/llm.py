"""Extrator com Claude via Structured Outputs (resposta validada contra o schema Pydantic)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from .normalize import norm_value
from .schema import FIELDS, CaseData

DEFAULT_MODEL = os.getenv("JURISLENS_MODEL", "claude-opus-5")
EFFORT = os.getenv("JURISLENS_EFFORT", "low")

# USD por 1M tokens (entrada, saída) — usado só para o relatório de custo.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

SYSTEM = """Você é um analista jurídico que extrai dados de processos judiciais brasileiros (PJe).
Regras:
- Extraia apenas o que está escrito no documento. Se um campo não aparece, devolva null — nunca invente.
- numero_processo no padrão CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO.
- autor_documento / reu_documento: somente dígitos do CPF ou CNPJ da parte correspondente.
- advogado_oab no formato UF/NÚMERO (ex.: BA/12345), sem pontos.
- valor_causa como número decimal em reais (R$ 15.000,00 -> 15000.0).
- data_audiencia em ISO (AAAA-MM-DD) e hora_audiencia em HH:MM, convertendo formatos por extenso.
- justica_gratuita: true se há pedido ou deferimento de gratuidade; false se não há menção ou se houve custas recolhidas.
- Nomes de partes e advogados em MAIÚSCULAS, como aparecem no documento.
- O texto veio de um PDF: ignore cabeçalhos de assinatura eletrônica e quebras de linha no meio de palavras."""


@dataclass
class LLMResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    model: str = DEFAULT_MODEL
    error: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICING.get(self.model, PRICING["claude-opus-5"])
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def extract(text: str, only_fields: list[str] | None = None, model: str = DEFAULT_MODEL, client=None) -> LLMResult:
    """Extrai todos os campos; `only_fields` indica onde as regras falharam (modo híbrido)."""
    import anthropic

    client = client or anthropic.Anthropic()
    focus = ""
    if only_fields:
        focus = ("\n\nAs regras determinísticas não conseguiram extrair: "
                 + ", ".join(only_fields) + ". Dê atenção especial a esses campos, mas preencha todos.")
    start = time.perf_counter()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=4096,
            system=SYSTEM,
            output_config={"effort": EFFORT},
            messages=[{"role": "user", "content": f"<documento>\n{text}\n</documento>{focus}"}],
            output_format=CaseData,
        )
    except anthropic.APIError as e:
        return LLMResult(data={}, error=f"{type(e).__name__}: {e}", model=model,
                         seconds=time.perf_counter() - start)
    elapsed = time.perf_counter() - start
    usage = response.usage
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return LLMResult(data={}, error=f"stop_reason={response.stop_reason}", model=model, seconds=elapsed,
                         input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
    raw = response.parsed_output.model_dump()
    data = {k: norm_value(k, raw.get(k)) for k in FIELDS}
    return LLMResult(data=data, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                     seconds=elapsed, model=model)
