"""
hubspot_client.py — Integração com a HubSpot API.
Usa o SDK oficial hubspot-api-client com autenticação via Private App Token.
"""

from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from hubspot import HubSpot
from hubspot.crm.tickets import ApiException as TicketApiException
from hubspot.crm.companies import ApiException as CompanyApiException
from loguru import logger

from src.models import Cliente, Ticket

# ─── Propriedades customizadas esperadas no HubSpot ───────────────────────────
# Crie estas propriedades no HubSpot antes de usar:
#   Objeto Company:
#     twygo_email_adm_onboarding  → E-mail do ADM no momento do onboarding
#     twygo_email_adm_atual       → E-mail do ADM atual (sincronizado pelo produto)
#     twygo_ultimo_login_adm      → Data/hora do último login do ADM (timestamp ms)
#     twygo_percentual_onboarding → % conclusão da trilha do Academy (número)
#     twygo_modulos_contratados   → Módulos contratados separados por ponto-e-vírgula
#     twygo_modulos_nunca_usados  → Módulos que nunca foram acessados
#     twygo_score_risco           → Score calculado pelo agente (atualizado pelo script)
#     twygo_nivel_risco           → Nível de risco (saudavel/atencao/risco/critico)
#     twygo_acao_tomada           → Boolean: analista marcou que tomou ação

# Propriedades padrão do HubSpot (sem customizadas — funcionam sem configuração prévia)
PROPS_COMPANY = [
    "name", "industry", "hs_object_id", "hubspot_owner_id",
    "domain", "phone", "city",
]

# TODO: adicionar propriedades customizadas abaixo quando criadas no HubSpot:
#   "twygo_email_adm_onboarding", "twygo_email_adm_atual",
#   "twygo_ultimo_login_adm", "twygo_percentual_onboarding",
#   "twygo_modulos_contratados", "twygo_modulos_nunca_usados",
#   "twygo_score_risco", "twygo_nivel_risco", "twygo_acao_tomada"

# Propriedades padrão de tickets (sem customizadas)
PROPS_TICKET = [
    "subject", "content", "createdate", "closed_date",
    "hs_pipeline_stage", "hubspot_owner_id",
    "hs_ticket_priority", "hs_ticket_category",
]

# TODO: adicionar "twygo_email_solicitante" quando a propriedade for criada no HubSpot


def _get_client() -> HubSpot:
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        raise EnvironmentError("HUBSPOT_API_KEY não configurada.")
    return HubSpot(access_token=api_key)


