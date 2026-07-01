"""
app.py — Monitoramento de Risco de Reimplantação — Twygo CS

Lê dados-reais.json (tickets HubSpot 2026), identifica empresas
com alto volume de atendimentos e sinaliza necessidade de reimplantação.

Executar:
    streamlit run dashboard/app.py
"""

import sys, json, re, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from html import escape as he
from openai import OpenAI

_openai_client = None
def _get_openai():
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY", "")
        if key:
            _openai_client = OpenAI(api_key=key)
    return _openai_client

# ─── Config ───────────────────────────────────────────────────────────────────
# Caminho local (Windows) — ignorado no Streamlit Cloud, que busca via API
_LOCAL_JSON = Path(r"C:\Users\kelly\OneDrive\Documentos\Claude\Gestão de incidentes\dados-reais.json")
DADOS_REAIS = _LOCAL_JSON if _LOCAL_JSON.exists() else None

CORES = {
    "roxo":    "#9349DE",
    "dark":    "#1F2041",
    "verde":   "#2ECC71",
    "amarelo": "#F39C12",
    "laranja": "#E67E22",
    "vermelho":"#E74C3C",
    "azul":    "#3498DB",
    "cinza":   "#95A5A6",
}

LIMITE_MES = 3  # 3+ tickets no mesmo mês → sinal de reimplantação

# Categorias a excluir da análise de dores (não são atendimentos de dificuldade de uso)
CATEGORIAS_IGNORAR = {
    "implantação", "implantacao", "cancelamento",
    "criado pelo time comercial", "desenvolvimento",
    "plano e assinatura", "ajuste de assinatura",
    "inadimplência", "inadimplencia", "liberação de beta",
    "reversao_de_detrator", "reversão de detrator",
}

SUBJECTS_NPS = ["nps", "pesquisa de satisfação", "pesquisa de satisfacao",
                "detrator", "promotor", "nota ", "avaliação do atendimento",
                "avaliacao do atendimento", "reversao", "reversão"]

SUBJECTS_CANCELAMENTO = ["cancelamento", "cancela", "rescisão", "rescisao", "churn"]

# Nomes que parecem empresa mas não são clientes reais
EMPRESAS_IGNORAR = [
    "acordo novo", "novo(a) deal", "novo deal", "nova deal",
    "suporte do brasil", "support do brasil",
    "vencimento boleto", "inicio de conversa", "início de conversa",
    "twygo",
]


# Subjects genéricos a ignorar
SUBJECTS_IGNORAR = {
    "ticket chatbot (cliente)", "ticket chatbot", "início de conversa com cliente",
    "inicio de conversa com cliente", "indisponibilidade",
}

# ─── Classificação de dores ───────────────────────────────────────────────────
DORES = [
    ("Dificuldade de acesso / login",     True,  ["login", "acesso", "senha", "entrar", "bloqueio", "bloqueado", "acessar"]),
    ("Dúvida de uso da plataforma",       True,  ["dúvida", "duvida", "como", "como faz", "não sei", "ajuda"]),
    ("Conteúdo não carrega / não exibe",  True,  ["não carrega", "nao carrega", "não aparece", "nao aparece", "não abre", "não exibe", "visualiz"]),
    ("Problema de inscrição / matrícula", True,  ["inscri", "matrícula", "matricula", "indevidamente", "indevid"]),
    ("Questionário com problema",         True,  ["questionário", "questionario", "questão", "questao", "quiz", "reprovando"]),
    ("Certificado com problema",          True,  ["certificado", "certifica"]),
    ("Relatório / dados incorretos",      True,  ["relatório", "relatorio", "divergência", "divergencia", "dado errado", "bi ", "power bi"]),
    ("Pontuação ou ranking incorreto",    True,  ["pontuação", "pontuacao", "ranking"]),
    ("Erro / Bug técnico",                False, ["bug", "[bug]", "erro", "falha", "indisponib", "fuso"]),
    ("Solicitação de serviço",            False, ["[serviço]", "[servico]", "migração", "migracao", "inativação", "exclusão", "cpf", "alteração"]),
    ("Sugestão de melhoria",              False, ["melhoria", "sugestão", "sugestao", "[melhoria]"]),
    ("Studio / IA",                       False, ["studio", "estúdio", "crédito", "credito", "ia consumid"]),
    ("Acompanhamento / Reversão",         False, ["acompanhamento", "reversão", "reversao", "detrator"]),
]

def _classificar(subject: str, category: str) -> tuple[str, bool]:
    t = (subject + " " + category).lower()
    for nome, eh_uso, palavras in DORES:
        if any(p in t for p in palavras):
            return nome, eh_uso
    return "Outro atendimento", False

def _extrair_empresa(subject: str) -> str:
    """Extrai nome da empresa do subject do HubSpot."""
    s = (subject or "").strip()
    # Padrão: "Implantação - Empresa Nome" ou "[BUG] Desc - Empresa"
    m = re.search(r"\s[-]\s([A-Za-zÀ-ÿ0-9][^-\[\]]{2,50})$", s)
    if m:
        cand = m.group(1).strip()
        # Ignora se parece descrição técnica
        ignore = ["studio", "processo", "criar", "crédito", "melhoria", "dúvida", "atividade", "identifica"]
        if not any(p in cand.lower() for p in ignore) and len(cand) > 2:
            return cand
    return ""

