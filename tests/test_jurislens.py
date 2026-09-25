from types import SimpleNamespace

import pytest

from jurislens import bench, hybrid, redact, rules, synth
from jurislens.schema import FIELDS, CaseData
from jurislens.validators import cnj_is_valid, cnpj_is_valid, cpf_is_valid, document_is_valid


# ---------- validadores ----------

def test_cpf_cnpj_cnj():
    assert cpf_is_valid("529.982.247-25")
    assert not cpf_is_valid("529.982.247-26")
    assert not cpf_is_valid("111.111.111-11")
    assert cnpj_is_valid("11.222.333/0001-81")
    assert not cnpj_is_valid("11.222.333/0001-82")
    assert cnj_is_valid("8000958-06.2024.8.05.0255")
    assert not cnj_is_valid("8000958-07.2024.8.05.0255")


def test_synthetic_data_is_internally_valid():
    for c in synth.generate(40, seed=1):
        assert cnj_is_valid(c.truth["numero_processo"])
        assert document_is_valid(c.truth["autor_documento"])
        assert document_is_valid(c.truth["reu_documento"])
        assert c.truth["autor_nome"] != c.truth["reu_nome"]
        assert set(c.truth) == set(FIELDS)


def test_generation_is_deterministic():
    assert [c.text for c in synth.generate(5, seed=9)] == [c.text for c in synth.generate(5, seed=9)]


# ---------- regras ----------

def test_rules_on_structured_layout():
    case = next(c for c in synth.generate(12, seed=3) if c.layout == "capa_pje")
    s = bench.score(rules.extract(case.text), case.truth)
    assert sum(s.values()) >= len(FIELDS) - 2


def test_rules_baseline_is_reasonable():
    report = bench.run_strategy("regras", synth.generate(45, seed=5))
    assert report["field_accuracy"] > 0.8


# ---------- híbrido com cliente Claude simulado ----------

class FakeClient:
    """Imita client.messages.parse devolvendo um CaseData pronto."""

    def __init__(self, answer: dict):
        self.answer = answer
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed_output=CaseData(**self.answer),
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1200, output_tokens=150),
        )


def _prose_case():
    return next(c for c in synth.generate(30, seed=11)
                if c.layout == "peticao_inicial" and c.truth["data_audiencia"])


def test_hybrid_only_asks_llm_for_missing_fields():
    case = _prose_case()
    client = FakeClient(case.truth)
    r = hybrid.extract(case.text, use_llm=True, client=client)
    assert r.llm_fields, "petição em prosa deveria ter campos pendentes"
    assert "numero_processo" not in r.llm_fields  # regra já resolveu
    assert "data_audiencia" in r.llm_fields  # data por extenso vai para a IA
    assert r.data["data_audiencia"] == case.truth["data_audiencia"]
    assert r.source["data_audiencia"] == "ia"
    assert r.cost_usd > 0
    assert len(client.calls) == 1


def test_hybrid_rejects_hallucinated_values():
    case = _prose_case()
    answer = dict(case.truth)
    answer["data_audiencia"] = "2031-12-25"  # não está no texto
    answer["reu_documento"] = "52998224725"  # CPF válido, mas inventado
    r = hybrid.extract(case.text, use_llm=True, client=FakeClient(answer))
    assert r.data["data_audiencia"] is None
    assert r.source["data_audiencia"] == "descartado"
    if "reu_documento" in r.llm_fields:
        assert r.data["reu_documento"] != "52998224725"


def test_hybrid_without_llm_equals_rules():
    case = _prose_case()
    r = hybrid.extract(case.text, use_llm=False)
    assert r.cost_usd == 0 and not r.llm_fields


# ---------- LGPD ----------

def test_redaction():
    text = "Autor CPF 529.982.247-25, réu CNPJ 11.222.333/0001-81, protocolo 123.456.789-00"
    masked = redact.mask_text(text)
    assert "529.982.247-25" not in masked and "***.982.***-**" in masked
    assert "11.222.333/0001-81" not in masked
    assert "123.456.789-00" in masked  # não é CPF válido: não mexe


@pytest.mark.parametrize("layout", list(synth.LAYOUTS))
def test_every_layout_renders(layout):
    assert any(c.layout == layout for c in synth.generate(9))
