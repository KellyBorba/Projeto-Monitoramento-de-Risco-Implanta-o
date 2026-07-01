"""
components.py — Componentes reutilizáveis do dashboard Streamlit.
"""

from __future__ import annotations
import streamlit as st
from config import NIVEL_CORES, PRAZOS_DE_ACAO
from src.models import HistoricoCliente

_SINAL_LABEL = {
    "ticket_basico_repetido":     "Tickets repetidos sobre o mesmo tema",
    "adm_diferente_onboarding":   "Administrador atual diferente do onboarding",
    "sem_acesso_14_dias":         "Sem acesso há mais de 14 dias",
    "mais_de_5_tickets_mes":      "Mais de 5 tickets abertos no último mês",
    "frase_frustracao_detectada": "Cliente demonstrou frustração explícita",
    "funcionalidade_nao_usada":   "Funcionalidade contratada nunca foi usada",
    "onboarding_nao_concluido":   "Onboarding não foi concluído",
}

_NIVEL_EMOJI = {
    "critico":  "🔴",
    "risco":    "🔶",
    "atencao":  "⚠️",
    "saudavel": "✅",
}

_ANALISE_TEXTO = {
    "ticket_basico_repetido":     "abrindo tickets repetidos sobre o mesmo problema",
    "adm_diferente_onboarding":   "com troca de administrador desde o onboarding",
    "sem_acesso_14_dias":         "sem acessar a plataforma há mais de 14 dias",
    "mais_de_5_tickets_mes":      "com alto volume de tickets no mês",
    "frase_frustracao_detectada": "demonstrando frustração explícita nos atendimentos",
    "funcionalidade_nao_usada":   "com funcionalidade contratada sem uso",
    "onboarding_nao_concluido":   "com onboarding incompleto",
}


def badge_nivel(nivel: str) -> str:
    cor = NIVEL_CORES.get(nivel, "#888888")
    label = {
        "saudavel": "✅ Saudável",
        "atencao":  "⚠️ Atenção",
        "risco":    "🔶 Em Risco",
        "critico":  "🔴 CRÍTICO",
    }.get(nivel, nivel.upper())
    return (
        f'<span style="background:{cor};color:#fff;padding:3px 10px;'
        f'border-radius:12px;font-size:12px;font-weight:600;">{label}</span>'
    )


def barra_score(score: int, nivel: str) -> None:
    cor = NIVEL_CORES.get(nivel, "#888888")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin:4px 0;">
          <div style="flex:1;background:#e8e8e6;border-radius:4px;height:8px;overflow:hidden;">
            <div style="width:{score}%;background:{cor};height:100%;border-radius:4px;"></div>
          </div>
          <span style="font-size:15px;font-weight:700;color:{cor};min-width:38px;">{score}/100</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _gerar_analise_texto(sinais: list[str], detalhes: dict[str, str], nivel: str, prazo: str) -> str:
    """Gera um parágrafo em linguagem natural explicando o risco."""
    if not sinais:
        return ""
    partes = [_ANALISE_TEXTO.get(s, s.replace("_", " ")) for s in sinais]
    if len(partes) == 1:
        motivos = partes[0]
    elif len(partes) == 2:
        motivos = f"{partes[0]} e {partes[1]}"
    else:
        motivos = ", ".join(partes[:-1]) + f" e {partes[-1]}"

    nivel_label = {"atencao": "atenção", "risco": "risco", "critico": "risco crítico"}.get(nivel, nivel)
    prazo_texto = f" Prazo de ação: **{prazo}**." if prazo else ""
    return f"Este cliente foi sinalizado como **{nivel_label}** por estar {motivos}.{prazo_texto}"


