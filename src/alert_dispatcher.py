"""
alert_dispatcher.py — Envio de alertas por e-mail para o CSM responsável.
Usa SendGrid SDK com fallback para SMTP nativo do Python.
"""

from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional

from loguru import logger

from config import PLAYBOOKS, NIVEL_CORES
from src.models import Cliente, ScoreResult


# ─── Funções de template ──────────────────────────────────────────────────────

def _cor_nivel(nivel: str) -> str:
    return NIVEL_CORES.get(nivel, "#888888")


def _label_nivel(nivel: str) -> str:
    return {
        "saudavel": "Saudável",
        "atencao":  "Atenção",
        "risco":    "Risco",
        "critico":  "CRÍTICO",
    }.get(nivel, nivel.upper())


def _sinais_html(score: ScoreResult) -> str:
    linhas = []
    for sinal in score.sinais_identificados:
        detalhe = score.detalhes_sinais.get(sinal, "")
        nome_legivel = sinal.replace("_", " ").title()
        linhas.append(
            f"<li><strong>{nome_legivel}</strong>"
            + (f": {detalhe}" if detalhe else "")
            + "</li>"
        )
    return "<ul>" + "".join(linhas) + "</ul>" if linhas else "<p>Nenhum sinal.</p>"


def _tickets_html(score: ScoreResult) -> str:
    if not score.tickets_resumo:
        return "<p>Sem tickets recentes.</p>"
    items = "".join(f"<li>{t}</li>" for t in score.tickets_resumo)
    return f"<ul>{items}</ul>"


def _montar_html(cliente: Cliente, score: ScoreResult) -> str:
    cor    = _cor_nivel(score.nivel)
    label  = _label_nivel(score.nivel)
    prazo  = score.prazo_acao or "—"
    link   = PLAYBOOKS.get(score.nivel, "")
    agora  = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8" /></head>
<body style="font-family:system-ui,sans-serif;background:#f5f5f5;padding:24px;color:#1F2041;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 8px rgba(0,0,0,0.08);">

    <!-- Cabeçalho -->
    <div style="background:{cor};padding:20px 24px;">
      <h1 style="color:#fff;font-size:18px;margin:0;">
        ⚠️ Alerta de Reimplantação — {label}
      </h1>
      <p style="color:rgba(255,255,255,0.85);font-size:13px;margin:4px 0 0;">
        Gerado em {agora}
      </p>
    </div>

    <!-- Corpo -->
    <div style="padding:24px;">
      <h2 style="font-size:20px;margin:0 0 4px;">{cliente.nome}</h2>
      <p style="font-size:13px;color:#666;margin:0 0 20px;">
        Segmento: {cliente.segmento or '—'} &nbsp;·&nbsp; CSM: {cliente.csm_nome or '—'}
      </p>

      <!-- Score -->
      <div style="background:#f9f9f9;border-radius:8px;padding:16px;margin-bottom:20px;">
        <p style="font-size:13px;color:#666;margin:0 0 8px;">Score de Risco</p>
        <div style="display:flex;align-items:center;gap:12px;">
          <div style="font-size:36px;font-weight:700;color:{cor};">{score.score}</div>
          <div>
            <span style="background:{cor};color:#fff;padding:4px 12px;border-radius:20px;
                         font-size:13px;font-weight:600;">{label}</span>
            <p style="font-size:12px;color:#666;margin:6px 0 0;">
              Prazo de ação: <strong>{prazo}</strong>
            </p>
          </div>
        </div>
      </div>

      <!-- Sinais -->
      <h3 style="font-size:14px;color:#1F2041;margin:0 0 8px;">Sinais Identificados</h3>
      <div style="font-size:13px;color:#333;margin-bottom:20px;">
        {_sinais_html(score)}
      </div>

      <!-- Últimos tickets -->
      <h3 style="font-size:14px;color:#1F2041;margin:0 0 8px;">Últimos 3 Tickets</h3>
      <div style="font-size:13px;color:#333;margin-bottom:20px;">
        {_tickets_html(score)}
      </div>

      <!-- CTA -->
      {"" if not link else f'''
      <a href="{link}" style="display:inline-block;background:#9349DE;color:#fff;
         padding:10px 20px;border-radius:8px;text-decoration:none;font-size:14px;
         font-weight:500;">
        Ver Playbook de Ação →
      </a>'''}
    </div>

    <!-- Rodapé -->
    <div style="background:#f5f5f5;padding:12px 24px;font-size:11px;color:#999;
                border-top:1px solid #eee;">
      Agente de IA Twygo · CS Intelligence · Este e-mail foi gerado automaticamente.
    </div>
  </div>
</body>
</html>"""


# ─── Envio via SendGrid ───────────────────────────────────────────────────────

def _enviar_sendgrid(destinatarios: list[str], assunto: str, html: str) -> bool:
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        sg = SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
        msg = Mail(
            from_email=os.getenv("ALERT_EMAIL_FROM", "cs@twygo.com"),
            to_emails=destinatarios,
            subject=assunto,
            html_content=html,
        )
        resp = sg.send(msg)
        logger.info(f"E-mail enviado via SendGrid para {destinatarios} — status {resp.status_code}")
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        logger.error(f"Falha no SendGrid: {e}. Tentando SMTP...")
        return False


def _enviar_smtp(destinatarios: list[str], assunto: str, html: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    remetente = os.getenv("ALERT_EMAIL_FROM", "cs@twygo.com")

    if not smtp_user:
        logger.error("SMTP_USER não configurado. Configure SMTP ou SendGrid.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = remetente
        msg["To"]      = ", ".join(destinatarios)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(remetente, destinatarios, msg.as_string())
        logger.info(f"E-mail enviado via SMTP para {destinatarios}")
        return True
    except Exception as e:
        logger.error(f"Falha no SMTP: {e}")
        return False


# ─── Dispatcher principal ─────────────────────────────────────────────────────

def disparar_alerta(cliente: Cliente, score_result: ScoreResult) -> bool:
    """
    - atencao / risco → e-mail para o CSM responsável
    - critico          → e-mail para o CSM E para a gerente de CS (Kelly)
    Retorna True se o envio foi bem-sucedido.
    """
    nivel = score_result.nivel
    if nivel == "saudavel":
        return True   # sem alerta para clientes saudáveis

    destinatarios: list[str] = []

    if cliente.csm_email:
        destinatarios.append(cliente.csm_email)

    if nivel == "critico":
        gerente = os.getenv("GERENTE_CS_EMAIL", "kelly@twygo.com")
        if gerente not in destinatarios:
            destinatarios.append(gerente)

    if not destinatarios:
        logger.warning(f"Nenhum destinatário para alertar sobre {cliente.nome}.")
        return False

    assunto = (
        f"[CRÍTICO] Reimplantação necessária — {cliente.nome}"
        if nivel == "critico"
        else f"[{_label_nivel(nivel)}] Risco de Reimplantação — {cliente.nome}"
    )
    html = _montar_html(cliente, score_result)

    # Tenta SendGrid; se falhar, usa SMTP
    if os.getenv("SENDGRID_API_KEY"):
        sucesso = _enviar_sendgrid(destinatarios, assunto, html)
    else:
        sucesso = False

    if not sucesso:
        sucesso = _enviar_smtp(destinatarios, assunto, html)

    return sucesso
