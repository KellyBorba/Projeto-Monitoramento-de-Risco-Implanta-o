"""
dashboard_data.py — Leitura e escrita do arquivo de histórico de scores.
Serve como camada de acesso ao cache local data/clientes_monitorados.json.
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from src.models import HistoricoCliente, ScoreResult

DATA_FILE = Path(__file__).parent.parent / "data" / "clientes_monitorados.json"


def _carregar() -> dict[str, dict]:
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Erro ao ler {DATA_FILE}: {e}. Iniciando com vazio.")
        return {}


def _salvar(dados: dict[str, dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)


def buscar_historico(cliente_id: str) -> Optional[HistoricoCliente]:
    dados = _carregar()
    raw = dados.get(cliente_id)
    if not raw:
        return None
    try:
        return HistoricoCliente(**raw)
    except Exception as e:
        logger.warning(f"Dados corrompidos para {cliente_id}: {e}")
        return None


def salvar_resultado(score: ScoreResult) -> HistoricoCliente:
    """Salva ou atualiza o score do cliente no histórico local."""
    dados = _carregar()
    agora = datetime.now(timezone.utc)

    anterior = dados.get(score.cliente_id, {})
    historico_anterior = anterior.get("historico_scores", [])

    # Adiciona entrada ao histórico
    historico_anterior.append({
        "score": score.score,
        "nivel": score.nivel,
        "data":  agora.isoformat(),
    })
    # Mantém só os últimos 90 registros
    historico_anterior = historico_anterior[-90:]

    registro = {
        "cliente_id":          score.cliente_id,
        "cliente_nome":        score.cliente_nome,
        "score_atual":         score.score,
        "nivel_atual":         score.nivel,
        "score_anterior":      anterior.get("score_atual"),
        "nivel_anterior":      anterior.get("nivel_atual"),
        "ultima_analise":      agora.isoformat(),
        "acao_tomada":         anterior.get("acao_tomada", False),
        "acao_tomada_em":      anterior.get("acao_tomada_em"),
        "historico_scores":    historico_anterior,
        "sinais_identificados": score.sinais_identificados,
        "detalhes_sinais":     score.detalhes_sinais,
        "tickets_resumo":      score.tickets_resumo,
    }

    dados[score.cliente_id] = registro
    _salvar(dados)
    return HistoricoCliente(**registro)


def marcar_acao_tomada_local(cliente_id: str) -> bool:
    dados = _carregar()
    if cliente_id not in dados:
        return False
    dados[cliente_id]["acao_tomada"]    = True
    dados[cliente_id]["acao_tomada_em"] = datetime.now(timezone.utc).isoformat()
    _salvar(dados)
    return True


def listar_todos() -> list[HistoricoCliente]:
    """Retorna todos os clientes monitorados, ordenados por score decrescente."""
    dados = _carregar()
    resultados = []
    for raw in dados.values():
        try:
            resultados.append(HistoricoCliente(**raw))
        except Exception:
            continue
    return sorted(resultados, key=lambda h: h.score_atual, reverse=True)


def nivel_subiu(historico: Optional[HistoricoCliente], score_atual: ScoreResult) -> bool:
    """
    Retorna True se o nível de risco subiu em relação ao registro anterior,
    ou se o nível atual é 'critico' (sempre alerta).
    """
    if score_atual.nivel == "critico":
        return True
    if historico is None:
        return score_atual.nivel != "saudavel"

    ordem = ["saudavel", "atencao", "risco", "critico"]
    idx_anterior = ordem.index(historico.nivel_atual) if historico.nivel_atual in ordem else 0
    idx_atual    = ordem.index(score_atual.nivel)     if score_atual.nivel    in ordem else 0
    return idx_atual > idx_anterior
