"""
risk_calculator.py — Cálculo do score de risco de reimplantação por cliente.
Cada sinal identificado soma seu peso ao score total (cap: 100).
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from rapidfuzz import fuzz

from config import (
    SINAIS_DE_RISCO,
    NIVEIS_DE_RISCO,
    PRAZOS_DE_ACAO,
    DIAS_SEM_ACESSO_LIMITE,
    TICKETS_MES_LIMITE,
    SIMILARIDADE_TEMAS_MINIMA,
    ONBOARDING_CONCLUIDO_MINIMO,
)
from src.models import Cliente, ScoreResult, Ticket


def _nivel_para_score(score: int) -> str:
    for nivel, (minimo, maximo) in NIVEIS_DE_RISCO.items():
        if minimo <= score <= maximo:
            return nivel
    return "critico"


def _agrupar_temas_similares(tickets: list[Ticket]) -> dict[str, list[Ticket]]:
    """
    Agrupa tickets com temas similares usando fuzzy matching.
    Retorna dict {tema_representante: [tickets]}.
    """
    grupos: dict[str, list[Ticket]] = {}

    for ticket in tickets:
        tema = ticket.tema_resumido or ""
        if not tema:
            continue

        encaixou = False
        for representante in list(grupos.keys()):
            similaridade = fuzz.token_sort_ratio(tema, representante)
            if similaridade >= SIMILARIDADE_TEMAS_MINIMA:
                grupos[representante].append(ticket)
                encaixou = True
                break

        if not encaixou:
            grupos[tema] = [ticket]

    return grupos


def calcular_score(
    cliente: Cliente,
    tickets_30_dias: list[Ticket],
    agora: Optional[datetime] = None,
) -> ScoreResult:
    """
    Analisa os sinais de risco do cliente e retorna ScoreResult com
    score (0–100), nível, sinais identificados e prazo de ação.
    """
    agora = agora or datetime.now(timezone.utc)
    score_acumulado = 0
    sinais: list[str] = []
    detalhes: dict[str, str] = {}

    tickets_basicos = [t for t in tickets_30_dias if t.tipo == "basico"]

    # ── Sinal 1: ticket básico repetido ──────────────────────────────────────
    grupos = _agrupar_temas_similares(tickets_basicos)
    temas_repetidos = {tema: ts for tema, ts in grupos.items() if len(ts) >= 2}

    if temas_repetidos:
        score_acumulado += SINAIS_DE_RISCO["ticket_basico_repetido"]
        sinais.append("ticket_basico_repetido")
        exemplos = list(temas_repetidos.keys())[:2]
        detalhes["ticket_basico_repetido"] = (
            f"{len(temas_repetidos)} tema(s) repetido(s) em tickets básicos: "
            f"{', '.join(exemplos)}"
        )
        logger.debug(f"[{cliente.nome}] ticket_basico_repetido: {temas_repetidos}")

    # ── Sinal 2: ADM diferente do onboarding ─────────────────────────────────
    adm_onboarding = (cliente.email_adm_onboarding or "").strip().lower()
    adm_atual      = (cliente.email_adm_atual      or "").strip().lower()

    if adm_onboarding and adm_atual and adm_onboarding != adm_atual:
        score_acumulado += SINAIS_DE_RISCO["adm_diferente_onboarding"]
        sinais.append("adm_diferente_onboarding")
        detalhes["adm_diferente_onboarding"] = (
            f"ADM atual diferente de quem fez o onboarding ({adm_onboarding})"
        )
        logger.debug(f"[{cliente.nome}] adm_diferente_onboarding")

    # ── Sinal 3: sem acesso há 14+ dias ──────────────────────────────────────
    if cliente.ultimo_login_adm:
        ultimo_login = cliente.ultimo_login_adm
        if ultimo_login.tzinfo is None:
            ultimo_login = ultimo_login.replace(tzinfo=timezone.utc)
        dias_inativos = (agora - ultimo_login).days
        if dias_inativos >= DIAS_SEM_ACESSO_LIMITE:
            score_acumulado += SINAIS_DE_RISCO["sem_acesso_14_dias"]
            sinais.append("sem_acesso_14_dias")
            detalhes["sem_acesso_14_dias"] = (
                f"Último acesso do ADM há {dias_inativos} dia(s)"
            )
            logger.debug(f"[{cliente.nome}] sem_acesso_14_dias: {dias_inativos}d")

    # ── Sinal 4: mais de 5 tickets no mês ────────────────────────────────────
    if len(tickets_30_dias) > TICKETS_MES_LIMITE:
        score_acumulado += SINAIS_DE_RISCO["mais_de_5_tickets_mes"]
        sinais.append("mais_de_5_tickets_mes")
        detalhes["mais_de_5_tickets_mes"] = (
            f"{len(tickets_30_dias)} tickets abertos nos últimos 30 dias"
        )
        logger.debug(f"[{cliente.nome}] mais_de_5_tickets_mes: {len(tickets_30_dias)}")

    # ── Sinal 5: frustração detectada pela IA ────────────────────────────────
    tickets_com_frustracao = [t for t in tickets_30_dias if t.tem_frustracao]
    if tickets_com_frustracao:
        score_acumulado += SINAIS_DE_RISCO["frase_frustracao_detectada"]
        sinais.append("frase_frustracao_detectada")
        frases = [t.descricao[:80] for t in tickets_com_frustracao[:2] if t.descricao]
        detalhes["frase_frustracao_detectada"] = (
            "\"" + "\" / \"".join(frases) + "\"" if frases
            else f"Frustração detectada em {len(tickets_com_frustracao)} ticket(s)"
        )
        logger.debug(f"[{cliente.nome}] frase_frustracao_detectada")

    # ── Sinal 6: funcionalidade nunca usada ──────────────────────────────────
    if cliente.modulos_nunca_usados:
        score_acumulado += SINAIS_DE_RISCO["funcionalidade_nao_usada"]
        sinais.append("funcionalidade_nao_usada")
        detalhes["funcionalidade_nao_usada"] = (
            f"Módulo de {', '.join(cliente.modulos_nunca_usados)} contratado e nunca usado"
        )
        logger.debug(f"[{cliente.nome}] funcionalidade_nao_usada: {cliente.modulos_nunca_usados}")

    # ── Sinal 7: onboarding incompleto ───────────────────────────────────────
    pct = cliente.percentual_onboarding
    if pct is not None and pct < ONBOARDING_CONCLUIDO_MINIMO:
        score_acumulado += SINAIS_DE_RISCO["onboarding_nao_concluido"]
        sinais.append("onboarding_nao_concluido")
        detalhes["onboarding_nao_concluido"] = (
            f"Trilha {pct:.0f}% concluída (mínimo é {ONBOARDING_CONCLUIDO_MINIMO}%)"
        )
        logger.debug(f"[{cliente.nome}] onboarding_nao_concluido: {pct}%")

    # ── Score final ───────────────────────────────────────────────────────────
    score_final = min(score_acumulado, 100)
    nivel       = _nivel_para_score(score_final)
    prazo       = PRAZOS_DE_ACAO.get(nivel)

    # Resumo dos últimos 3 tickets
    ultimos_3 = sorted(tickets_30_dias, key=lambda t: t.criado_em, reverse=True)[:3]
    tickets_resumo = [
        f"[{t.tipo or '?'}] {t.tema_resumido or t.assunto[:60]}"
        for t in ultimos_3
    ]

    logger.info(
        f"[{cliente.nome}] score={score_final} | nivel={nivel} | "
        f"sinais={sinais}"
    )

    return ScoreResult(
        cliente_id=cliente.id,
        cliente_nome=cliente.nome,
        score=score_final,
        nivel=nivel,
        sinais_identificados=sinais,
        detalhes_sinais=detalhes,
        prazo_acao=prazo,
        tickets_resumo=tickets_resumo,
    )