def _ts_ms_para_datetime(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        return datetime.fromtimestamp(int(valor) / 1000, tz=timezone.utc)
    except (ValueError, TypeError):
        return None


def buscar_empresas_ativas(limit: int = 10) -> list[dict]:
    """
    Retorna empresas do HubSpot com as propriedades padrão.
    limit: quantidade máxima a buscar (padrão 10 para testes).
    TODO: aumentar o limit (ex: 500) quando validado em produção.
    """
    client = _get_client()
    empresas = []
    after = None

    while True:
        try:
            pagina = min(limit - len(empresas), 100)
            resp = client.crm.companies.basic_api.get_page(
                limit=pagina,
                properties=PROPS_COMPANY,
                after=after,
            )
            empresas.extend(resp.results)
            # Para quando atingiu o limite ou não há mais páginas
            if len(empresas) >= limit or not (resp.paging and resp.paging.next):
                break
            after = resp.paging.next.after
        except CompanyApiException as e:
            logger.error(f"Erro ao buscar empresas: {e.status} — {e.reason}")
            break

    logger.info(f"{len(empresas)} empresa(s) carregada(s) do HubSpot.")
    return empresas


def buscar_dados_cliente(company_id: str) -> Optional[Cliente]:
    """
    Busca as propriedades de uma empresa específica e retorna um objeto Cliente.
    """
    client = _get_client()
    try:
        resp = client.crm.companies.basic_api.get_by_id(
            company_id=company_id,
            properties=PROPS_COMPANY,
        )
        p = resp.properties

        # CSM responsável
        csm_email, csm_nome = None, None
        owner_id = p.get("hubspot_owner_id")
        if owner_id:
            csm_email, csm_nome = buscar_csm_responsavel(owner_id)

        return Cliente(
            id=company_id,
            nome=p.get("name") or f"Empresa {company_id}",
            segmento=p.get("industry"),
            csm_email=csm_email,
            csm_nome=csm_nome,
            # TODO: preencher com propriedades customizadas quando criadas no HubSpot
            email_adm_onboarding=None,
            email_adm_atual=None,
            ultimo_login_adm=None,
            percentual_onboarding=None,
            modulos_contratados=[],
            modulos_nunca_usados=[],
        )
    except CompanyApiException as e:
        logger.error(f"Erro ao buscar empresa {company_id}: {e.status}")
        return None


def buscar_csm_responsavel(owner_id: str) -> tuple[Optional[str], Optional[str]]:
    """Retorna (email, nome) do owner/CSM pelo owner_id do HubSpot."""
    client = _get_client()
    try:
        owner = client.crm.owners.owners_api.get_by_id(owner_id=int(owner_id))
        return owner.email, f"{owner.first_name} {owner.last_name}".strip()
    except Exception as e:
        logger.warning(f"Não foi possível buscar owner {owner_id}: {e}")
        return None, None


def buscar_tickets_por_cliente(company_id: str, dias: int = 30) -> list[Ticket]:
    """
    Busca tickets associados à empresa nos últimos N dias.
    Usa a Search API do HubSpot para filtrar por associação e data.
    """
    client = _get_client()
    data_corte = datetime.now(timezone.utc) - timedelta(days=dias)
    data_corte_ms = int(data_corte.timestamp() * 1000)

    try:
        body = {
            "filterGroups": [{
                "filters": [
                    {
                        "propertyName": "associations.company",
                        "operator": "EQ",
                        "value": company_id,
                    },
                    {
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": str(data_corte_ms),
                    },
                ]
            }],
            "properties": PROPS_TICKET,
            "limit": 100,
        }

        resp = client.crm.tickets.search_api.do_search(public_object_search_request=body)
        tickets = []

        for t in (resp.results or []):
            p = t.properties
            criado_em = _ts_ms_para_datetime(p.get("createdate"))
            if not criado_em:
                continue

            tickets.append(Ticket(
                id=str(t.id),
                company_id=company_id,
                assunto=p.get("subject") or "",
                descricao=p.get("content") or "",
                criado_em=criado_em,
                fechado_em=_ts_ms_para_datetime(p.get("closed_date")),
                solicitante_email=None,  # TODO: usar p.get("twygo_email_solicitante") quando criado
            ))

        logger.debug(f"Empresa {company_id}: {len(tickets)} ticket(s) nos últimos {dias}d.")
        return tickets

    except TicketApiException as e:
        logger.error(f"Erro ao buscar tickets para {company_id}: {e.status}")
        return []


def atualizar_score_no_hubspot(company_id: str, score: int, nivel: str) -> bool:
    """
    Atualiza as propriedades twygo_score_risco e twygo_nivel_risco na empresa.
    """
    client = _get_client()
    try:
        client.crm.companies.basic_api.update(
            company_id=company_id,
            simple_public_object_input={
                "properties": {
                    "twygo_score_risco": str(score),
                    "twygo_nivel_risco": nivel,
                }
            },
        )
        return True
    except CompanyApiException as e:
        logger.error(f"Erro ao atualizar score da empresa {company_id}: {e.status}")
        return False


def marcar_acao_tomada(company_id: str) -> bool:
    """Marca a propriedade twygo_acao_tomada = true no HubSpot."""
    client = _get_client()
    try:
        client.crm.companies.basic_api.update(
            company_id=company_id,
            simple_public_object_input={
                "properties": {"twygo_acao_tomada": "true"}
            },
        )
        return True
    except CompanyApiException as e:
        logger.error(f"Erro ao marcar ação tomada para {company_id}: {e.status}")
        return False