def _parse_data(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except Exception:
        return None

def _mes_label(mes_str: str) -> str:
    try:
        return datetime.strptime(mes_str, "%Y-%m").strftime("%b/%Y")
    except Exception:
        return mes_str

# ─── Carregar e processar ─────────────────────────────────────────────────────
def _buscar_hubspot_api() -> list:
    """Busca tickets diretamente da API HubSpot (usado no Streamlit Cloud)."""
    hub_key = os.getenv("HUBSPOT_API_KEY", "")
    if not hub_key:
        return []

    headers = {"Authorization": f"Bearer {hub_key}", "Content-Type": "application/json"}
    properties = ["subject", "content", "hs_ticket_category", "hs_ticket_priority",
                  "hs_pipeline_stage", "createdate", "closed_date", "hubspot_owner_id"]

    # Owners
    try:
        r_own = requests.get("https://api.hubapi.com/crm/v3/owners?limit=100", headers=headers, timeout=15)
        owner_map = {o["id"]: f"{o.get('firstName','')} {o.get('lastName','')}".strip() or o.get("email","")
                     for o in r_own.json().get("results", [])}
    except Exception:
        owner_map = {}

    STAGES_FECHADOS = {"151512326","1301981612","1276861825","151781184",
                       "151382299","151382300","151550800","151550801"}

    inicio = datetime(2026, 1, 1)
    ontem  = datetime.utcnow().replace(hour=23, minute=59, second=59)
    todos, vistos = [], set()

    cursor = inicio
    while cursor < ontem:
        fim_mes = datetime(cursor.year, cursor.month % 12 + 1, 1) if cursor.month < 12 \
                  else datetime(cursor.year + 1, 1, 1)
        ate = min(fim_mes, ontem)
        after = None
        while True:
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": str(int(cursor.timestamp()*1000))},
                    {"propertyName": "createdate", "operator": "LTE", "value": str(int(ate.timestamp()*1000))},
                ]}],
                "properties": properties, "limit": 100,
                **({"after": after} if after else {}),
            }
            try:
                r = requests.post("https://api.hubapi.com/crm/v3/objects/tickets/search",
                                  json=body, headers=headers, timeout=20)
                data = r.json()
            except Exception:
                break
            for t in data.get("results", []):
                if t["id"] not in vistos:
                    vistos.add(t["id"])
                    p = t["properties"]
                    todos.append({
                        "hubId": t["id"],
                        "subject":   p.get("subject","") or "",
                        "content":   p.get("content","") or "",
                        "category":  p.get("hs_ticket_category","") or "",
                        "priority":  p.get("hs_ticket_priority","") or "",
                        "hubClosed": p.get("hs_pipeline_stage","") in STAGES_FECHADOS,
                        "createdate": p.get("createdate"),
                        "closedDate": p.get("closed_date"),
                        "hubOwner":  owner_map.get(p.get("hubspot_owner_id",""), None),
                        "artiaTitle": None, "artiaStatus": None,
                        "artiaClosed": None, "artiaResp": None, "artiaEnd": None,
                    })
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        cursor = fim_mes

    return todos