def card_cliente(h: HistoricoCliente) -> None:
    cor   = NIVEL_CORES.get(h.nivel_atual, "#888888")
    prazo = PRAZOS_DE_ACAO.get(h.nivel_atual, "")
    emoji = _NIVEL_EMOJI.get(h.nivel_atual, "")
    sinais      = getattr(h, "sinais_identificados", []) or []
    detalhes_map = getattr(h, "detalhes_sinais", {}) or {}
    tickets_res  = getattr(h, "tickets_resumo", []) or []

    expanded = h.nivel_atual in ("critico", "risco")

    with st.expander(
        f"{emoji} **{h.cliente_nome}** — Score {h.score_atual}/100",
        expanded=expanded,
    ):
        # ── Linha 1: badge + barra + prazo + data ──────────────────────────
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.markdown(badge_nivel(h.nivel_atual), unsafe_allow_html=True)
            barra_score(h.score_atual, h.nivel_atual)
        with col2:
            st.caption("Prazo de ação")
            st.markdown(f"**{prazo or '—'}**")
        with col3:
            st.caption("Última análise")
            ultima = h.ultima_analise
            if hasattr(ultima, "strftime"):
                st.markdown(f"**{ultima.strftime('%d/%m %H:%M')}**")

        st.markdown("---")

        # ── Análise em texto ───────────────────────────────────────────────
        analise = _gerar_analise_texto(sinais, detalhes_map, h.nivel_atual, prazo)
        if analise:
            st.markdown(f"> {analise}")
        elif h.nivel_atual == "saudavel":
            st.markdown("> ✅ Nenhum sinal de risco detectado neste momento.")
        else:
            st.markdown("> ℹ️ Análise baseada no volume de tickets recentes.")

        # ── Tickets abertos ────────────────────────────────────────────────
        if tickets_res:
            st.markdown("**Tickets abertos:**")
            for item in tickets_res:
                st.markdown(
                    f'<div style="padding:4px 0 4px 12px;border-left:3px solid {cor};'
                    f'font-size:13px;margin:2px 0;">{item}</div>',
                    unsafe_allow_html=True,
                )

        # ── Tabela de sinais ───────────────────────────────────────────────
        if sinais:
            st.markdown("**Motivos identificados:**")
            linhas = []
            for sinal in sinais:
                label   = _SINAL_LABEL.get(sinal, sinal.replace("_", " ").capitalize())
                detalhe = detalhes_map.get(sinal, "—")
                linhas.append(f"""
                  <tr>
                    <td style="padding:6px 12px;font-size:12px;color:#555;
                               white-space:nowrap;border-bottom:1px solid #eee;
                               font-family:monospace;">{sinal}</td>
                    <td style="padding:6px 12px;font-size:13px;
                               border-bottom:1px solid #eee;">{detalhe or label}</td>
                  </tr>
                """)
            st.markdown(f"""
              <table style="width:100%;border-collapse:collapse;background:#fff;
                            border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.06);
                            margin:8px 0 12px;">
                <thead><tr style="background:#f7f7f5;">
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#444;
                             font-weight:600;border-bottom:2px solid #e0e0e0;white-space:nowrap;">
                    Sinal detectado</th>
                  <th style="padding:8px 12px;text-align:left;font-size:12px;color:#444;
                             font-weight:600;border-bottom:2px solid #e0e0e0;">
                    O que identificou</th>
                </tr></thead>
                <tbody>{''.join(linhas)}</tbody>
              </table>
            """, unsafe_allow_html=True)

        # ── Subiu de nível ─────────────────────────────────────────────────
        if h.nivel_anterior and h.nivel_anterior != h.nivel_atual:
            st.info(f"↗ Nível subiu: **{h.nivel_anterior}** → **{h.nivel_atual}**")

        # ── Ação ───────────────────────────────────────────────────────────
        if h.acao_tomada:
            st.success("✔ Ação registrada pelo CSM")
        elif h.nivel_atual in ("atencao", "risco", "critico"):
            if st.button("✅ Marcar ação tomada", key=f"acao_{h.cliente_id}"):
                _marcar_acao(h.cliente_id)


def _marcar_acao(cliente_id: str) -> None:
    from src.dashboard_data import marcar_acao_tomada_local
    from src.hubspot_client import marcar_acao_tomada
    marcar_acao_tomada_local(cliente_id)
    marcar_acao_tomada(cliente_id)
    st.success("Ação registrada com sucesso!")
    st.rerun()
