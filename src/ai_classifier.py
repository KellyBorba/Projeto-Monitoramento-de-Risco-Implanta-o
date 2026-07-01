"""
ai_classifier.py — Classificação de tickets.

MODO ATUAL: mock local (sem chamada de API).
Quando a ANTHROPIC_API_KEY estiver configurada e o mock for removido,
a função classificar_ticket enviará o texto para o Claude Haiku.

Para ativar a IA real: procure por "TODO: substituir mock" neste arquivo.
"""

from __future__ import annotations
import hashlib
import os
import random
from typing import Optional

from loguru import logger

from src.models import Ticket

# ─── Modelo que será usado quando a IA real for ativada ───────────────────────
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_cache: dict[str, dict] = {}   # hash do texto → resultado classificado


def _hash_texto(texto: str) -> str:
    return hashlib.md5(texto.encode()).hexdigest()


# ─── Mock de classificação ────────────────────────────────────────────────────

# Palavras-chave simples para variar o mock de forma coerente com o texto
_PALAVRAS_BUG      = {"erro", "falha", "bug", "quebrou", "parou", "não abre", "tela branca"}
_PALAVRAS_FRUSTR   = {"urgente", "cancelar", "absurdo", "horrível", "desistir",
                      "sempre", "de novo", "novamente", "já falei"}
_PALAVRAS_AVANC    = {"integração", "api", "webhook", "sso", "ldap", "customiz",
                      "script", "relatório avançado"}
_PALAVRAS_RECORR   = {"de novo", "novamente", "outra vez", "segunda vez",
                      "continua", "persiste", "ainda"}

_MOTIVOS_MOCK = [
    "cliente abre muitos tickets sobre o mesmo tema de certificados",
    "ADM atual é diferente do ADM que fez o onboarding original",
    "último acesso ao painel foi há mais de 14 dias",
    "cliente demonstrou frustração com a ferramenta em múltiplos tickets",
    "funcionalidade de trilhas contratada nunca foi utilizada",
    "onboarding incompleto — menos de 50% da trilha concluída",
    "volume de tickets acima do esperado para o porte do cliente",
]


def _classificar_mock(texto: str) -> dict:
    """
    TODO: substituir mock por chamada real à API Claude.

    Lógica de substituição:
      1. Instanciar anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
      2. Chamar client.messages.create(model=CLAUDE_MODEL, ...) com PROMPT_CLASSIFICACAO
      3. Fazer json.loads() na resposta e retornar o dict

    Por enquanto retorna dados fictícios baseados em palavras-chave simples.
    """
    texto_lower = texto.lower()

    # Tipo do ticket
    if any(p in texto_lower for p in _PALAVRAS_BUG):
        tipo = "bug_tecnico"
    elif any(p in texto_lower for p in _PALAVRAS_RECORR):
        tipo = "recorrente"
    elif any(p in texto_lower for p in _PALAVRAS_AVANC):
        tipo = "avancado"
    else:
        tipo = "basico"

    # Frustração
    tem_frustracao = any(p in texto_lower for p in _PALAVRAS_FRUSTR)

    # Tema resumido: pega as primeiras 4 palavras do assunto (linha 1 do texto)
    primeira_linha = texto.split("\n")[0].strip()
    palavras = primeira_linha.split()[:4]
    tema_resumido = " ".join(palavras).lower() if palavras else "dúvida geral"

    # Risco simulado (varia para mostrar diferentes cenários no dashboard)
    risco_opcoes = ["baixo", "medio", "alto"]
    risco = random.choice(risco_opcoes)
    motivo = random.choice(_MOTIVOS_MOCK)

    return {
        "tipo":          tipo,
        "tem_frustracao": tem_frustracao,
        "tema_resumido": tema_resumido,
        # Campos extras de risco — usados futuramente pelo risk_calculator
        "risco":  risco,
        "motivo": motivo,
    }


# ─── Função pública ───────────────────────────────────────────────────────────

def classificar_ticket(ticket: Ticket) -> Ticket:
    """
    Classifica o ticket e preenche: tipo, tem_frustracao, tema_resumido.
    Usa cache para não processar o mesmo texto duas vezes na mesma execução.
    """
    texto = f"{ticket.assunto}\n\n{ticket.descricao}".strip()
    if not texto:
        logger.warning(f"Ticket {ticket.id} sem texto — pulando classificação.")
        return ticket

    chave = _hash_texto(texto)
    if chave in _cache:
        resultado = _cache[chave]
        logger.debug(f"Ticket {ticket.id}: classificação via cache.")
    else:
        # TODO: substituir mock por chamada real à API Claude
        resultado = _classificar_mock(texto)
        _cache[chave] = resultado
        logger.debug(f"Ticket {ticket.id} [MOCK]: {resultado}")

    return ticket.model_copy(update={
        "tipo":           resultado.get("tipo"),
        "tem_frustracao": bool(resultado.get("tem_frustracao", False)),
        "tema_resumido":  resultado.get("tema_resumido"),
    })


def classificar_tickets(tickets: list[Ticket]) -> list[Ticket]:
    """Classifica uma lista de tickets, pulando os que já têm tipo preenchido."""
    return [
        t if t.tipo is not None else classificar_ticket(t)
        for t in tickets
    ]
