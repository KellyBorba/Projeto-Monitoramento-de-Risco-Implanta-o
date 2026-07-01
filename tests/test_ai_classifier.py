"""
test_ai_classifier.py — Testes para o classificador de tickets.
Usa mocks para não chamar a API OpenAI nos testes.
"""

from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models import Ticket


def _ticket(assunto="Problema no certificado", descricao="Não consigo emitir o certificado") -> Ticket:
    return Ticket(
        id="T-TEST",
        company_id="EMP-001",
        assunto=assunto,
        descricao=descricao,
        criado_em=datetime.now(timezone.utc),
    )


def _mock_openai_response(tipo="basico", frustracao=False, tema="certificado não emitido"):
    import json
    choice = MagicMock()
    choice.message.content = json.dumps({
        "tipo": tipo,
        "tem_frustracao": frustracao,
        "tema_resumido": tema,
    })
    completion = MagicMock()
    completion.choices = [choice]
    return completion


class TestAiClassifier:
    @patch("src.ai_classifier._get_client")
    def test_classifica_ticket_basico(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            tipo="basico", frustracao=False, tema="certificado não emitido"
        )
        mock_get_client.return_value = mock_client

        # Limpa o cache entre testes
        import src.ai_classifier as mod
        mod._cache.clear()

        from src.ai_classifier import classificar_ticket
        resultado = classificar_ticket(_ticket())
        assert resultado.tipo == "basico"
        assert resultado.tem_frustracao is False
        assert resultado.tema_resumido == "certificado não emitido"

    @patch("src.ai_classifier._get_client")
    def test_detecta_frustracao(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            tipo="recorrente", frustracao=True, tema="erro de login"
        )
        mock_get_client.return_value = mock_client

        import src.ai_classifier as mod
        mod._cache.clear()

        from src.ai_classifier import classificar_ticket
        t = _ticket(assunto="Não funciona MAIS!", descricao="Já reportei isso 3 vezes!")
        resultado = classificar_ticket(t)
        assert resultado.tem_frustracao is True
        assert resultado.tipo == "recorrente"

    @patch("src.ai_classifier._get_client")
    def test_usa_cache_na_segunda_chamada(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        mock_get_client.return_value = mock_client

        import src.ai_classifier as mod
        mod._cache.clear()

        from src.ai_classifier import classificar_ticket
        t = _ticket(assunto="Teste cache")
        classificar_ticket(t)
        classificar_ticket(t)
        # Deve ter sido chamada apenas uma vez (segunda usa cache)
        assert mock_client.chat.completions.create.call_count == 1

    def test_ticket_sem_texto_retorna_intacto(self):
        import src.ai_classifier as mod
        mod._cache.clear()

        from src.ai_classifier import classificar_ticket
        t = Ticket(
            id="T-VAZIO",
            company_id="EMP-001",
            assunto="",
            descricao="",
            criado_em=datetime.now(timezone.utc),
        )
        resultado = classificar_ticket(t)
        assert resultado.tipo is None

    @patch("src.ai_classifier._get_client")
    def test_erro_na_api_retorna_ticket_original(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Timeout")
        mock_get_client.return_value = mock_client

        import src.ai_classifier as mod
        mod._cache.clear()

        from src.ai_classifier import classificar_ticket
        t = _ticket(assunto="Erro de API")
        resultado = classificar_ticket(t)
        assert resultado.tipo is None
        assert resultado.tem_frustracao is None
