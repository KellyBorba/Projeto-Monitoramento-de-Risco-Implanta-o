"""
test_risk_calculator.py — Testes unitários para o cálculo de score de risco.
Executar: pytest tests/ -v
"""

from __future__ import annotations
import pytest
from datetime import datetime, timedelta, timezone

from src.models import Cliente, Ticket
from src.risk_calculator import calcular_score


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _cliente_base(**kwargs) -> Cliente:
    defaults = dict(
        id="EMP-001",
        nome="Empresa Teste",
        csm_email="csm@twygo.com",
        csm_nome="CSM Teste",
        email_adm_onboarding="adm@empresa.com",
        email_adm_atual="adm@empresa.com",
        percentual_onboarding=100.0,
        modulos_contratados=["LMS", "Gestão de Pessoas"],
        modulos_nunca_usados=[],
    )
    defaults.update(kwargs)
    return Cliente(**defaults)


def _ticket(tipo="basico", tema="configuração de vídeo", frustracao=False, horas_atras=24) -> Ticket:
    criado = datetime.now(timezone.utc) - timedelta(hours=horas_atras)
    return Ticket(
        id=f"T-{horas_atras}",
        company_id="EMP-001",
        assunto="Assunto do ticket",
        descricao="Descrição do ticket",
        criado_em=criado,
        tipo=tipo,
        tem_frustracao=frustracao,
        tema_resumido=tema,
    )


# ─── Testes: score baixo (saudável) ──────────────────────────────────────────

class TestScoreSaudavel:
    def test_sem_tickets_score_zero(self):
        cliente = _cliente_base()
        result = calcular_score(cliente, [])
        assert result.score == 0
        assert result.nivel == "saudavel"
        assert result.sinais_identificados == []

    def test_ticket_unico_basico_sem_frustracao(self):
        cliente = _cliente_base()
        tickets = [_ticket(tipo="basico", frustracao=False)]
        result = calcular_score(cliente, tickets)
        assert result.score <= 20
        assert result.nivel == "saudavel"

    def test_ticket_avancado_sem_outros_sinais(self):
        cliente = _cliente_base()
        tickets = [_ticket(tipo="avancado", frustracao=False)]
        result = calcular_score(cliente, tickets)
        assert result.nivel == "saudavel"


# ─── Testes: score médio (atenção) ────────────────────────────────────────────

class TestScoreAtencao:
    def test_ticket_basico_repetido_dispara_sinal(self):
        cliente = _cliente_base()
        # Dois tickets com tema similar → sinal de 30 pontos
        tickets = [
            _ticket(tipo="basico", tema="configuração de vídeo", horas_atras=48),
            _ticket(tipo="basico", tema="vídeo configuração",    horas_atras=24),
        ]
        result = calcular_score(cliente, tickets)
        assert "ticket_basico_repetido" in result.sinais_identificados
        assert result.score >= 21

    def test_mais_de_5_tickets_no_mes(self):
        cliente = _cliente_base()
        tickets = [_ticket(tipo="avancado", horas_atras=i*10) for i in range(1, 7)]
        result = calcular_score(cliente, tickets)
        assert "mais_de_5_tickets_mes" in result.sinais_identificados

    def test_frustracao_detectada(self):
        cliente = _cliente_base()
        tickets = [_ticket(tipo="basico", frustracao=True)]
        result = calcular_score(cliente, tickets)
        assert "frase_frustracao_detectada" in result.sinais_identificados
        assert result.score >= 15


# ─── Testes: score alto (risco) ───────────────────────────────────────────────

class TestScoreRisco:
    def test_combinacao_de_sinais_gera_risco(self):
        agora = datetime.now(timezone.utc)
        cliente = _cliente_base(
            ultimo_login_adm=agora - timedelta(days=20),   # sem_acesso_14_dias (+20)
            percentual_onboarding=60.0,                    # onboarding_nao_concluido (+10)
        )
        tickets = [
            _ticket(tipo="basico", tema="certificado emitido", horas_atras=48),
            _ticket(tipo="basico", tema="emissão de certificado", horas_atras=24),  # repetido (+30)
        ]
        result = calcular_score(cliente, tickets)
        assert result.score >= 51
        assert result.nivel in ("risco", "critico")

    def test_adm_diferente_do_onboarding(self):
        cliente = _cliente_base(
            email_adm_onboarding="antigo@empresa.com",
            email_adm_atual="novo@empresa.com",
        )
        tickets = [_ticket()]
        result = calcular_score(cliente, tickets)
        assert "adm_diferente_onboarding" in result.sinais_identificados
        assert result.score >= 25


# ─── Testes: score crítico ────────────────────────────────────────────────────

class TestScoreCritico:
    def test_todos_os_sinais_resulta_em_critico(self):
        agora = datetime.now(timezone.utc)
        cliente = _cliente_base(
            email_adm_onboarding="antigo@empresa.com",
            email_adm_atual="novo@empresa.com",
            ultimo_login_adm=agora - timedelta(days=20),
            percentual_onboarding=50.0,
            modulos_nunca_usados=["Gestão de Pessoas"],
        )
        tickets = [
            _ticket(tipo="basico", tema="certificado", horas_atras=i*10, frustracao=(i == 1))
            for i in range(1, 8)
        ] + [
            _ticket(tipo="basico", tema="emissão de certificado", horas_atras=80),
        ]
        result = calcular_score(cliente, tickets)
        assert result.score == 100
        assert result.nivel == "critico"
        assert result.prazo_acao == "mesmo dia"

    def test_score_capeado_em_100(self):
        """Mesmo com todos os sinais, o score não pode ultrapassar 100."""
        agora = datetime.now(timezone.utc)
        cliente = _cliente_base(
            email_adm_onboarding="a@empresa.com",
            email_adm_atual="b@empresa.com",
            ultimo_login_adm=agora - timedelta(days=30),
            percentual_onboarding=10.0,
            modulos_nunca_usados=["X", "Y"],
        )
        tickets = [_ticket(tipo="basico", tema="tema X", frustracao=True, horas_atras=i*5)
                   for i in range(1, 15)]
        result = calcular_score(cliente, tickets)
        assert result.score <= 100


# ─── Testes: campos do resultado ─────────────────────────────────────────────

class TestCamposResultado:
    def test_resultado_inclui_tres_ultimos_tickets(self):
        cliente = _cliente_base()
        tickets = [_ticket(horas_atras=i*5, tema=f"tema {i}") for i in range(1, 6)]
        result = calcular_score(cliente, tickets)
        assert len(result.tickets_resumo) <= 3

    def test_resultado_inclui_detalhes_dos_sinais(self):
        agora = datetime.now(timezone.utc)
        cliente = _cliente_base(ultimo_login_adm=agora - timedelta(days=20))
        result = calcular_score(cliente, [_ticket()])
        if "sem_acesso_14_dias" in result.sinais_identificados:
            assert "sem_acesso_14_dias" in result.detalhes_sinais

    def test_nivel_correto_para_cada_faixa(self):
        # Testa mapeamento direto de score → nível
        from src.risk_calculator import _nivel_para_score
        assert _nivel_para_score(0)   == "saudavel"
        assert _nivel_para_score(20)  == "saudavel"
        assert _nivel_para_score(21)  == "atencao"
        assert _nivel_para_score(50)  == "atencao"
        assert _nivel_para_score(51)  == "risco"
        assert _nivel_para_score(70)  == "risco"
        assert _nivel_para_score(71)  == "critico"
        assert _nivel_para_score(100) == "critico"
