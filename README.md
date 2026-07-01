# Twygo CS Intelligence — Agente de Reimplantação

Monitora atendimentos de suporte via HubSpot e identifica automaticamente clientes que precisam de uma nova rodada de implantação/treinamento, calculando um **score de risco** e alertando o CSM responsável.

---

## Como funciona

```
HubSpot Tickets
      │
      ▼
Classificação via GPT-4o-mini
(tipo, frustração, tema)
      │
      ▼
Cálculo do Score de Risco (0–100)
(7 sinais com pesos diferentes)
      │
      ├── Score subiu de faixa ou é CRÍTICO?
      │         │
      │         ▼
      │    Disparo de alerta por e-mail
      │    (CSM + Gerente se crítico)
      │
      ▼
Histórico salvo + HubSpot atualizado
      │
      ▼
Dashboard Streamlit (visualização)
```

---

## Sinais de Risco

| Sinal | Peso |
|---|---|
| Ticket básico repetido (mesmo tema 2+ vezes em 30 dias) | 30 |
| ADM atual ≠ ADM do onboarding original | 25 |
| Nenhum login do ADM em 14+ dias | 20 |
| Mais de 5 tickets no mês | 15 |
| Frustração detectada pela IA | 15 |
| Funcionalidade contratada nunca usada | 10 |
| Trilha de onboarding incompleta (< 80%) | 10 |

## Níveis de Risco

| Nível | Score | Prazo de ação |
|---|---|---|
| ✅ Saudável | 0–20 | — |
| ⚠️ Atenção | 21–50 | 5 dias úteis |
| 🔶 Risco | 51–70 | 2 dias úteis |
| 🔴 Crítico | 71–100 | Mesmo dia |

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/twygo/cs-intelligence.git
cd cs-intelligence
```

### 2. Criar ambiente virtual

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

Variáveis necessárias:

| Variável | Descrição |
|---|---|
| `HUBSPOT_API_KEY` | Token do Private App HubSpot (escopos: CRM, Tickets, Owners) |
| `OPENAI_API_KEY` | Chave da API OpenAI |
| `SENDGRID_API_KEY` | Chave SendGrid (ou configure SMTP abaixo) |
| `ALERT_EMAIL_FROM` | E-mail remetente dos alertas |
| `GERENTE_CS_EMAIL` | E-mail da gerente de CS (recebe alertas críticos) |

---

## Propriedades customizadas no HubSpot

Crie estas propriedades no objeto **Company** antes de rodar o script:

| Nome interno | Tipo | Descrição |
|---|---|---|
| `twygo_email_adm_onboarding` | Texto | E-mail do ADM no onboarding |
| `twygo_email_adm_atual` | Texto | E-mail do ADM atual |
| `twygo_ultimo_login_adm` | Data/hora | Último login do ADM (em ms) |
| `twygo_percentual_onboarding` | Número | % conclusão da trilha (0–100) |
| `twygo_modulos_contratados` | Texto | Módulos separados por `;` |
| `twygo_modulos_nunca_usados` | Texto | Módulos nunca acessados |
| `twygo_score_risco` | Texto | Score calculado pelo agente |
| `twygo_nivel_risco` | Texto | Nível de risco atual |
| `twygo_acao_tomada` | Booleano | CSM marcou ação como tomada |

---

## Execução

### Análise diária (script principal)

```bash
python scripts/run_daily_analysis.py
```

### Dashboard

```bash
streamlit run dashboard/app.py
```

Acesse em: [http://localhost:8501](http://localhost:8501)

### Testes

```bash
pytest tests/ -v
# Com cobertura:
pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## Agendamento automático

O arquivo `.github/workflows/daily_analysis.yml` agenda a execução **toda segunda a sexta às 08h00 BRT**.

Configure os Secrets no repositório do GitHub:
- `Settings → Secrets and variables → Actions`
- Adicione todas as variáveis do `.env.example`

---

## Estrutura do projeto

```
twygo-agente-reimplantacao/
├── config.py                    # pesos, faixas e configurações
├── src/
│   ├── models.py                # Pydantic models (Cliente, Ticket, ScoreResult)
│   ├── hubspot_client.py        # integração HubSpot API
│   ├── ai_classifier.py         # classificação de tickets via GPT
│   ├── risk_calculator.py       # cálculo do score de risco
│   ├── alert_dispatcher.py      # envio de alertas por e-mail
│   └── dashboard_data.py        # persistência local (JSON)
├── dashboard/
│   ├── app.py                   # Streamlit app
│   └── components.py            # componentes visuais
├── scripts/
│   └── run_daily_analysis.py    # orquestrador da análise diária
├── tests/
│   ├── test_risk_calculator.py  # 15+ casos de teste
│   └── test_ai_classifier.py    # testes com mock da OpenAI
├── data/
│   └── clientes_monitorados.json # cache local dos scores
├── .github/workflows/
│   └── daily_analysis.yml       # GitHub Actions (agendamento)
├── requirements.txt
├── .env.example
└── README.md
```