@st.cache_data(ttl=3600)
def carregar_dados():
    # Local (Windows): lê o JSON gerado pelo sync
    if DADOS_REAIS and DADOS_REAIS.exists():
        with open(DADOS_REAIS, encoding="utf-8-sig") as f:
            registros = json.load(f)
    else:
        # Cloud: busca direto da API HubSpot
        with st.spinner("Buscando tickets do HubSpot... (primeira carga ~30s)"):
            registros = _buscar_hubspot_api()
        if not registros:
            return [], {}


    # Filtrar tickets válidos para análise de dores
    uteis = []
    for r in registros:
        subj = (r.get("subject","") or "").strip()
        cat  = (r.get("category","") or "").strip().lower()
        subj_lower = subj.lower()

        # Ignorar categorias administrativas
        if any(ig in cat for ig in CATEGORIAS_IGNORAR):
            continue
        # Ignorar subjects genéricos
        if subj_lower in SUBJECTS_IGNORAR:
            continue
        if subj_lower.startswith("ticket n"):
            continue
        # Ignorar NPS e pesquisas de satisfação
        if any(p in subj_lower for p in SUBJECTS_NPS):
            continue
        if not subj:
            continue

        uteis.append(r)

    # Agrupar por empresa
    por_empresa: dict[str, list] = defaultdict(list)
    sem_empresa = []
    for r in uteis:
        emp = _extrair_empresa(r.get("subject",""))
        if emp:
            # Ignorar se o nome da empresa for "Cancelamento" ou similar
            if any(p in emp.lower() for p in SUBJECTS_CANCELAMENTO):
                continue
            if any(ig in emp.lower() for ig in EMPRESAS_IGNORAR):
                continue
            por_empresa[emp].append(r)
        else:
            sem_empresa.append(r)

    # Remover empresas onde a maioria dos tickets é de cancelamento
    por_empresa = {
        emp: tks for emp, tks in por_empresa.items()
        if not all(any(p in (t.get("subject","") or "").lower() for p in SUBJECTS_CANCELAMENTO) for t in tks)
    }

    # Analisar cada empresa
    resultados = []
    for emp, tickets in por_empresa.items():
        resultados.append(_analisar(emp, tickets))

    ordem = {"critico": 0, "atencao": 1, "observar": 2, "ok": 3}
    resultados_ord = sorted(resultados, key=lambda x: (ordem[x["nivel"]], -x["total"]))

    # Período real dos dados
    todas_datas = [
        _parse_data(r.get("createdate"))
        for r in registros if r.get("createdate")
    ]
    todas_datas = [d for d in todas_datas if d]
    periodo = {}
    if todas_datas:
        periodo["inicio"] = min(todas_datas).strftime("%b/%Y")
        periodo["fim"]    = max(todas_datas).strftime("%b/%Y")
        periodo["ultima_sync"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    return resultados_ord, periodo

def _analisar(emp: str, tickets: list) -> dict:
    por_mes: Counter = Counter()
    for t in tickets:
        d = _parse_data(t.get("createdate"))
        if d:
            por_mes[d.strftime("%Y-%m")] += 1

    mes_pico, qtd_pico = por_mes.most_common(1)[0] if por_mes else (None, 0)
    meses_acima = [m for m, q in por_mes.items() if q >= LIMITE_MES]

    dores_uso, dores_sist = [], []
    for t in tickets:
        cat, eh_uso = _classificar(t.get("subject",""), t.get("category",""))
        (dores_uso if eh_uso else dores_sist).append(cat)

    dores_uso_u  = list(dict.fromkeys(dores_uso))
    dores_sist_u = list(dict.fromkeys(dores_sist))
    pct_uso = len(dores_uso) / len(tickets) if tickets else 0

    if meses_acima and pct_uso >= 0.4:
        nivel = "critico"
    elif meses_acima:
        nivel = "atencao"
    elif pct_uso >= 0.5 and len(tickets) >= 2:
        nivel = "observar"
    else:
        nivel = "ok"

    resumo = _gerar_resumo(emp, tickets, qtd_pico, mes_pico, meses_acima, dores_uso_u, nivel)

    return {
        "empresa": emp, "total": len(tickets), "tickets": tickets,
        "por_mes": dict(por_mes), "mes_pico": mes_pico, "qtd_pico": qtd_pico,
        "meses_acima": meses_acima, "dores_uso": dores_uso_u,
        "dores_sist": dores_sist_u, "pct_uso": pct_uso, "nivel": nivel,
        "resumo": resumo,
    }

@st.cache_data(ttl=3600)
def _buscar_contato_hubspot(empresa_nome: str) -> dict:
    """Busca empresa e contatos no HubSpot. Retorna emails, URL da empresa e portal ID."""
    hub_key = os.getenv("HUBSPOT_API_KEY", "")
    if not hub_key:
        return {"erro": "Chave HubSpot não configurada."}

    headers = {"Authorization": f"Bearer {hub_key}", "Content-Type": "application/json"}

    try:
        # 1. Busca empresa por nome
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": empresa_nome}
            ]}],
            "properties": ["name"],
            "limit": 3,
        }
        r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/companies/search",
            json=body, headers=headers, timeout=10
        )
        companies = r.json().get("results", [])
        if not companies:
            return {"erro": f"Empresa '{empresa_nome}' não encontrada no HubSpot."}

        company_id = companies[0]["id"]

        # 2. Portal ID (para montar URL)
        r_portal = requests.get(
            "https://api.hubapi.com/account-info/v3/details",
            headers=headers, timeout=10
        )
        portal_id = r_portal.json().get("portalId", "")

        # 3. Contatos associados
        r2 = requests.get(
            f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}/associations/contacts",
            headers=headers, timeout=10
        )
        contact_ids = [c["id"] for c in r2.json().get("results", [])[:5]]

        # 4. E-mails dos contatos
        emails = []
        for cid in contact_ids:
            r3 = requests.get(
                f"https://api.hubapi.com/crm/v3/objects/contacts/{cid}?properties=email,firstname,lastname",
                headers=headers, timeout=10
            )
            props = r3.json().get("properties", {})
            email = props.get("email", "")
            nome  = f"{props.get('firstname','')} {props.get('lastname','')}".strip()
            if email:
                emails.append({"email": email, "nome": nome})

        hub_url = (
            f"https://app.hubspot.com/contacts/{portal_id}/company/{company_id}"
            if portal_id else ""
        )

        return {
            "company_id": company_id,
            "portal_id":  portal_id,
            "hub_url":    hub_url,
            "emails":     emails,
        }

    except Exception as e:
        return {"erro": str(e)}


def _montar_mailto(emails: list, assunto: str, corpo: str) -> str:
    """Monta link mailto: com destinatários, assunto e corpo pré-preenchidos."""
    to = ",".join(e["email"] for e in emails)
    return (
        f"mailto:{quote(to)}"
        f"?subject={quote(assunto)}"
        f"&body={quote(corpo)}"
    )


