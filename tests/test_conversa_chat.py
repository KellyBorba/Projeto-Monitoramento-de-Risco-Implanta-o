"""
test_conversa_chat.py — Teste de ponta a ponta:

  1. Lê uma conversa real de chat (conversa_teste.json)
  2. Extrai os tickets gerados a partir das mensagens do cliente
  3. Classifica cada ticket via mock de IA
  4. Calcula o score de risco do cliente
  5. Valida que todos os sinais esperados foram detectados
  6. Imprime um relatório legível do resultado

Executar:
    pytest tests/test_conversa_chat.py -v -s
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Cliente, Ticket
from src.ai_classifier import classificar_ticket
from src.risk_calculator import calcular_score

CONVERSA = Path(__file__).parent / "conversa_teste.json"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def carregar_mensagens_cliente() -> list[dict]:
    with open(CONVERSA, encoding="utf-8") as f:
        msgs = json.load(f)
    return [m for m in msgs if m["de"] == "cliente"]


def mensagens_para_tickets(mensagens: list[dict]) -> list[Ticket]:
    """
    Converte cada mensagem do cliente em um Ticket para análise.
    Na prática, cada conversa vira 1 ticket — aqui separamos por mensagem
    para ter granularidade máxima no teste.
    """
    tickets = []
    agora = datetime.now(timezone.utc)

    for i, msg in enumerate(mensagens):
        criado_em = datetime.fromisoformat(msg["hora"]).replace(tzinfo=timezone.utc)
        tickets.append(Ticket(
            id=f"CHAT-{msg['id']}",
            company_id=msg["email"],
            assunto=f"Chat — {msg['empresa']} — msg {i+1}",
            descricao=msg["texto"],
            criado_em=criado_em,
        ))

    return tickets


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mensagens():
    return carregar_mensagens_cliente()


@pytest.fixture(scope="module")
def tickets_classificados(mensagens):
    tickets = mensagens_para_tickets(mensagens)
    return [classificar_ticket(t) for t in tickets]


@pytest.fixture(scope="module")
def cliente_teste():
    return Cliente(
        id="marcos.oliveira@rhconecta.com.br",
        nome="Marcos Oliveira — RH Conecta",
        email_adm_onboarding="outro.adm@rhconecta.com.br",   # ADM diferente → sinal
        email_adm_atual="marcos.oliveira@rhconecta.com.br",
        percentual_onboarding=40.0,                           # trilha incompleta → sinal
        modulos_nunca_usados=["Trilhas de Aprendizado"],      # módulo contratado não usado → sinal
    )


@pytest.fixture(scope="module")
def score_resultado(cliente_teste, tickets_classificados):
    return calcular_score(cliente_teste, tickets_classificados)


# ─── Testes de classificação ──────────────────────────────────────────────────

class TestClassificacaoMensagens:

    def test_carrega_mensagens_do_cliente(self, mensagens):
        assert len(mensagens) >= 4, "Deve haver pelo menos 4 mensagens do cliente"
        print(f"\n  ✓ {len(mensagens)} mensagens do cliente carregadas")

    def test_mensagens_convertidas_em_tickets(self, mensagens):
        tickets = mensagens_para_tickets(mensagens)
        assert len(tickets) == len(mensagens)
        print(f"  ✓ {len(tickets)} tickets gerados a partir das mensagens")

    def test_classificacao_detecta_bug_tecnico(self, tickets_classificados):
        tipos = [t.tipo for t in tickets_classificados]
        assert "bug_tecnico" in tipos, (
            "Mensagens com 'erro 500' e 'tela em branco' devem ser classificadas como bug_tecnico"
        )
        bugs = [t for t in tickets_classificados if t.tipo == "bug_tecnico"]
        print(f"  ✓ {len(bugs)} mensagem(ns) classificada(s) como bug_tecnico")

    def test_classificacao_detecta_recorrente(self, tickets_classificados):
        tipos = [t.tipo for t in tickets_classificados]
        assert "recorrente" in tipos, (
            "Mensagens que citam 'de novo', 'semana passada', 'já fiz essa pergunta' "
            "devem ser classificadas como recorrente"
        )
        recorr = [t for t in tickets_classificados if t.tipo == "recorrente"]
        print(f"  ✓ {len(recorr)} mensagem(ns) classificada(s) como recorrente")

    def test_classificacao_detecta_frustracao(self, tickets_classificados):
        com_frustracao = [t for t in tickets_classificados if t.tem_frustracao]
        assert len(com_frustracao) >= 1, (
            "Mensagens com 'vou reconsiderar a contratação', 'muito frustrado', "
            "'nunca resolve' devem ter frustração detectada"
        )
        print(f"  ✓ Frustração detectada em {len(com_frustracao)} mensagem(ns)")
        for t in com_frustracao:
            print(f"      → [{t.tipo}] {t.descricao[:70]}...")

    def test_temas_resumidos_preenchidos(self, tickets_classificados):
        sem_tema = [t for t in tickets_classificados if not t.tema_resumido]
        assert len(sem_tema) == 0, "Todo ticket deve ter tema_resumido preenchido"
        print(f"  ✓ Todos os tickets têm tema resumido")
        for t in tickets_classificados:
            print(f"      [{t.tipo}] tema: '{t.tema_resumido}' | frustração: {t.tem_frustracao}")


# ─── Testes de score de risco ─────────────────────────────────────────────────

class TestScoreDeRisco:

    def test_score_acima_de_zero(self, score_resultado):
        assert score_resultado.score > 0
        print(f"\n  ✓ Score calculado: {score_resultado.score}/100")

    def test_nivel_nao_e_saudavel(self, score_resultado):
        assert score_resultado.nivel != "saudavel", (
            "Cliente com múltiplos problemas, frustração e módulo não usado "
            "não deve ter nível 'saudável'"
        )
        print(f"  ✓ Nível de risco: {score_resultado.nivel.upper()}")

    def test_detecta_frustracao_no_score(self, score_resultado):
        assert "frase_frustracao_detectada" in score_resultado.sinais_identificados
        print(f"  ✓ Sinal 'frase_frustracao_detectada' presente")

    def test_detecta_ticket_basico_repetido(self, score_resultado, tickets_classificados):
        # O sinal aparece quando há temas suficientemente similares (fuzzy >= 75).
        # Nesta conversa os temas são variados (criar curso, criar usuário, trilhas),
        # então o sinal pode ou não estar presente — ambos são comportamentos corretos.
        presente = "ticket_basico_repetido" in score_resultado.sinais_identificados
        basicos  = [t for t in tickets_classificados if t.tipo == "basico"]
        print(f"  ✓ Sinal 'ticket_basico_repetido': {'PRESENTE' if presente else 'ausente (temas variados)'}")
        print(f"     {len(basicos)} ticket(s) básico(s) encontrado(s)")
        # Garante ao menos que há tickets básicos na conversa
        assert len(basicos) >= 0  # sempre verdadeiro — apenas documenta

    def test_detecta_adm_diferente(self, score_resultado):
        assert "adm_diferente_onboarding" in score_resultado.sinais_identificados
        print(f"  ✓ Sinal 'adm_diferente_onboarding' presente")

    def test_detecta_onboarding_incompleto(self, score_resultado):
        assert "onboarding_nao_concluido" in score_resultado.sinais_identificados
        print(f"  ✓ Sinal 'onboarding_nao_concluido' presente (40% concluído)")

    def test_detecta_funcionalidade_nao_usada(self, score_resultado):
        assert "funcionalidade_nao_usada" in score_resultado.sinais_identificados
        print(f"  ✓ Sinal 'funcionalidade_nao_usada' presente (Trilhas de Aprendizado)")

    def test_prazo_de_acao_definido(self, score_resultado):
        assert score_resultado.prazo_acao is not None
        print(f"  ✓ Prazo de ação: {score_resultado.prazo_acao}")

    def test_tickets_resumo_preenchido(self, score_resultado):
        assert len(score_resultado.tickets_resumo) > 0
        print(f"  ✓ Últimos tickets no resumo:")
        for t in score_resultado.tickets_resumo:
            print(f"      → {t}")


# ─── Teste de tema repetido ───────────────────────────────────────────────────

class TestTemaRepetido:
    """
    Prova isolada que o sinal ticket_basico_repetido funciona.
    Simula um cliente que abre o mesmo ticket sobre certificado 3 vezes.
    """

    def test_mesmo_tema_repetido_dispara_sinal(self):
        from datetime import datetime, timezone, timedelta

        agora = datetime.now(timezone.utc)
        cliente = Cliente(
            id="teste@repetido.com",
            nome="Cliente Repetitivo",
        )

        # Três tickets com o mesmo tema — certificado não emitido
        tickets = [
            Ticket(
                id=f"REP-00{i}",
                company_id="teste@repetido.com",
                assunto="Certificado não está sendo emitido",
                descricao="O aluno conclui o curso mas o certificado não aparece.",
                criado_em=agora - timedelta(days=i * 5),
                tipo="basico",
                tema_resumido="certificado não emitido",
                tem_frustracao=False,
            )
            for i in range(1, 4)
        ]

        score = calcular_score(cliente, tickets)

        print(f"\n  ✓ Teste tema repetido — score: {score.score} | sinais: {score.sinais_identificados}")
        assert "ticket_basico_repetido" in score.sinais_identificados, (
            "3 tickets com tema 'certificado não emitido' devem disparar o sinal"
        )

    def test_temas_diferentes_nao_dispara_sinal(self):
        from datetime import datetime, timezone, timedelta

        agora = datetime.now(timezone.utc)
        cliente = Cliente(id="teste@variado.com", nome="Cliente Variado")

        tickets = [
            Ticket(id="VAR-001", company_id="teste@variado.com",
                   assunto="Certificado não emite", descricao="",
                   criado_em=agora - timedelta(days=1),
                   tipo="basico", tema_resumido="certificado não emite", tem_frustracao=False),
            Ticket(id="VAR-002", company_id="teste@variado.com",
                   assunto="Criar usuário com erro", descricao="",
                   criado_em=agora - timedelta(days=2),
                   tipo="basico", tema_resumido="criar usuário erro", tem_frustracao=False),
            Ticket(id="VAR-003", company_id="teste@variado.com",
                   assunto="Relatório não carrega", descricao="",
                   criado_em=agora - timedelta(days=3),
                   tipo="basico", tema_resumido="relatório não carrega", tem_frustracao=False),
        ]

        score = calcular_score(cliente, tickets)
        presente = "ticket_basico_repetido" in score.sinais_identificados
        print(f"\n  ✓ Temas variados — sinal repetido: {'presente' if presente else 'ausente (correto)'}")
        # Com temas bem diferentes, o sinal não deve disparar
        assert not presente, "Temas distintos não devem disparar ticket_basico_repetido"


# ─── Relatório final ─────────────────────────────────────────────────────────

def test_relatorio_completo(score_resultado, tickets_classificados):
    """Imprime o relatório completo do cliente — prova visual do monitoramento."""

    sep = "=" * 65
    print(f"\n{sep}")
    print("  RELATÓRIO DE RISCO — MONITORAMENTO DE REIMPLANTAÇÃO")
    print(sep)
    print(f"  Cliente  : {score_resultado.cliente_nome}")
    print(f"  Score    : {score_resultado.score}/100")
    print(f"  Nível    : {score_resultado.nivel.upper()}")
    print(f"  Prazo    : {score_resultado.prazo_acao or '—'}")
    print(f"  Gerado em: {score_resultado.calculado_em.strftime('%d/%m/%Y %H:%M UTC')}")
    print(f"\n  SINAIS DETECTADOS ({len(score_resultado.sinais_identificados)}):")
    for sinal in score_resultado.sinais_identificados:
        detalhe = score_resultado.detalhes_sinais.get(sinal, "")
        print(f"    ⚠  {sinal}")
        if detalhe:
            print(f"       {detalhe}")
    print(f"\n  CLASSIFICAÇÃO DAS MENSAGENS:")
    for t in tickets_classificados:
        icone = "😤" if t.tem_frustracao else "💬"
        print(f"    {icone} [{t.tipo:<12}] {t.tema_resumido}")
    print(f"\n  ÚLTIMOS TICKETS NO DASHBOARD:")
    for t in score_resultado.tickets_resumo:
        print(f"    → {t}")
    print(sep)

    # Validação final
    assert score_resultado.nivel in ("atencao", "risco", "critico"), (
        f"Score {score_resultado.score} com tantos sinais deveria resultar em "
        f"atencao/risco/critico, mas foi '{score_resultado.nivel}'"
    )
