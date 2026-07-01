"""
run_daily_analysis.py — Script principal de análise diária.

Fluxo atual (modo teste):
1. Busca tickets recentes do HubSpot diretamente
2. Agrupa por e-mail do solicitante (contact associado ao ticket)
3. Classifica cada ticket via mock de IA
4. Calcula score de risco por solicitante
5. Salva em data/clientes_monitorados.json para o dashboard
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta, timezone
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from hubspot import HubSpot
import os

from src.models import Cliente, Ticket
from src.ai_classifier import classificar_tickets
from src.risk_calculator import calcular_score
from src.dashboard_data import salvar_resultado


def configurar_log():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
    )


def _ts_para_datetime(valor):
    if not valor:
        return None
    try:
        return datetime.fromtimestamp(int(valor) / 1000, tz=timezone.utc)
    except Exception:
        return None


def main():
    configurar_log()
    inicio = datetime.utcnow()
    logger.info("=" * 60)
    logger.info(f"Iniciando análise — {inicio.strftime('%d/%m/%Y %H:%M UTC')}")
    logger.info("=" * 60)

    client = HubSpot(access_token=os.getenv('HUBSPOT_API_KEY'))

    # 1. Buscar tickets dos últimos 180 dias
    data_corte = datetime.now(timezone.utc) - timedelta(days=180)
    data_corte_ms = int(data_corte.timestamp() * 1000)

    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "createdate",
                "operator": "GTE",
                "value": str(data_corte_ms),
            }]
        }],
        "properties": [
            "subject", "content", "createdate", "closed_date",
            "hs_pipeline_stage", "hs_ticket_priority", "hs_ticket_category",
            "hubspot_owner_id",
        ],
        "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
        "limit": 100,
    }

    resp = client.crm.tickets.search_api.do_search(
        public_object_search_request=body
    )
    tickets_raw = resp.results or []
    logger.info(f"{len(tickets_raw)} ticket(s) encontrado(s).")

    if not tickets_raw:
        logger.warning("Nenhum ticket encontrado. Encerrando.")
        return

    # 2. Buscar contato (e-mail do solicitante) associado a cada ticket
    logger.info("Buscando contatos associados aos tickets...")
    tickets_por_contato = defaultdict(list)
    nome_contato = {}

    for t in tickets_raw:
        p = t.properties
        criado_em = _ts_para_datetime(p.get("createdate"))
        if not criado_em:
            continue

        email = None
        nome  = None

        # Tenta buscar contato associado ao ticket
        try:
            assoc = client.crm.tickets.associations_api.get_all(
                ticket_id=t.id,
                to_object_type="contacts",
            )
            if assoc.results:
                contact_id = assoc.results[0].id
                contact = client.crm.contacts.basic_api.get_by_id(
                    contact_id=contact_id,
                    properties=["email", "firstname", "lastname"],
                )
                cp    = contact.properties
                email = cp.get("email")
                nome  = f"{cp.get('firstname') or ''} {cp.get('lastname') or ''}".strip()
        except Exception:
            pass

        # Fallback: usa o ID do ticket como agrupador
        chave = email or f"ticket_{t.id}"
        if not nome:
            nome = email or f"Solicitante {t.id}"

        nome_contato[chave] = nome

        tickets_por_contato[chave].append(Ticket(
            id=str(t.id),
            company_id=chave,
            assunto=p.get("subject") or "Sem assunto",
            descricao=p.get("content") or "",
            criado_em=criado_em,
            fechado_em=_ts_para_datetime(p.get("closed_date")),
            solicitante_email=email,
        ))

    contatos = list(tickets_por_contato.keys())
    logger.info(f"{len(contatos)} solicitante(s) identificado(s).")

    # 3. Processar cada solicitante
    salvos = 0
    for i, chave in enumerate(contatos, 1):
        tickets  = tickets_por_contato[chave]
        nome     = nome_contato[chave]
        logger.info(f"[{i}/{len(contatos)}] {nome} — {len(tickets)} ticket(s)")

        tickets_classificados = classificar_tickets(tickets)

        cliente = Cliente(id=chave, nome=nome, csm_email=None)
        score   = calcular_score(cliente, tickets_classificados)

        logger.info(
            f"  Score: {score.score} | Nível: {score.nivel} | "
            f"Sinais: {score.sinais_identificados or 'nenhum'}"
        )

        salvar_resultado(score)
        salvos += 1

    duracao = (datetime.utcnow() - inicio).seconds
    logger.info("=" * 60)
    logger.info(f"Concluído em {duracao}s | {salvos} registro(s) salvos no dashboard")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
