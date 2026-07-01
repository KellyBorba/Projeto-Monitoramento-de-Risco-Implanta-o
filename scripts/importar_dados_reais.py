"""
importar_dados_reais.py — Importa dados-reais.json agrupando por empresa cliente.

Executar:
    python scripts/importar_dados_reais.py
"""

import sys, json, re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from src.models import Cliente, Ticket
from src.ai_classifier import classificar_tickets
from src.risk_calculator import calcular_score
from src.dashboard_data import salvar_resultado

DADOS_REAIS = Path(r"C:\Users\kelly\OneDrive\Documentos\Claude\Gestão de incidentes\dados-reais.json")

_IGNORAR = {"ticket chatbot (cliente)", "ticket chatbot", ""}
_RE_EMPRESA = re.compile(r'\s[-–]\s([^-–]+)$')


def _extrair_empresa(subject: str, artia_title: str) -> str:
    """Tenta extrair o nome da empresa do subject ou artiaTitle."""
    for texto in (subject, artia_title):
        m = _RE_EMPRESA.search(texto or "")
        if m:
            empresa = m.group(1).strip()
            # Ignora matches que parecem descrição, não nome de empresa
            if len(empresa) > 2 and not empresa.lower().startswith(("ticket", "erro", "bug", "atividade")):
                return empresa
    return ""


def _parse_dt(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    logger.remove()
    logger.add(sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO")

    logger.info("=" * 60)
    logger.info("Importando dados-reais.json → agrupando por empresa")
    logger.info("=" * 60)

    if not DADOS_REAIS.exists():
        logger.error(f"Arquivo não encontrado: {DADOS_REAIS}")
        return

    with open(DADOS_REAIS, encoding="utf-8-sig") as f:
        registros = json.load(f)

    logger.info(f"{len(registros)} registros carregados.")

    # ── Agrupar por empresa cliente ──────────────────────────────────────────
    tickets_por_empresa  = defaultdict(list)
    subjects_por_empresa = defaultdict(list)
    resp_por_empresa     = defaultdict(set)

    for r in registros:
        subject     = r.get("subject", "").strip()
        artia_title = r.get("artiaTitle", "").strip()
        artia_resp  = r.get("artiaResp") or "Sem responsável"
        criado      = _parse_dt(r.get("createdate")) or datetime.now(timezone.utc)

        empresa = _extrair_empresa(subject, artia_title)
        if not empresa:
            # Fallback: usar artiaResp como agrupador
            empresa = artia_resp

        tickets_por_empresa[empresa].append(Ticket(
            id=str(r.get("hubId", "")),
            company_id=empresa,
            assunto=subject or "Sem assunto",
            descricao=artia_title or subject or "",
            criado_em=criado,
            fechado_em=_parse_dt(r.get("closedDate")),
            solicitante_email=None,
        ))

        # Guardar subjects legíveis com número do ticket e analista N1
        hub_id    = str(r.get("hubId", "")).strip()
        hub_owner = r.get("hubOwner", "") or ""
        subj_lower = subject.lower()
        if not any(ig in subj_lower for ig in _IGNORAR) and not subj_lower.startswith("ticket nº"):
            analista = f" · N1: {hub_owner}" if hub_owner else ""
            entrada  = f"#{hub_id} — {subject}{analista}" if hub_id else subject
            subjects_por_empresa[empresa].append(entrada)

        resp_por_empresa[empresa].add(artia_resp)

    empresas = list(tickets_por_empresa.keys())
    logger.info(f"{len(empresas)} empresa(s) identificada(s).")

    salvos = 0
    for i, empresa in enumerate(empresas, 1):
        tickets   = tickets_por_empresa[empresa]
        subjects  = list(dict.fromkeys(subjects_por_empresa[empresa]))[:5]  # até 5, sem duplicatas
        resps     = ", ".join(r for r in resp_por_empresa[empresa] if "fantasma" not in r.lower())

        logger.info(f"[{i}/{len(empresas)}] {empresa} — {len(tickets)} ticket(s)")

        tickets_classificados = classificar_tickets(tickets)
        cliente = Cliente(id=empresa, nome=empresa)
        score   = calcular_score(cliente, tickets_classificados)

        # Sobrescrever tickets_resumo com os subjects reais (mais legíveis)
        score.tickets_resumo = subjects if subjects else [t.assunto[:80] for t in tickets[:5]]

        logger.info(f"  Score: {score.score} | Nível: {score.nivel} | Responsável(is): {resps or '—'}")
        salvar_resultado(score)
        salvos += 1

    logger.info("=" * 60)
    logger.info(f"Concluído! {salvos} empresa(s) salvas.")
    logger.info("Abra o dashboard e clique em '🔄 Recarregar dados'.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
