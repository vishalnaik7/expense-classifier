"""
Unit tests for the AWS Bedrock vision extraction path (Claude 3.5 Sonnet
v2, falling back to Amazon Nova Lite). Never calls real AWS -
boto3.client is mocked directly.
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


class TestNovaLiteFallback:
    def test_does_not_call_fallback_when_primary_succeeds(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.converse.return_value = _converse_response([
            {'date': '2026-05-05', 'description': 'Txn A', 'amount': 100.0, 'type': 'DEBIT', 'balance': None},
        ])

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

        assert mock_client.converse.call_count == 1
        assert mock_client.converse.call_args.kwargs['modelId'] == bedrock_vision.BEDROCK_MODEL_ID

    def test_falls_back_to_nova_lite_when_primary_model_fails(self, monkeypatch):
        # Simulates the real-world case this fallback exists for: Claude
        # (a third-party model) fails due to the AWS Marketplace
        # INVALID_PAYMENT_INSTRUMENT error, independent of IAM
        # permissions, while Amazon's own Nova Lite keeps working.
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        nova_response = _converse_response([
            {'date': '2026-05-05', 'description': 'Txn via Nova', 'amount': 250.0, 'type': 'CREDIT', 'balance': None},
        ])
        mock_client.converse.side_effect = [
            ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'INVALID_PAYMENT_INSTRUMENT'}}, 'Converse'),
            nova_response,
        ]

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            transactions = bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'Txn via Nova'
        assert mock_client.converse.call_count == 2
        first_model = mock_client.converse.call_args_list[0].kwargs['modelId']
        second_model = mock_client.converse.call_args_list[1].kwargs['modelId']
        assert first_model == bedrock_vision.BEDROCK_MODEL_ID
        assert second_model == bedrock_vision.BEDROCK_FALLBACK_MODEL_ID

    def test_raises_combined_error_when_both_models_fail(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.converse.side_effect = [
            ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'denied'}}, 'Converse'),
            ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'too many requests'}}, 'Converse'),
        ]

        with patch.object(bedrock_vision, '_client', return_value=mock_client):
            with pytest.raises(LLMExtractionError, match='Fallback model also failed'):
                bedrock_vision.extract_transactions_from_images([b'fake-png-bytes'])
