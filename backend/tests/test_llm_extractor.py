"""
Unit tests for the LLM-based CSV extraction fallback. Never calls a real
model - is_configured_for()/get_client_for() on services.ai_client are
mocked directly (the provider env-var mechanics themselves are covered by
test_ai_client.py).
"""
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from services import ai_client
from services.llm_extractor import LLMExtractionError, extract_transactions, extract_transactions_from_images, is_configured


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

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
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

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
        mock_create = mock_get_client.return_value.chat.completions.create
        mock_create.return_value = mock_response
        extract_transactions(b'some csv text')

    assert mock_create.call_args.kwargs['response_format'] == {'type': 'json_object'}


def test_extract_raises_on_content_filter(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([], finish_reason='content_filter')

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(LLMExtractionError, match='declined'):
            extract_transactions(b'some csv text')


def test_extract_raises_when_no_transactions_found(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([])

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(LLMExtractionError, match='could not find'):
            extract_transactions(b'some csv text')


def test_extract_skips_unusable_rows(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response([
        {'date': 'not-a-date', 'description': 'Bad row', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        {'date': '2026-06-01', 'description': 'Valid row', 'amount': 200.0, 'type': 'DEBIT', 'balance': None},
    ])

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        transactions = extract_transactions(b'some csv text')

    assert len(transactions) == 1
    assert transactions[0]['description'] == 'Valid row'


def test_extract_wraps_connection_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client_for') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = RuntimeError('network down')
        with pytest.raises(LLMExtractionError, match='request failed'):
            extract_transactions(b'some csv text')


def test_extract_wraps_provider_config_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client_for', side_effect=ai_client.AIProviderError('no GROQ_API_KEY set')):
        with pytest.raises(LLMExtractionError, match='GROQ_API_KEY'):
            extract_transactions(b'some csv text')


class TestExtractFromImages:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: False)
        with pytest.raises(LLMExtractionError, match='not configured'):
            extract_transactions_from_images([b'fake-png-bytes'])

    def test_raises_when_no_images_given(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)
        with pytest.raises(LLMExtractionError, match='No page images'):
            extract_transactions_from_images([])

    def test_uses_vision_model_and_sends_images_as_data_uris(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)
        mock_response = _make_response([
            {'date': '2026-05-05', 'description': 'ACH D- HDFC BANK LTD', 'amount': 11611.0, 'type': 'DEBIT', 'balance': 9525.05},
        ])

        with patch.object(ai_client, 'get_client_for') as mock_get_client, \
                patch.object(ai_client, 'get_vision_model_for', return_value='llama3.2-vision'):
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            transactions = extract_transactions_from_images([b'\x89PNG-page-one', b'\x89PNG-page-two'])

        assert len(transactions) == 1
        assert transactions[0]['amount'] == 11611.0
        assert transactions[0]['type'] == 'debit'

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs['model'] == 'llama3.2-vision'
        user_content = call_kwargs['messages'][1]['content']
        assert user_content[0]['type'] == 'text'
        image_blocks = [block for block in user_content if block['type'] == 'image_url']
        assert len(image_blocks) == 2  # one per page image supplied
        for block in image_blocks:
            assert block['image_url']['url'].startswith('data:image/png;base64,')

    def test_uses_explicit_provider_when_given(self, monkeypatch):
        # main.py's vision fallback chain calls this with an explicit
        # provider (e.g. 'gemini') regardless of the deployment's active
        # AI_PROVIDER - both the configured-check and the client/model
        # lookups must honor that explicit provider, not the global one.
        monkeypatch.setattr(ai_client, 'AI_PROVIDER', 'groq')
        seen_providers = []

        def fake_is_configured_for(provider):
            seen_providers.append(provider)
            return True

        mock_response = _make_response([
            {'date': '2026-05-05', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        ])

        with patch.object(ai_client, 'is_configured_for', side_effect=fake_is_configured_for), \
                patch.object(ai_client, 'get_client_for') as mock_get_client, \
                patch.object(ai_client, 'get_vision_model_for', return_value='gemini-3.7-flash') as mock_get_vision_model:
            mock_get_client.return_value.chat.completions.create.return_value = mock_response
            extract_transactions_from_images([b'fake-png-bytes'], provider='gemini')

        assert seen_providers == ['gemini']
        mock_get_client.assert_called_once_with('gemini')
        mock_get_vision_model.assert_called_once_with('gemini')

    def test_batches_more_than_max_images_per_request(self, monkeypatch):
        # Vision models commonly cap images per request (e.g. Groq's
        # qwen/qwen3.6-27b allows at most 3) - five page images should
        # split into two requests (3 then 2) with results merged.
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)
        responses = [
            _make_response([
                {'date': '2026-05-01', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
            ]),
            _make_response([
                {'date': '2026-05-02', 'description': 'Txn B', 'amount': 200.0, 'type': 'CREDIT', 'balance': None},
            ]),
        ]

        with patch.object(ai_client, 'get_client_for') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.side_effect = responses
            pages = [f'\x89PNG-page-{i}'.encode() for i in range(5)]
            transactions = extract_transactions_from_images(pages)

        assert mock_create.call_count == 2
        first_call_images = [b for b in mock_create.call_args_list[0].kwargs['messages'][1]['content'] if b['type'] == 'image_url']
        second_call_images = [b for b in mock_create.call_args_list[1].kwargs['messages'][1]['content'] if b['type'] == 'image_url']
        assert len(first_call_images) == 3
        assert len(second_call_images) == 2
        assert {t['description'] for t in transactions} == {'Txn A', 'Txn B'}

    def test_partial_batch_failure_still_returns_successful_transactions(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)
        ok_response = _make_response([
            {'date': '2026-05-01', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        ])

        with patch.object(ai_client, 'get_client_for') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.side_effect = [ok_response, RuntimeError('network down')]
            pages = [f'\x89PNG-page-{i}'.encode() for i in range(5)]
            transactions = extract_transactions_from_images(pages)

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'Txn A'

    def test_raises_when_no_transactions_found(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)
        mock_response = _make_response([])

        with patch.object(ai_client, 'get_client_for') as mock_get_client:
            mock_get_client.return_value.chat.completions.create.return_value = mock_response
            with pytest.raises(LLMExtractionError, match='could not find'):
                extract_transactions_from_images([b'fake-png-bytes'])

    def test_wraps_connection_errors(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured_for', lambda provider: True)

        with patch.object(ai_client, 'get_client_for') as mock_get_client:
            mock_get_client.return_value.chat.completions.create.side_effect = RuntimeError('network down')
            with pytest.raises(LLMExtractionError, match='request failed'):
                extract_transactions_from_images([b'fake-png-bytes'])
