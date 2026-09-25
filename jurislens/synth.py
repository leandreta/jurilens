"""Gerador de processos judiciais 100% sintéticos (LGPD-safe).

Imita três layouts reais do PJe — capa do processo, petição inicial em prosa e
intimação de audiência — e injeta o ruído típico de PDFs extraídos
(quebras de linha no meio de números, cabeçalhos de assinatura, espaços duplos).
Cada documento vem com o gabarito, o que permite medir qualquer extrator.

Nenhum nome, CPF ou CNPJ aqui pertence a uma pessoa real: os nomes são
combinações aleatórias e os documentos são gerados com dígito verificador válido.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from .validators import cnj_check_digits

FIRST = ["ANA", "BRUNO", "CARLA", "DIEGO", "ELISA", "FABIO", "GABRIELA", "HELIO", "IARA", "JOAO",
         "KARINA", "LUCAS", "MARIA", "NILTON", "OLGA", "PAULO", "QUITERIA", "RAFAEL", "SONIA", "TIAGO",
         "URSULA", "VALDIR", "WANDA", "YASMIN", "ZECA", "JOSEFA", "ANTONIO", "RAIMUNDA", "EDNALDO", "LUZIA"]
LAST = ["SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "PEREIRA", "FERREIRA", "COSTA", "RODRIGUES",
        "ALMEIDA", "NASCIMENTO", "CARVALHO", "ARAUJO", "RIBEIRO", "BARBOSA", "MOURA", "CAVALCANTI",
        "MENEZES", "BATISTA", "FREITAS", "PAIXAO", "NOGUEIRA", "TEIXEIRA", "ROCHA", "DIAS"]
COMPANIES = ["BANCO AURORA S.A.", "BANCO HORIZONTE S.A.", "FINANCEIRA ATLAS S.A.",
             "TELEFONICA BORBOLETA LTDA", "COMPANHIA ELETRICA DO VALE S.A.", "SEGURADORA PRUMO S.A.",
             "BANCO CAJUEIRO S.A.", "VAREJO MANDACARU LTDA", "OPERADORA DE SAUDE VIVER BEM LTDA"]
PLACES = [("SALVADOR", "BA", "05"), ("FEIRA DE SANTANA", "BA", "05"), ("RECIFE", "PE", "17"),
          ("FORTALEZA", "CE", "06"), ("SAO PAULO", "SP", "26"), ("CAMPINAS", "SP", "26"),
          ("BELO HORIZONTE", "MG", "13"), ("CURITIBA", "PR", "16"), ("TAPEROA", "BA", "05"),
          ("ARACAJU", "SE", "25"), ("NATAL", "RN", "20"), ("GOIANIA", "GO", "09")]
CLASSES = ["PROCEDIMENTO DO JUIZADO ESPECIAL CIVEL", "PROCEDIMENTO COMUM CIVEL"]
SUBJECTS = ["INCLUSAO INDEVIDA EM CADASTRO DE INADIMPLENTES", "INDENIZACAO POR DANO MORAL",
            "CONTRATOS BANCARIOS", "EMPRESTIMO CONSIGNADO", "FORNECIMENTO DE ENERGIA ELETRICA",
            "PLANOS DE SAUDE", "CARTAO DE CREDITO", "TARIFAS BANCARIAS", "PRATICAS ABUSIVAS"]
VARAS = ["{n}ª VARA CIVEL DE {city}", "{n}ª VARA DO SISTEMA DOS JUIZADOS ESPECIAIS DE {city}",
         "V DOS FEITOS DE REL DE CONS CIV E COMERCIAIS DE {city}", "{n}º JUIZADO ESPECIAL CIVEL DE {city}"]
MONTHS = ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
          "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
UNITS = ["", "UM", "DOIS", "TRES", "QUATRO", "CINCO", "SEIS", "SETE", "OITO", "NOVE", "DEZ",
         "ONZE", "DOZE", "TREZE", "QUATORZE", "QUINZE", "DEZESSEIS", "DEZESSETE", "DEZOITO", "DEZENOVE"]
TENS = ["", "", "VINTE", "TRINTA", "QUARENTA", "CINQUENTA", "SESSENTA", "SETENTA", "OITENTA", "NOVENTA"]


def _cpf(rng: random.Random) -> str:
    d = [rng.randint(0, 9) for _ in range(9)]
    for size in (9, 10):
        total = sum(d[i] * (size + 1 - i) for i in range(size))
        d.append((total * 10) % 11 % 10)
    return "".join(map(str, d))


def _cnpj(rng: random.Random) -> str:
    d = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for size in (12, 13):
        total = sum(d[i] * weights[i + 13 - size] for i in range(size))
        check = 11 - total % 11
        d.append(0 if check >= 10 else check)
    return "".join(map(str, d))


def fmt_cpf(d: str) -> str:
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def fmt_cnpj(d: str) -> str:
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def fmt_brl(v: float) -> str:
    inteiro, cent = f"{v:.2f}".split(".")
    return f"{int(inteiro):,}".replace(",", ".") + "," + cent


def _extenso_milhares(v: int) -> str:
    """Valor por extenso simplificado (só milhares redondos), como nas petições."""
    mil = v // 1000
    if mil < 20:
        words = UNITS[mil]
    else:
        words = TENS[mil // 10] + (f" E {UNITS[mil % 10]}" if mil % 10 else "")
    return f"{words} MIL REAIS"


def _name(rng: random.Random) -> str:
    parts = [rng.choice(FIRST)] + rng.sample(LAST, rng.choice([2, 2, 3]))
    if rng.random() < 0.25:
        parts.insert(-1, rng.choice(["DE", "DA", "DOS"]))
    return " ".join(parts)


def _cnj(rng: random.Random, ano: int, tribunal: str) -> str:
    seq = f"{rng.randint(0, 9_999_999):07d}"
    seg = "8"
    orig = f"{rng.randint(1, 999):04d}"
    dv = cnj_check_digits(seq, str(ano), seg, tribunal, orig)
    return f"{seq}-{dv}.{ano}.{seg}.{tribunal}.{orig}"


@dataclass
class SyntheticCase:
    id: str
    layout: str
    text: str
    truth: dict

    def to_json(self) -> dict:
        return {"id": self.id, "layout": self.layout, "text": self.text, "truth": self.truth}


def _truth(rng: random.Random) -> dict:
    city, uf, trib = rng.choice(PLACES)
    ano = rng.choice([2024, 2025, 2026])
    autor_pj = rng.random() < 0.08
    reu_pf = autor_pj or rng.random() < 0.1
    valor = float(rng.choice([rng.randint(2, 40) * 1000, rng.randint(1500, 60000) + rng.choice([0, 0.5, 0.37])]))
    has_hearing = rng.random() < 0.7
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = f"{rng.choice([8, 9, 10, 11, 13, 14, 15, 16])}:{rng.choice(['00', '15', '30', '45'])}"
    if len(hour) == 4:
        hour = "0" + hour
    return {
        "numero_processo": _cnj(rng, ano, trib),
        "classe": rng.choice(CLASSES),
        "orgao_julgador": rng.choice(VARAS).format(n=rng.randint(1, 12), city=city),
        "uf": uf,
        "valor_causa": round(valor, 2),
        "assunto": rng.choice(SUBJECTS),
        "autor_nome": rng.choice(COMPANIES) if autor_pj else _name(rng),
        "autor_documento": _cnpj(rng) if autor_pj else _cpf(rng),
        "reu_nome": _name(rng) if reu_pf else rng.choice(COMPANIES),
        "reu_documento": _cpf(rng) if reu_pf else _cnpj(rng),
        "advogado_nome": _name(rng),
        "advogado_oab": f"{uf}/{rng.randint(1000, 99999)}",
        "data_audiencia": f"{ano + (1 if month < 3 else 0)}-{month:02d}-{day:02d}" if has_hearing else None,
        "hora_audiencia": hour if has_hearing else None,
        "justica_gratuita": rng.random() < 0.75,
        "_city": city,
    }


def _doc(num: str) -> str:
    return fmt_cpf(num) if len(num) == 11 else fmt_cnpj(num)


def _layout_capa(t: dict, rng: random.Random) -> str:
    hearing = ""
    if t["data_audiencia"]:
        y, m, d = t["data_audiencia"].split("-")
        hearing = f"\nAudiencia: CONCILIACAO em {d}/{m}/{y} as {t['hora_audiencia']}"
    oab_uf, oab_num = t["advogado_oab"].split("/")
    return f"""{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/2025
Número: {t['numero_processo']}
Classe: {t['classe']}
Órgão julgador: {t['orgao_julgador']}
Última distribuição : {rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/2025
Valor da causa: R$ {fmt_brl(t['valor_causa'])}
Assuntos: {t['assunto'].title()}
Segredo de justiça? NÃO
Justiça gratuita? {'SIM' if t['justica_gratuita'] else 'NÃO'}
Pedido de liminar ou antecipação de tutela? {rng.choice(['SIM', 'NÃO'])}{hearing}
TJ{t['uf']}
PJe - Processo Judicial Eletrônico
Partes Advogados
{t['autor_nome']} (AUTOR)
{t['advogado_nome']} (ADVOGADO) OAB {oab_uf}{oab_num}
{t['reu_nome']} (REU)
Documentos
Autor inscrito sob o nº {_doc(t['autor_documento'])}; réu inscrito sob o nº {_doc(t['reu_documento'])}.
"""


def _layout_peticao(t: dict, rng: random.Random) -> str:
    autor_q = ("pessoa jurídica de direito privado, inscrita no CNPJ sob o nº"
               if len(t["autor_documento"]) == 14 else
               f"brasileiro(a), {rng.choice(['casado(a)', 'solteiro(a)', 'aposentado(a)', 'lavrador(a)'])}, "
               f"portador(a) do CPF nº")
    reu_q = ("pessoa jurídica de direito privado, inscrita no CNPJ sob o nº"
             if len(t["reu_documento"]) == 14 else "brasileiro(a), inscrito(a) no CPF sob o nº")
    gratuita = ("\nDOS BENEFÍCIOS DA JUSTIÇA GRATUITA\nRequer a concessão da gratuidade da justiça, nos termos do "
                "art. 98 do CPC, por não possuir condições de arcar com as custas.\n") if t["justica_gratuita"] else ""
    hearing = ""
    if t["data_audiencia"]:
        y, m, d = t["data_audiencia"].split("-")
        hh, mm = t["hora_audiencia"].split(":")
        hora = f"{int(hh)}h{mm}" if mm != "00" else f"{int(hh)}h"
        hearing = (f"\nInforma que já foi designada audiência de conciliação para o dia {int(d)} de "
                   f"{MONTHS[int(m) - 1].lower()} de {y}, às {hora}.\n")
    valor = f"R$ {fmt_brl(t['valor_causa'])}"
    if t["valor_causa"] % 1000 == 0 and t["valor_causa"] < 100000:
        valor += f" ({_extenso_milhares(int(t['valor_causa'])).lower()})"
    oab_uf, oab_num = t["advogado_oab"].split("/")
    oab_num = f"{int(oab_num):,}".replace(",", ".")
    return f"""EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {t['orgao_julgador']} – {t['uf']}

Processo nº {t['numero_processo']}

{t['autor_nome'].title()}, {autor_q} {_doc(t['autor_documento'])}, residente e domiciliado(a) na
comarca de {t['_city'].title()}, vem, por intermédio de seu advogado que esta subscreve, propor a presente
{t['classe'].title()} — {t['assunto'].lower()}
em face de {t['reu_nome']}, {reu_q} {_doc(t['reu_documento'])}, pelos fatos e fundamentos a seguir.
{gratuita}
DOS FATOS
A parte autora foi surpreendida com cobranças que desconhece, o que lhe causou prejuízos de ordem moral.
{hearing}
DOS PEDIDOS
Diante do exposto, requer a procedência total dos pedidos.

Dá-se à causa o valor de {valor}.

Nestes termos, pede deferimento.
{t['_city'].title()}, {rng.randint(1, 28)} de {rng.choice(MONTHS).lower()} de 2025.

{t['advogado_nome'].title()}
OAB/{oab_uf} {oab_num}
"""


def _layout_intimacao(t: dict, rng: random.Random) -> str:
    y, m, d = (t["data_audiencia"] or "2025-01-01").split("-")
    hearing = (f"Fica a parte intimada para a AUDIÊNCIA DE CONCILIAÇÃO designada para "
               f"{d}.{m}.{y}, {t['hora_audiencia'].replace(':', 'h')}min, na sala virtual do juízo."
               if t["data_audiencia"] else "Aguarda-se designação de pauta.")
    return f"""PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA DO ESTADO — {t['uf']}
{t['orgao_julgador']}
PROCESSO: {t['numero_processo']}   CLASSE: {t['classe']}
ASSUNTO: {t['assunto']}
REQUERENTE: {t['autor_nome']} — CPF/CNPJ {_doc(t['autor_documento'])}
Advogado(s) do reclamante: {t['advogado_nome']} (OAB {oab_fmt(t['advogado_oab'])})
REQUERIDO: {t['reu_nome']} — CPF/CNPJ {_doc(t['reu_documento'])}
VALOR DA CAUSA: R$ {fmt_brl(t['valor_causa'])}
{"GRATUIDADE DA JUSTIÇA: DEFERIDA" if t['justica_gratuita'] else "CUSTAS: RECOLHIDAS"}

ATO ORDINATÓRIO
{hearing}
"""


def oab_fmt(oab: str) -> str:
    uf, num = oab.split("/")
    return f"{num}/{uf}"


LAYOUTS = {"capa_pje": _layout_capa, "peticao_inicial": _layout_peticao, "intimacao": _layout_intimacao}


def _noise(text: str, rng: random.Random, doc_no: int) -> str:
    """Ruído de extração de PDF: quebras em números, cabeçalhos de assinatura."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        if rng.random() < 0.05 and len(line) > 30:
            cut = rng.randint(10, len(line) - 10)
            if line[cut - 1] != " " and line[cut] != " ":
                line = line[:cut] + "\n" + line[cut:]
        out.append(line)
        if i and i % rng.randint(12, 20) == 0:
            out.append(f"Num. {46919000 + doc_no} - Pág. {i // 12 + 1}\nAssinado eletronicamente por: "
                       f"{_name(rng)} - {rng.randint(1, 28):02d}/10/2025 08:29:43")
    text = "\n".join(out)
    if rng.random() < 0.3:
        text = text.replace(" ", "  ", rng.randint(1, 8))
    return text


def generate(n: int = 60, seed: int = 42) -> list[SyntheticCase]:
    rng = random.Random(seed)
    cases = []
    layouts = list(LAYOUTS)
    for i in range(n):
        truth = _truth(rng)
        layout = layouts[i % len(layouts)]
        text = _noise(LAYOUTS[layout](truth, rng), rng, i)
        truth = {k: v for k, v in truth.items() if not k.startswith("_")}
        cases.append(SyntheticCase(id=f"sint-{i:03d}", layout=layout, text=text, truth=truth))
    return cases


def save(cases: list[SyntheticCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c.to_json(), ensure_ascii=False) + "\n")


def load(path: Path) -> list[SyntheticCase]:
    with path.open(encoding="utf-8") as f:
        return [SyntheticCase(**json.loads(line)) for line in f if line.strip()]
