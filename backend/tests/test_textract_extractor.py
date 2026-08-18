"""
Unit tests for the AWS Textract-based vision extraction path. Never
calls real AWS - boto3.client is mocked directly.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import textract_extractor
from services.pdf_parser import PDFParsingError


def _word(text, block_id):
    return {'Id': block_id, 'BlockType': 'WORD', 'Text': text}


def _cell(row, col, child_ids, cell_id):
    return {
        'Id': cell_id,
        'BlockType': 'CELL',
        'RowIndex': row,
        'ColumnIndex': col,
        'Relationships': [{'Type': 'CHILD', 'Ids': child_ids}],
    }


def _table(cell_ids, table_id='table-1'):
    return {
        'Id': table_id,
        'BlockType': 'TABLE',
        'Relationships': [{'Type': 'CHILD', 'Ids': cell_ids}],
    }


def _transaction_table_response():
    """A minimal 2-row (header + 1 data row) transaction table Textract response."""
    words = [
        _word('Date', 'w1'), _word('Particulars', 'w2'), _word('Debit', 'w3'), _word('Credit', 'w4'),
        _word('01/06/26', 'w5'), _word('UPI/Amazon/Payment', 'w6'), _word('1500.00', 'w7'), _word('', 'w8'),
    ]
    cells = [
        _cell(1, 1, ['w1'], 'c1'), _cell(1, 2, ['w2'], 'c2'), _cell(1, 3, ['w3'], 'c3'), _cell(1, 4, ['w4'], 'c4'),
        _cell(2, 1, ['w5'], 'c5'), _cell(2, 2, ['w6'], 'c6'), _cell(2, 3, ['w7'], 'c7'), _cell(2, 4, [], 'c8'),
    ]
    table = _table(['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8'])
    return {'Blocks': [table] + cells + words}


class TestIsConfigured:
    def test_false_without_credentials(self, monkeypatch):
        monkeypatch.delenv('AWS_ACCESS_KEY_ID', raising=False)
        monkeypatch.delenv('AWS_SECRET_ACCESS_KEY', raising=False)
        assert textract_extractor.is_configured() is False

    def test_true_with_credentials(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        assert textract_extractor.is_configured() is True


class TestExtractFromImages:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv('AWS_ACCESS_KEY_ID', raising=False)
        monkeypatch.delenv('AWS_SECRET_ACCESS_KEY', raising=False)
        with pytest.raises(PDFParsingError, match='not configured'):
            textract_extractor.extract_transactions_from_images([b'fake-png-bytes'])

    def test_raises_when_no_images_given(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        with pytest.raises(PDFParsingError, match='No page images'):
            textract_extractor.extract_transactions_from_images([])

    def test_extracts_transaction_table(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = _transaction_table_response()

        with patch.object(textract_extractor, '_client', return_value=mock_client):
            transactions = textract_extractor.extract_transactions_from_images([b'fake-png-bytes'])

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'UPI/Amazon/Payment'
        assert transactions[0]['amount'] == 1500.0
        assert transactions[0]['type'] == 'debit'

    def test_ignores_non_transaction_tables(self, monkeypatch):
        # A bank statement PDF's account-summary/metadata table (branch,
        # address, etc.) gets detected by Textract just as readily as
        # the real transaction table - only a table whose header row
        # looks like a transaction header should be kept.
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')

        metadata_words = [_word('Branch:', 'm1'), _word('Sawantwadi', 'm2')]
        metadata_cells = [_cell(1, 1, ['m1'], 'mc1'), _cell(1, 2, ['m2'], 'mc2')]
        metadata_table = _table(['mc1', 'mc2'], table_id='metadata-table')

        response = _transaction_table_response()
        response['Blocks'] = [metadata_table] + metadata_cells + metadata_words + response['Blocks']

        mock_client = MagicMock()
        mock_client.analyze_document.return_value = response

        with patch.object(textract_extractor, '_client', return_value=mock_client):
            transactions = textract_extractor.extract_transactions_from_images([b'fake-png-bytes'])

        assert len(transactions) == 1
        assert transactions[0]['description'] == 'UPI/Amazon/Payment'

    def test_merges_matching_tables_across_pages(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')

        page_2_words = [
            _word('Date', 'w1'), _word('Particulars', 'w2'), _word('Debit', 'w3'), _word('Credit', 'w4'),
            _word('02/06/26', 'w5'), _word('Salary Credit', 'w6'), _word('', 'w7'), _word('50000.00', 'w8'),
        ]
        page_2_cells = [
            _cell(1, 1, ['w1'], 'c1'), _cell(1, 2, ['w2'], 'c2'), _cell(1, 3, ['w3'], 'c3'), _cell(1, 4, ['w4'], 'c4'),
            _cell(2, 1, ['w5'], 'c5'), _cell(2, 2, ['w6'], 'c6'), _cell(2, 3, [], 'c7'), _cell(2, 4, ['w8'], 'c8'),
        ]
        page_2_table = _table(['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8'])
        page_2_response = {'Blocks': [page_2_table] + page_2_cells + page_2_words}

        mock_client = MagicMock()
        mock_client.analyze_document.side_effect = [_transaction_table_response(), page_2_response]

        with patch.object(textract_extractor, '_client', return_value=mock_client):
            transactions = textract_extractor.extract_transactions_from_images([b'page-1-bytes', b'page-2-bytes'])

        assert mock_client.analyze_document.call_count == 2
        assert {t['description'] for t in transactions} == {'UPI/Amazon/Payment', 'Salary Credit'}

    def test_raises_when_no_transaction_table_found(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = {'Blocks': []}

        with patch.object(textract_extractor, '_client', return_value=mock_client):
            with pytest.raises(PDFParsingError, match='could not find'):
                textract_extractor.extract_transactions_from_images([b'fake-png-bytes'])

    def test_wraps_client_errors(self, monkeypatch):
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'AKIATEST')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.analyze_document.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'denied'}}, 'AnalyzeDocument'
        )

        with patch.object(textract_extractor, '_client', return_value=mock_client):
            with pytest.raises(PDFParsingError, match='request failed'):
                textract_extractor.extract_transactions_from_images([b'fake-png-bytes'])
