"""Esquema único de saída, compartilhado por regras, LLM, benchmark e bot."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CaseData(BaseModel):
    numero_processo: Optional[str] = Field(
        None, description="Número CNJ no formato NNNNNNN-DD.AAAA.J.TR.OOOO"
    )
    classe: Optional[str] = Field(None, description="Classe processual, ex.: PROCEDIMENTO COMUM CÍVEL")
    orgao_julgador: Optional[str] = Field(None, description="Vara / juízo, ex.: 2ª VARA CÍVEL DE SALVADOR")
    uf: Optional[str] = Field(None, description="Sigla da UF do tribunal, ex.: BA")
    valor_causa: Optional[float] = Field(None, description="Valor da causa em reais, ex.: 15000.00")
    assunto: Optional[str] = Field(None, description="Assunto principal da ação")
    autor_nome: Optional[str] = Field(None, description="Nome completo da parte autora")
    autor_documento: Optional[str] = Field(None, description="CPF ou CNPJ da parte autora, só dígitos")
    reu_nome: Optional[str] = Field(None, description="Nome completo da parte ré")
    reu_documento: Optional[str] = Field(None, description="CPF ou CNPJ da parte ré, só dígitos")
    advogado_nome: Optional[str] = Field(None, description="Nome do advogado da parte autora")
    advogado_oab: Optional[str] = Field(None, description="Inscrição OAB no formato UF/NÚMERO, ex.: BA/12345")
    data_audiencia: Optional[str] = Field(None, description="Data da audiência em ISO, ex.: 2025-03-12")
    hora_audiencia: Optional[str] = Field(None, description="Hora da audiência HH:MM, ex.: 14:30")
    justica_gratuita: Optional[bool] = Field(None, description="Se há pedido/deferimento de justiça gratuita")


FIELDS: list[str] = list(CaseData.model_fields)
