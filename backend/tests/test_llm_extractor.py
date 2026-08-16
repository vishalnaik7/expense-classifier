"""
Unit tests for the LLM-based CSV extraction fallback. Never calls a real
model - is_configured() and get_client() on services.ai_client are mocked
directly (the provider env-var mechanics themselves are covered by
test_ai_client.py).
"""
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from services import ai_client
from services.llm_extractor import LLMExtractionError, extract_transactions, is_configured


def test_not_configured_delegates_to_ai_client(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: False)
    assert is_configured() is False


def test_configured_delegates_to_ai_client(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    assert is_configured() is True


def test_extract_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: False)
    with pytest.raises(LLMExtractionError, match='not configured'):
        extract_transactions(b'anything')


def _make_response(transactions, finish_reason='stop'):
    message = MagicMock()
    message.content = json.dumps({'transactions': transactions})
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    return response


def test_extract_normalizes_llm_output(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    mock_response = _make_response([
        {'date': '2026-06-01', 'description': 'UPI/Amazon/123456/Payment', 'amount': 1500.0, 'type': 'DEBIT', 'balance': 24500.5},
        {'date': '2026-06-02', 'description': 'Salary', 'amount': 50000.0, 'type': 'CREDIT', 'balance': 74500.5},
    ])

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        transactions = extract_transactions(b'some messy csv text')

    assert len(transactions) == 2
    assert transactions[0]['date'] == '2026-06-01'
    assert transactions[0]['type'] == 'debit'
    assert transactions[0]['amount'] == 1500.0
    assert transactions[1]['type'] == 'credit'
    # hash formula must match CSVParser's so dedup stays consistent across paths
    expected_hash = hashlib.sha256(b'2026-06-01|UPI/Amazon/123456/Payment|1500.0').hexdigest()
    assert transactions[0]['hash'] == expected_hash


def test_extract_requests_json_mode(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([
        {'date': '2026-06-01', 'description': 'x', 'amount': 1.0, 'type': 'DEBIT', 'balance': None},
    ])

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_create = mock_get_client.return_value.chat.completions.create
        mock_create.return_value = mock_response
        extract_transactions(b'some csv text')

    assert mock_create.call_args.kwargs['response_format'] == {'type': 'json_object'}


def test_extract_raises_on_content_filter(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([], finish_reason='content_filter')

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(LLMExtractionError, match='declined'):
            extract_transactions(b'some csv text')


def test_extract_raises_when_no_transactions_found(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([])

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(LLMExtractionError, match='could not find'):
            extract_transactions(b'some csv text')


def test_extract_skips_unusable_rows(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([
        {'date': 'not-a-date', 'description': 'Bad row', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        {'date': '2026-06-01', 'description': 'Valid row', 'amount': 200.0, 'type': 'DEBIT', 'balance': None},
    ])

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        transactions = extract_transactions(b'some csv text')

    assert len(transactions) == 1
    assert transactions[0]['description'] == 'Valid row'


def test_extract_wraps_connection_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = RuntimeError('network down')
        with pytest.raises(LLMExtractionError, match='request failed'):
            extract_transactions(b'some csv text')


def test_extract_wraps_provider_config_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client', side_effect=ai_client.AIProviderError('no GROQ_API_KEY set')):
        with pytest.raises(LLMExtractionError, match='GROQ_API_KEY'):
            extract_transactions(b'some csv text')
