"""
Unit tests for the AWS Bedrock (Amazon Nova Lite) vision extraction
path. Never calls real AWS - boto3.client is mocked directly.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services import bedrock_vision
from services.llm_extractor import LLMExtractionError


def _converse_response(transactions, stop_reason='end_turn'):
    return {
        'output': {'message': {'content': [{'text': json.dumps({'transactions': transactions})}]}},
        'stopReason': stop_reason,
    }


class TestIsConfigured:
    def test_false_without_credentials(self, monkeypatch):
        monkeypatch.delenv('AWS_ACCESS_KEY_ID', raising=False)
        monkeypatch.delenv('AWS_SECRET_ACCESS_KEY', raising=False)
        assert bedrock_vision.is_configured() is False

    def test_true_with_credentials(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        assert bedrock_vision.is_configured() is True


class TestExtractFromImages:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv('AWS_ACCESS_KEY_ID', raising=False)
        monkeypatch.delenv('AWS_SECRET_ACCESS_KEY', raising=False)
        with pytest.raises(LLMExtractionError, match='not configured'):
            bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

    def test_raises_when_no_images_given(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        with pytest.raises(LLMExtractionError, match='No page images'):
            bedrock_vision.extract_transactions_from_images([])

    def test_sends_images_and_parses_response(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        response = _converse_response([
            {'date': '2026-05-05', 'description': 'ACH D- HDFC BANK LTD', 'amount': 11611.0, 'type': 'DEBIT', 'balance': 9525.05},
        ])
        mock_client = MagicMock()
        mock_client.converse.return_value = response

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            transactions = bedrock_vision.extract_transactions_from_images([b'\x89PNG-page-one', b'\x89PNG-page-two'])

        assert len(transactions) == 1
        assert transactions[0]['amount'] == 11611.0
        assert transactions[0]['type'] == 'debit'

        call_kwargs = mock_client.converse.call_args.kwargs
        assert call_kwargs['modelId'] == bedrock_vision.BEDROCK_MODEL_ID
        content = call_kwargs['messages'][0]['content']
        image_blocks = [block for block in content if 'image' in block]
        assert len(image_blocks) == 2
        for block in image_blocks:
            assert block['image']['format'] == 'png'

    def test_raises_when_no_transactions_found(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.return_value = _converse_response([])

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='could not find'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

    def test_raises_on_content_filtered_stop_reason(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.return_value = _converse_response([], stop_reason='content_filtered')

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='declined'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

    def test_wraps_client_errors(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'denied'}}, 'Converse'
        )

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='request failed'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

    def test_raises_on_malformed_json(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': 'not valid json'}]}},
            'stopReason': 'end_turn',
        }

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='malformed JSON'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

    def test_strips_markdown_code_fence_before_parsing(self, monkeypatch):
        # Observed live with Nova Lite: it wraps its JSON reply in a
        # ```json ... ``` fence despite the prompt explicitly saying not
        # to, which broke json.loads outright before this was handled.
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        fenced_json = '```json\n' + json.dumps({'transactions': [
            {'date': '2026-05-05', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        ]}) + '\n```'
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': fenced_json}]}},
            'stopReason': 'end_turn',
        }

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            transactions = bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'Txn A'

    def test_raises_clear_error_on_max_tokens_truncation(self, monkeypatch):
        # Observed live on a real dense HDFC statement: Nova Lite hit its
        # output token limit mid-JSON, which used to surface as an
        # unhelpful generic "malformed JSON" error.
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.return_value = {
            'output': {'message': {'content': [{'text': '{"transactions": [{"date": "2026-05-0'}]}},
            'stopReason': 'max_tokens',
        }

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='cut off before finishing'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])


class TestPageBatching:
    def test_splits_into_batches_and_merges_results(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            _converse_response([{'date': '2026-05-01', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None}]),
            _converse_response([{'date': '2026-05-02', 'description': 'Txn B', 'amount': 200.0, 'type': 'CREDIT', 'balance': None}]),
        ]

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            pages = [f'\x89PNG-page-{i}'.encode() for i in range(3)]
            transactions = bedrock_vision.extract_transactions_from_images(pages)

        assert mock_client.converse.call_count == 2  # batches of MAX_PAGES_PER_REQUEST=2, then 1
        first_batch_images = [b for b in mock_client.converse.call_args_list[0].kwargs['messages'][0]['content'] if 'image' in b]
        second_batch_images = [b for b in mock_client.converse.call_args_list[1].kwargs['messages'][0]['content'] if 'image' in b]
        assert len(first_batch_images) == 2
        assert len(second_batch_images) == 1
        assert {t['description'] for t in transactions} == {'Txn A', 'Txn B'}

    def test_one_failed_batch_does_not_lose_other_batches_results(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            # First batch fails.
            ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'denied'}}, 'Converse'),
            # Second batch succeeds.
            _converse_response([{'date': '2026-05-02', 'description': 'Txn B', 'amount': 200.0, 'type': 'CREDIT', 'balance': None}]),
        ]

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            pages = [f'\x89PNG-page-{i}'.encode() for i in range(3)]
            transactions = bedrock_vision.extract_transactions_from_images(pages)

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'Txn B'
