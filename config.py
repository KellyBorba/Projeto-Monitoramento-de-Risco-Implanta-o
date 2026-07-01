"""
config.py — Configurações centrais e pesos do agente de reimplantação Twygo.
Altere os pesos aqui sem precisar mexer na lógica de negócio.
"""

# ─── Pesos dos sinais de risco ─────────────────────────────────────────────────
SINAIS_DE_RISCO: dict[str, int] = {
    "ticket_basico_repetido":      30,  # mesmo tema de ticket 2+ vezes em 30 dias
    "adm_diferente_onboarding":    25,  # ADM atual ≠ ADM do onboarding original
    "sem_acesso_14_dias":          20,  # nenhum login do ADM em 14+ dias
    "mais_de_5_tickets_mes":       15,  # volume de tickets no mês
    "frase_frustracao_detectada":  15,  # IA identifica frustração no texto
    "funcionalidade_nao_usada":    10,  # feature contratada nunca acessada
    "onboarding_nao_concluido":    10,  # trilha do Academy incompleta
}

# ─── Faixas de risco (score mínimo, score máximo inclusive) ───────────────────
NIVEIS_DE_RISCO: dict[str, tuple[int, int]] = {
    "saudavel": (0, 20),
    "atencao":  (21, 50),
    "risco":    (51, 70),
    "critico":  (71, 100),
}

# ─── Prazos de ação por nível ──────────────────────────────────────────────────
PRAZOS_DE_ACAO: dict[str, str] = {
    "atencao": "5 dias úteis",
    "risco":   "2 dias úteis",
    "critico": "mesmo dia",
}

# ─── Links dos playbooks por nível ────────────────────────────────────────────
PLAYBOOKS: dict[str, str] = {
    "atencao": "https://notion.so/twygo/playbook-atencao",
    "risco":   "https://notion.so/twygo/playbook-risco",
    "critico": "https://notion.so/twygo/playbook-critico",
}

# ─── Parâmetros de detecção ────────────────────────────────────────────────────
JANELA_ANALISE_DIAS:         int = 30   # período de análise de tickets
DIAS_SEM_ACESSO_LIMITE:      int = 14   # inatividade de login que dispara sinal
TICKETS_MES_LIMITE:          int = 5    # quantidade de tickets que dispara sinal
SIMILARIDADE_TEMAS_MINIMA:   int = 75   # threshold fuzzy match (0–100) para agrupar temas
ONBOARDING_CONCLUIDO_MINIMO: int = 80   # % mínimo de conclusão considerado "ok"

# ─── Modelo Claude (Anthropic) ───────────────────────────────────────────────
# Haiku: rápido e barato para classificação em lote
CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

# ─── Cores da marca Twygo (para o dashboard) ──────────────────────────────────
CORES = {
    "roxo":    "#9349DE",
    "dark":    "#1F2041",
    "dourado": "#F5C518",
    "verde":   "#2ECC71",
    "amarelo": "#F39C12",
    "laranja": "#E67E22",
    "vermelho":"#E74C3C",
}

NIVEL_CORES: dict[str, str] = {
    "saudavel": CORES["verde"],
    "atencao":  CORES["amarelo"],
    "risco":    CORES["laranja"],
    "critico":  CORES["vermelho"],
}
