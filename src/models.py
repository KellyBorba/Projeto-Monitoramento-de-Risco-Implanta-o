"""
models.py — Modelos de dados do agente de reimplantação.
Usa Pydantic para validação e serialização.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Ticket(BaseModel):
    id: str
    company_id: str
    assunto: str
    descricao: str
    criado_em: datetime
    fechado_em: Optional[datetime] = None
    solicitante_email: Optional[str] = None

    # Campos preenchidos pelo ai_classifier
    tipo: Optional[str] = None            # basico | avancado | recorrente | bug_tecnico
    tem_frustracao: Optional[bool] = None
    tema_resumido: Optional[str] = None


class Cliente(BaseModel):
    id: str                               # HubSpot company ID
    nome: str
    segmento: Optional[str] = None
    plano: Optional[str] = None
    csm_email: Optional[str] = None
    csm_nome: Optional[str] = None

    # Dados de implantação
    email_adm_onboarding: Optional[str] = None   # ADM que fez o onboarding original
    email_adm_atual: Optional[str] = None         # ADM do ticket mais recente
    ultimo_login_adm: Optional[datetime] = None   # última vez que ADM acessou a plataforma
    percentual_onboarding: Optional[float] = None # % conclusão da trilha (0–100)
    modulos_contratados: list[str] = Field(default_factory=list)
    modulos_nunca_usados: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    cliente_id: str
    cliente_nome: str
    score: int = Field(ge=0, le=100)
    nivel: str                            # saudavel | atencao | risco | critico
    sinais_identificados: list[str]       # nomes dos sinais que contribuíram
    detalhes_sinais: dict[str, str] = Field(default_factory=dict)  # sinal → explicação
    prazo_acao: Optional[str] = None
    calculado_em: datetime = Field(default_factory=datetime.utcnow)
    tickets_resumo: list[str] = Field(default_factory=list)       # últimos 3 resumos


class HistoricoCliente(BaseModel):
    """Registro salvo em data/clientes_monitorados.json."""
    cliente_id: str
    cliente_nome: str
    score_atual: int
    nivel_atual: str
    score_anterior: Optional[int] = None
    nivel_anterior: Optional[str] = None
    ultima_analise: datetime
    acao_tomada: bool = False
    acao_tomada_em: Optional[datetime] = None
    historico_scores: list[dict] = Field(default_factory=list)    # [{score, nivel, data}]
    sinais_identificados: list[str] = Field(default_factory=list)
    detalhes_sinais: dict[str, str] = Field(default_factory=dict)
    tickets_resumo: list[str] = Field(default_factory=list)
