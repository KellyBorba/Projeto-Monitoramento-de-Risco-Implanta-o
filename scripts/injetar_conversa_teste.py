"""
injetar_conversa_teste.py — Processa a conversa de chat de teste
e salva o resultado no dashboard para visualização.

Executar:
    python scripts/injetar_conversa_teste.py
"""

import sys, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from src.models import Cliente, Ticket
from src.ai_classifier import classificar_ticket
from src.risk_calculator import calcular_score
from src.dashboard_data import salvar_resultado

CONVERSA = Path(__file__).parent.parent / "tests" / "conversa_teste.json"


def main():
    logger.remove()
    logger.add(sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO")

    logger.info("=" * 60)
    logger.info("Processando conversa de chat de teste")
    logger.info("=" * 60)

    with open(CONVERSA, encoding="utf-8") as f:
        msgs = json.load(f)

    # Apenas mensagens do cliente
    msgs_cliente = [m for m in msgs if m["de"] == "cliente"]
    logger.info(f"{len(msgs_cliente)} mensagem(ns) do cliente carregadas.")

    # Converter mensagens em tickets
    tickets = []
    for i, msg in enumerate(msgs_cliente):
        criado_em = datetime.fromisoformat(msg["hora"]).replace(tzinfo=timezone.utc)
        tickets.append(Ticket(
            id=f"CHAT-{msg['id']}",
            company_id=msg["email"],
            assunto=f"Chat — {msg['empresa']} — mensagem {i+1}",
            descricao=msg["texto"],
            criado_em=criado_em,
            solicitante_email=msg["email"],
        ))

    # Classificar via mock
    logger.info("Classificando mensagens via IA (mock)...")
    tickets_classificados = [classificar_ticket(t) for t in tickets]

    for t in tickets_classificados:
        icone = "😤" if t.tem_frustracao else "💬"
        logger.info(f"  {icone} [{t.tipo}] tema: '{t.tema_resumido}'")

    # Montar cliente com sinais extras para o score ficar completo
    cliente = Cliente(
        id="marcos.oliveira@rhconecta.com.br",
        nome="Marcos Oliveira — RH Conecta",
        csm_email=None,
        csm_nome=None,
        email_adm_onboarding="outro.adm@rhconecta.com.br",
        email_adm_atual="marcos.oliveira@rhconecta.com.br",
        percentual_onboarding=40.0,
        modulos_contratados=["LMS", "Trilhas de Aprendizado"],
        modulos_nunca_usados=["Trilhas de Aprendizado"],
    )

    # Calcular score
    score = calcular_score(cliente, tickets_classificados)

    logger.info("=" * 60)
    logger.info(f"RESULTADO:")
    logger.info(f"  Cliente : {score.cliente_nome}")
    logger.info(f"  Score   : {score.score}/100")
    logger.info(f"  Nível   : {score.nivel.upper()}")
    logger.info(f"  Prazo   : {score.prazo_acao}")
    logger.info(f"  Sinais  : {score.sinais_identificados}")
    logger.info("=" * 60)

    # Salvar no dashboard
    salvar_resultado(score)
    logger.info("✅ Salvo em data/clientes_monitorados.json")
    logger.info("   Abra o dashboard e clique em '🔄 Recarregar dados'")


if __name__ == "__main__":
    main()