def _analisar_ia(emp: str, tickets: list) -> str:
    """Envia os tickets para a OpenAI e retorna análise da dor real do cliente."""
    client = _get_openai()
    if not client:
        return "⚠️ Chave OpenAI não configurada."

    linhas = []
    for t in tickets[:30]:  # limita a 30 tickets para controlar tokens
        subj    = (t.get("subject","") or "").strip()
        content = (t.get("content","") or "").strip()
        data    = _parse_data(t.get("createdate"))
        data_s  = data.strftime("%d/%m/%Y") if data else ""
        pri     = t.get("priority","")
        linha   = f"- [{data_s}] {subj}"
        if content:
            # remove HTML tags do content
            content_clean = re.sub(r"<[^>]+>", " ", content).strip()
            content_clean = re.sub(r"\s+", " ", content_clean)[:300]
            linha += f"\n  Descrição: {content_clean}"
        if pri in ("HIGH","URGENT"):
            linha += " [ALTA PRIORIDADE]"
        linhas.append(linha)

    tickets_txt = "\n".join(linhas)

    prompt = f"""Você é especialista em Customer Success de plataformas SaaS de e-learning.

Analise os atendimentos de suporte da empresa "{emp}" e identifique:

1. **Dor real do cliente** — o que de fato está impedindo ou dificultando o uso da plataforma no dia a dia (não apenas o sintoma superficial)
2. **Padrão identificado** — existe um problema recorrente? Qual a frequência e o impacto?
3. **Risco de churn** — avalie o risco (alto/médio/baixo) com justificativa
4. **Ação recomendada para o CSM** — o que fazer concretamente nas próximas 48h

Seja objetivo, direto e em português. Use no máximo 250 palavras.

Atendimentos:
{tickets_txt}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Erro na análise: {e}"


def _gerar_comunicado_ia(emp: str, analise_ia: str, nivel: str) -> str:
    """Gera rascunho de comunicado para a CS enviar ao cliente."""
    client = _get_openai()
    if not client:
        return "⚠️ Chave OpenAI não configurada."

    urgencia = {
        "critico":  "O cliente está em risco crítico de churn e precisa de atenção imediata.",
        "atencao":  "O cliente apresenta sinais de dificuldade e precisa de acompanhamento próximo.",
        "observar": "O cliente tem algumas dificuldades pontuais que merecem atenção preventiva.",
    }.get(nivel, "")

    prompt = f"""Você é a Kelly Borba, Customer Success Manager da Twygo, plataforma de e-learning corporativo.

Contexto do cliente "{emp}":
{analise_ia}

{urgencia}

Escreva um e-mail profissional e empático para o gestor de T&D da empresa "{emp}":
- Cumprimento personalizado (sem "Prezado(a) [nome]" — use o nome da empresa)
- Reconheça que percebeu as dificuldades (sem citar "tickets" — use "nos acionaram" ou "identificamos")
- Proponha uma agenda de engajamento com data flexível esta semana ou na próxima
- Mostre que a Twygo quer garantir o sucesso do cliente
- Assinatura: Kelly Borba | Customer Success Manager | Twygo | kelly.borba@twygo.com

Tom: próximo, prestativo e proativo. Máximo 200 palavras."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Erro ao gerar comunicado: {e}"


def _gerar_resumo(emp, tickets, qtd_pico, mes_pico, meses_acima, dores_uso, nivel):
    total = len(tickets)
    alta  = sum(1 for t in tickets if t.get("priority") in ("HIGH","URGENT"))
    partes = []

    if meses_acima:
        if len(meses_acima) == 1:
            partes.append(f"abriu **{qtd_pico} atendimentos em {_mes_label(meses_acima[0])}**, acima do limite de {LIMITE_MES} por mês")
        else:
            meses_fmt = ", ".join(_mes_label(m) for m in sorted(meses_acima))
            partes.append(f"ultrapassou **{LIMITE_MES} atendimentos/mês em {len(meses_acima)} meses** ({meses_fmt})")
    else:
        partes.append(f"registrou **{total} atendimento{'s' if total>1 else ''}** no período")

    if dores_uso:
        lista = " e ".join(f"**{d.lower()}**" for d in dores_uso[:3])
        partes.append(f"com dificuldades em {lista}")

    if alta:
        partes.append(f"sendo {alta} de alta prioridade")

    acao = {
        "critico":  "**Reimplantação urgente recomendada** — volume alto + dificuldades de uso recorrentes. Risco de churn elevado.",
        "atencao":  "**Avaliar necessidade de reimplantação** — volume de atendimentos acima do esperado. Verificar se o cliente usa a plataforma com autonomia.",
        "observar": "**Monitorar** — dificuldades de uso detectadas, mas volume ainda dentro do esperado.",
        "ok":       "Sem indicativo de reimplantação no momento.",
    }.get(nivel, "")

    return "Esta empresa " + ", ".join(partes) + ". " + acao

# ─── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Twygo · Monitoramento de Risco",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
  /* ── Sidebar fundo escuro ── */
  [data-testid="stSidebar"] {{ background:{CORES["dark"]}; }}

  /* Apenas textos estáticos em branco — não toca em elementos interativos */
  [data-testid="stSidebar"] .stMarkdown p,
  [data-testid="stSidebar"] .stMarkdown div,
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stCheckbox  label p,
  [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3, [data-testid="stSidebar"] small {{
    color:#fff !important;
  }}

  /* Botão recarregar */
  [data-testid="stSidebar"] .stButton button {{
    color:#fff !important; background:{CORES["roxo"]} !important;
    border:none !important; border-radius:8px !important;
  }}
  [data-testid="stSidebar"] .stButton button:hover {{
    background:#7b2fbe !important;
  }}
  .metric-card {{
    background:#fff; border-radius:12px; padding:18px 20px;
    border-top:4px solid {CORES["roxo"]};
    box-shadow:0 2px 8px rgba(0,0,0,0.07); text-align:center;
  }}
  .metric-num   {{ font-size:34px; font-weight:700; }}
  .metric-label {{ font-size:12px; color:#666; margin-top:4px; }}
  .empresa-card {{
    background:#fff; border-radius:12px; padding:20px 24px 16px;
    margin-bottom:16px; box-shadow:0 2px 8px rgba(0,0,0,0.07);
  }}
  .nivel-critico  {{ border-left:5px solid {CORES["vermelho"]}; }}
  .nivel-atencao  {{ border-left:5px solid {CORES["laranja"]}; }}
  .nivel-observar {{ border-left:5px solid {CORES["amarelo"]}; }}
  .nivel-ok       {{ border-left:5px solid {CORES["verde"]}; }}
  .empresa-nome {{ font-size:18px; font-weight:700; color:{CORES["dark"]}; margin-bottom:8px; }}
  .resumo-texto {{ color:#444; font-size:14px; line-height:1.7; margin:10px 0; }}
  .dor-tag {{
    display:inline-block; background:#f0e8fd; color:{CORES["roxo"]};
    border-radius:20px; padding:3px 12px; font-size:12px;
    font-weight:600; margin:2px 4px 2px 0;
  }}
  .sist-tag {{
    display:inline-block; background:#f0f0f0; color:#666;
    border-radius:20px; padding:3px 12px; font-size:12px; margin:2px 4px 2px 0;
  }}
  .ticket-item {{
    padding:8px 14px; border-left:3px solid #ddd; margin:4px 0;
    font-size:13px; color:#444; background:#fafafa; border-radius:0 6px 6px 0;
  }}
</style>
""", unsafe_allow_html=True)

# ─── Carregar dados ────────────────────────────────────────────────────────────
dados, periodo = carregar_dados()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center;padding:20px 0 28px;">
      <div style="font-size:32px;">🔍</div>
      <div style="font-size:18px;font-weight:700;">Inteligência CS</div>
      <div style="font-size:12px;color:#aaa;margin-top:2px;">TWYGO</div>
    </div>""", unsafe_allow_html=True)

    NIVEL_EMOJI = {"critico": "🔴", "atencao": "🟠", "observar": "🟡", "ok": "🟢"}
    opcoes = ["Todas as empresas"] + [
        f"{NIVEL_EMOJI.get(d['nivel'],'')} {d['empresa']}" for d in dados
    ]
    sel = st.selectbox("🔎 Selecionar empresa", options=opcoes)
    busca = "" if sel == "Todas as empresas" else sel.split(" ", 1)[1]

    st.markdown("---")
    st.markdown("**Filtrar por nível:**")
    f_critico  = st.checkbox("🔴 Reimplantação urgente", value=True)
    f_atencao  = st.checkbox("🟠 Avaliar reimplantação",  value=True)
    f_observar = st.checkbox("🟡 Monitorar",              value=False)
    f_ok       = st.checkbox("🟢 Sem indicativo",         value=False)

    st.markdown("---")
    if st.button("🔄 Recarregar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if not dados:
    st.error(f"Arquivo não encontrado: `{DADOS_REAIS}`")
    st.stop()

# ─── Filtros ──────────────────────────────────────────────────────────────────
niveis_ativos = []
if f_critico:  niveis_ativos.append("critico")
if f_atencao:  niveis_ativos.append("atencao")
if f_observar: niveis_ativos.append("observar")
if f_ok:       niveis_ativos.append("ok")

filtrados = [
    d for d in dados
    if d["nivel"] in niveis_ativos
    and (not busca or busca.lower() in d["empresa"].lower())
]

# ─── Métricas ──────────────────────────────────────────────────────────────────
n_critico  = sum(1 for d in dados if d["nivel"] == "critico")
n_atencao  = sum(1 for d in dados if d["nivel"] == "atencao")
n_observar = sum(1 for d in dados if d["nivel"] == "observar")
n_ok       = sum(1 for d in dados if d["nivel"] == "ok")

periodo_label = f"{periodo.get('inicio','?')} a {periodo.get('fim','?')}" if periodo else "—"
ultima_sync   = periodo.get("ultima_sync", "—") if periodo else "—"

st.markdown("## 🔍 Monitoramento de Risco — Reimplantação")
st.caption(
    f"Empresas com {LIMITE_MES}+ atendimentos no mesmo mês sinalizadas como risco de churn. "
    f"Dados: **{periodo_label}** · Última atualização: {ultima_sync}"
)

NIVEL_CONFIG = {
    "critico":  ("🔴 Reimplantação urgente", CORES["vermelho"]),
    "atencao":  ("🟠 Avaliar reimplantação",  CORES["laranja"]),
    "observar": ("🟡 Monitorar",              CORES["amarelo"]),
    "ok":       ("🟢 Sem indicativo",         CORES["verde"]),
}

# ─── Métricas topo ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
for col, num, label, cor in [
    (c1, len(dados),  "Total de empresas",        CORES["roxo"]),
    (c2, n_critico,   "🔴 Reimplantação urgente", CORES["vermelho"]),
    (c3, n_atencao,   "🟠 Avaliar reimplantação",  CORES["laranja"]),
    (c4, n_observar,  "🟡 Monitorar",              CORES["amarelo"]),
    (c5, n_ok,        "🟢 Sem indicativo",         CORES["verde"]),
]:
    col.markdown(f"""
    <div class="metric-card">
      <div class="metric-num" style="color:{cor};">{num}</div>
      <div class="metric-label">{label}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── Abas ─────────────────────────────────────────────────────────────────────
aba1, aba2 = st.tabs(["🏢 Monitoramento de Risco", "📊 Painel de Indicadores"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — Cards de risco por empresa
# ══════════════════════════════════════════════════════════════════════════════
with aba1:
    st.markdown(f"### 🏢 {len(filtrados)} empresa(s) exibida(s)")

    if not filtrados:
        st.info("Nenhuma empresa com os filtros selecionados.")
    else:
        for d in filtrados:
            nivel_label, nivel_cor = NIVEL_CONFIG[d["nivel"]]

            tags_uso  = "".join(f'<span class="dor-tag">⚠ {he(t)}</span>'  for t in d["dores_uso"])
            tags_sist = "".join(f'<span class="sist-tag">🔧 {he(t)}</span>' for t in d["dores_sist"])

            meses_str = " &nbsp;|&nbsp; ".join(
                f"<b>{he(_mes_label(m))}</b>: {q} atend."
                for m, q in sorted(d["por_mes"].items())
            ) if d["por_mes"] else ""

            resumo_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', he(d["resumo"]))

            st.markdown(f"""
            <div class="empresa-card nivel-{d['nivel']}">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div class="empresa-nome">🏢 {he(d["empresa"])}</div>
                <span style="background:{nivel_cor};color:#fff;border-radius:8px;
                             padding:3px 14px;font-size:12px;font-weight:700;white-space:nowrap;">
                  {he(nivel_label)}
                </span>
              </div>
              <div style="font-size:12px;color:#888;margin-bottom:10px;">{meses_str}</div>
              <div style="margin-bottom:10px;">{tags_uso}{tags_sist}</div>
              <div class="resumo-texto">📝 {resumo_html}</div>
            </div>
            """, unsafe_allow_html=True)

            # ── Análise com IA ────────────────────────────────────────────────
            if d["nivel"] in ("critico", "atencao", "observar"):
                col_ia1, col_ia2 = st.columns(2)
                chave_analise   = f"ia_analise_{d['empresa']}"
                chave_comunicado = f"ia_comunicado_{d['empresa']}"

                with col_ia1:
                    if st.button(f"🤖 Analisar dor real com IA", key=f"btn_ia_{d['empresa']}",
                                 use_container_width=True):
                        with st.spinner("Analisando com GPT-4o-mini..."):
                            st.session_state[chave_analise] = _analisar_ia(d["empresa"], d["tickets"])

                with col_ia2:
                    if st.button(f"✉️ Gerar comunicado para CS", key=f"btn_com_{d['empresa']}",
                                 use_container_width=True,
                                 disabled=chave_analise not in st.session_state):
                        with st.spinner("Gerando comunicado..."):
                            st.session_state[chave_comunicado] = _gerar_comunicado_ia(
                                d["empresa"],
                                st.session_state.get(chave_analise, ""),
                                d["nivel"]
                            )

                if chave_analise in st.session_state:
                    st.markdown("**🤖 Análise da dor real (IA):**")
                    st.info(st.session_state[chave_analise])

                if chave_comunicado in st.session_state:
                    st.markdown("**✉️ Rascunho de comunicado para CS:**")
                    st.success(st.session_state[chave_comunicado])

                    # ── Botões de envio ───────────────────────────────────────
                    chave_contato = f"hub_contato_{d['empresa']}"

                    # Busca contato HubSpot ao primeiro clique
                    if chave_contato not in st.session_state:
                        with st.spinner("Buscando contatos no HubSpot..."):
                            st.session_state[chave_contato] = _buscar_contato_hubspot(d["empresa"])

                    info_hub = st.session_state[chave_contato]

                    if "erro" in info_hub:
                        st.warning(f"HubSpot: {info_hub['erro']}")
                        # Fallback: download txt
                        st.download_button(
                            "⬇ Baixar comunicado (.txt)",
                            data=st.session_state[chave_comunicado],
                            file_name=f"comunicado_{d['empresa'].replace(' ','_')}.txt",
                            mime="text/plain",
                            key=f"dl_{d['empresa']}",
                        )
                    else:
                        emails_hub = info_hub.get("emails", [])
                        hub_url    = info_hub.get("hub_url", "")

                        if emails_hub:
                            assunto = f"Agenda de Engajamento — Twygo × {d['empresa']}"
                            corpo   = st.session_state[chave_comunicado]
                            mailto  = _montar_mailto(emails_hub, assunto, corpo)

                            # Mostra os e-mails encontrados
                            nomes_emails = ", ".join(
                                f"{e['nome']} <{e['email']}>" if e['nome'] else e['email']
                                for e in emails_hub
                            )
                            st.caption(f"📬 Contatos encontrados no HubSpot: **{nomes_emails}**")

                            col_e1, col_e2 = st.columns(2)
                            with col_e1:
                                # Abre e-mail pré-preenchido (Gmail/Outlook/HubSpot extension)
                                st.link_button(
                                    "📧 Abrir e-mail pré-preenchido",
                                    url=mailto,
                                    use_container_width=True,
                                    type="primary",
                                )
                            with col_e2:
                                if hub_url:
                                    st.link_button(
                                        "🏢 Ver empresa no HubSpot",
                                        url=hub_url,
                                        use_container_width=True,
                                    )
                        else:
                            st.warning("Nenhum contato com e-mail encontrado para esta empresa no HubSpot.")
                            if hub_url:
                                st.link_button("🏢 Abrir empresa no HubSpot para adicionar contato", url=hub_url)
                            st.download_button(
                                "⬇ Baixar comunicado (.txt)",
                                data=st.session_state[chave_comunicado],
                                file_name=f"comunicado_{d['empresa'].replace(' ','_')}.txt",
                                mime="text/plain",
                                key=f"dl_{d['empresa']}",
                            )

            with st.expander(f"Ver {d['total']} atendimento(s) de {d['empresa']}"):
                for t in sorted(d["tickets"], key=lambda x: (x.get("priority","") not in ("HIGH","URGENT"), x.get("createdate",""))):
                    subj   = (t.get("subject","") or "Sem título").strip()
                    pri    = t.get("priority","")
                    hub_id = t.get("hubId","")
                    owner  = t.get("hubOwner","") or "—"
                    data_c = _parse_data(t.get("createdate"))
                    data_s = data_c.strftime("%d/%m/%Y") if data_c else "—"
                    cat, eh_uso = _classificar(subj, t.get("category",""))
                    fechado = t.get("hubClosed", True)
                    cor_borda = CORES["roxo"] if eh_uso else "#ccc"
                    pri_label = {"HIGH": "🔴 Alta", "URGENT": "🚨 Urgente", "MEDIUM": "🟡 Média", "LOW": "🔵 Baixa"}.get(pri, "—")
                    status    = "✓ Encerrado" if fechado else "🔓 Em aberto"
                    content_raw = (t.get("content","") or "").strip()
                    content_clean = re.sub(r"<[^>]+>", " ", content_raw)
                    content_clean = re.sub(r"\s+", " ", content_clean).strip()[:400]

                    st.markdown(f"""
                    <div class="ticket-item" style="border-left-color:{cor_borda};">
                      <div style="font-weight:600;color:{CORES['dark']};">#{he(str(hub_id))} — {he(subj[:90])}</div>
                      <div style="font-size:12px;color:#888;margin-top:3px;">
                        🏷 {he(cat)} &nbsp;|&nbsp; {pri_label} &nbsp;|&nbsp; 👤 {he(owner)} &nbsp;|&nbsp; 📅 {data_s} &nbsp;|&nbsp; {status}
                      </div>
                      {f'<div style="font-size:12px;color:#555;margin-top:6px;font-style:italic;">{he(content_clean)}</div>' if content_clean else ''}
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("---")
        with st.expander("📥 Exportar tabela de risco"):
            linhas = []
            for d in dados:
                linhas.append({
                    "Empresa":            d["empresa"],
                    "Nível":              NIVEL_CONFIG[d["nivel"]][0],
                    "Total atendimentos": d["total"],
                    "Mês com mais atend.":d["mes_pico"] or "—",
                    "Qtd no pico":        d["qtd_pico"],
                    "Dores de uso":       ", ".join(d["dores_uso"]) or "—",
                    "Análise":            d["resumo"].replace("**",""),
                })
            df_exp = pd.DataFrame(linhas)
            st.dataframe(df_exp, use_container_width=True, hide_index=True)
            csv = df_exp.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇ Baixar CSV", data=csv, file_name="risco_reimplantacao_twygo.csv", mime="text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — Painel de Indicadores / Funil
# ══════════════════════════════════════════════════════════════════════════════
with aba2:
    st.markdown("### 📊 Painel de Indicadores — Quem nos aciona e por quê")
    st.caption(f"Visão geral de todos os tickets de {periodo_label} para tomada de decisão e ações preventivas.")

    # Carregar todos os tickets brutos para análise geral
    if DADOS_REAIS and DADOS_REAIS.exists():
        with open(DADOS_REAIS, encoding="utf-8-sig") as _f:
            todos_raw = json.load(_f)
    else:
        todos_raw = _buscar_hubspot_api()

    # Filtrar chatbot e genéricos
    todos_validos = [
        r for r in todos_raw
        if (r.get("subject","") or "").strip().lower() not in SUBJECTS_IGNORAR
        and not (r.get("subject","") or "").strip().lower().startswith("ticket n")
        and (r.get("subject","") or "").strip()
    ]

    total_val = len(todos_validos)
    abertos   = sum(1 for r in todos_validos if not r.get("hubClosed"))
    urgentes  = sum(1 for r in todos_validos if r.get("priority") in ("HIGH","URGENT"))

    # ── KPIs ─────────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    for col, num, label, cor in [
        (k1, total_val, "Atendimentos analisados", CORES["roxo"]),
        (k2, abertos,   "Em aberto agora",          CORES["laranja"]),
        (k3, urgentes,  "Alta / Urgente prioridade", CORES["vermelho"]),
        (k4, len({_extrair_empresa(r.get("subject","")) for r in todos_validos if _extrair_empresa(r.get("subject",""))}),
             "Empresas identificadas", CORES["verde"]),
    ]:
        col.markdown(f"""
        <div class="metric-card">
          <div class="metric-num" style="color:{cor};">{num}</div>
          <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    # ── Top empresas que mais acionam ────────────────────────────────────────
    with col_a:
        st.markdown("#### 🏆 Empresas que mais abriram atendimentos")
        cont_emp: Counter = Counter()
        for r in todos_validos:
            emp = _extrair_empresa(r.get("subject",""))
            if emp and not any(ig in emp.lower() for ig in EMPRESAS_IGNORAR) \
               and not any(p in emp.lower() for p in SUBJECTS_CANCELAMENTO):
                cont_emp[emp] += 1

        top_emp = cont_emp.most_common(15)
        if top_emp:
            df_emp = pd.DataFrame(top_emp, columns=["Empresa", "Atendimentos"])
            df_emp.index = df_emp.index + 1
            st.dataframe(
                df_emp,
                use_container_width=True,
                hide_index=False,
                column_config={
                    "Empresa":       st.column_config.TextColumn("Empresa", width="large"),
                    "Atendimentos":  st.column_config.ProgressColumn(
                        "Atendimentos", min_value=0,
                        max_value=int(df_emp["Atendimentos"].max()),
                    ),
                }
            )

    # ── Motivos mais frequentes ───────────────────────────────────────────────
    with col_b:
        st.markdown("#### 🏷 Motivos mais frequentes de acionamento")
        cont_cat: Counter = Counter()
        for r in todos_validos:
            cat, _ = _classificar(r.get("subject",""), r.get("category",""))
            cont_cat[cat] += 1

        top_cat = cont_cat.most_common(12)
        if top_cat:
            df_cat = pd.DataFrame(top_cat, columns=["Motivo", "Quantidade"])
            df_cat.index = df_cat.index + 1
            st.dataframe(
                df_cat,
                use_container_width=True,
                hide_index=False,
                column_config={
                    "Motivo":     st.column_config.TextColumn("Motivo", width="large"),
                    "Quantidade": st.column_config.ProgressColumn(
                        "Quantidade", min_value=0,
                        max_value=int(df_cat["Quantidade"].max()),
                    ),
                }
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Evolução por mês ─────────────────────────────────────────────────────
    st.markdown("#### 📅 Volume de atendimentos por mês")
    cont_mes: Counter = Counter()
    for r in todos_validos:
        d = _parse_data(r.get("createdate"))
        if d:
            cont_mes[d.strftime("%Y-%m")] += 1

    if cont_mes:
        meses_ord = sorted(cont_mes.keys())
        fig = go.Figure(go.Bar(
            x=[_mes_label(m) for m in meses_ord],
            y=[cont_mes[m] for m in meses_ord],
            marker_color=CORES["roxo"],
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            height=300,
            xaxis=dict(categoryorder="array", categoryarray=[_mes_label(m) for m in meses_ord]),
            yaxis_title="Atendimentos",
            plot_bgcolor="#fff",
            paper_bgcolor="#fff",
        )
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    # ── Analistas com mais atendimentos ──────────────────────────────────────
    with col_c:
        st.markdown("#### 👤 Analistas N1 com mais atendimentos")
        cont_owner: Counter = Counter()
        for r in todos_validos:
            owner = r.get("hubOwner","") or "Sem analista"
            cont_owner[owner] += 1

        top_owner = cont_owner.most_common(10)
        df_owner = pd.DataFrame(top_owner, columns=["Analista N1", "Atendimentos"])
        df_owner.index = df_owner.index + 1
        st.dataframe(
            df_owner,
            use_container_width=True,
            hide_index=False,
            column_config={
                "Analista N1":  st.column_config.TextColumn("Analista N1", width="large"),
                "Atendimentos": st.column_config.ProgressColumn(
                    "Atendimentos", min_value=0,
                    max_value=int(df_owner["Atendimentos"].max()),
                ),
            }
        )

    # ── Motivos por empresa (top 10) ─────────────────────────────────────────
    with col_d:
        st.markdown("#### 🔎 Por que cada empresa mais aciona")
        linhas_motivo = []
        for emp, qtd in cont_emp.most_common(10):
            tks_emp = [r for r in todos_validos if _extrair_empresa(r.get("subject","")) == emp]
            cats = Counter(_classificar(r.get("subject",""), r.get("category",""))[0] for r in tks_emp)
            motivo_principal = cats.most_common(1)[0][0] if cats else "—"
            linhas_motivo.append({
                "Empresa":           emp,
                "Total":             qtd,
                "Principal motivo":  motivo_principal,
            })
        df_motivo = pd.DataFrame(linhas_motivo)
        df_motivo.index = df_motivo.index + 1
        st.dataframe(
            df_motivo,
            use_container_width=True,
            hide_index=False,
            column_config={
                "Empresa":          st.column_config.TextColumn("Empresa", width="medium"),
                "Total":            st.column_config.NumberColumn("Total", width="small"),
                "Principal motivo": st.column_config.TextColumn("Principal motivo", width="large"),
            }
        )

    # ── Exportar indicadores ─────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📥 Exportar dados completos"):
        linhas_full = []
        for r in todos_validos:
            cat, eh_uso = _classificar(r.get("subject",""), r.get("category",""))
            emp = _extrair_empresa(r.get("subject","")) or "—"
            d   = _parse_data(r.get("createdate"))
            linhas_full.append({
                "Empresa":        emp,
                "Ticket #":       r.get("hubId",""),
                "Assunto":        (r.get("subject","") or "")[:80],
                "Motivo":         cat,
                "Dificuldade uso":("Sim" if eh_uso else "Não"),
                "Prioridade":     r.get("priority",""),
                "Status":         "Fechado" if r.get("hubClosed") else "Aberto",
                "Analista N1":    r.get("hubOwner","") or "—",
                "Data":           d.strftime("%d/%m/%Y") if d else "—",
                "Mês":            d.strftime("%b/%Y") if d else "—",
            })
        df_full = pd.DataFrame(linhas_full)
        st.dataframe(df_full, use_container_width=True, hide_index=True)
        csv_full = df_full.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇ Baixar CSV completo", data=csv_full,
                           file_name="indicadores_atendimentos_twygo.csv", mime="text/csv")
