"""
Integration tests for uploading a PDF bank statement through
POST /api/uploads, exercised end to end through the Flask test client -
same endpoint CSV uploads go through, now branching on file extension.
"""
import io
from unittest.mock import patch

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

import main as main_module

TXN_HEADER = ['Transaction Date', 'Particulars', 'Debit', 'Credit', 'Balance']
_GRID_STYLE = TableStyle([
    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ('FONTSIZE', (0, 0), (-1, -1), 8),
])


def _build_statement_pdf(rows):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([TXN_HEADER] + rows, style=_GRID_STYLE)])
    return buffer.getvalue()


SAMPLE_PDF = _build_statement_pdf([
    ['', 'Opening Balance', '', '', '231789.00'],
    ['01-Jun-2026', 'UPI/DR/063110630325/CHALO/HDFC/Pay', '75.00', '', '231714.00'],
    ['08-Jun-2026', 'NEFT/Salary Credit', '', '72000.00', '303714.00'],
    ['11-Jul-2026', 'UPI/DR/588566388572/IRCTC Ra/YESB/Payment for booking', '442.70', '', '312968.21'],
])


def _upload(client, headers, content=SAMPLE_PDF, filename='statement.pdf'):
    return client.post(
        '/api/uploads',
        data={'file': (io.BytesIO(content), filename)},
        headers=headers,
        content_type='multipart/form-data'
    )


def test_pdf_upload_parses_and_stores_transactions(client, auth_headers):
    response = _upload(client, auth_headers)
    assert response.status_code == 201
    body = response.get_json()
    assert body['success'] is True
    # 4 rows in the PDF; the Opening Balance summary row has no date and is dropped
    assert body['data']['inserted'] == 3
    assert body['data']['used_ai_fallback'] is False

    transactions = client.get('/api/transactions', headers=auth_headers).get_json()['data']
    descriptions = ' '.join(t['description'] for t in transactions)
    assert 'IRCTC' in descriptions


def test_pdf_upload_categorizes_irctc_transaction_as_transport(client, auth_headers):
    _upload(client, auth_headers)
    transactions = client.get('/api/transactions', headers=auth_headers).get_json()['data']
    irctc_txn = next(t for t in transactions if 'IRCTC' in t['description'])
    assert irctc_txn['category']['name'] == 'Transport'


def test_pdf_uploads_are_isolated_per_user(client, auth_headers):
    _upload(client, auth_headers)

    client.post('/api/auth/signup', json={'username': 'pdfuser2', 'email': 'pdfuser2@example.com', 'password': 'Passw0rd!'})
    token_b = client.post('/api/auth/login', json={'email': 'pdfuser2@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

    transactions_b = client.get('/api/transactions', headers={'Authorization': f'Bearer {token_b}'}).get_json()['data']
    assert transactions_b == []


def test_non_pdf_non_csv_extension_rejected(client, auth_headers):
    response = _upload(client, auth_headers, content=b'hello', filename='statement.docx')
    assert response.status_code == 400
    assert 'csv' in response.get_json()['error'].lower()


def test_pdf_with_no_transaction_table_and_no_ai_configured_returns_original_error(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: False)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([['Foo', 'Bar'], ['1', '2']], style=_GRID_STYLE)])

    response = _upload(client, auth_headers, content=buffer.getvalue(), filename='unreadable.pdf')
    assert response.status_code == 422
    assert 'ai_fallback_error' not in response.get_json()


def test_pdf_ai_fallback_used_when_deterministic_parser_fails(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([['Foo', 'Bar'], ['1', '2']], style=_GRID_STYLE)])

    fake_transactions = [{
        'date': '2026-06-01',
        'description': 'AI extracted from PDF',
        'amount': 250.0,
        'type': 'debit',
        'hash': 'fakepdfhash123',
        'raw_amount': 250.0,
    }]

    with patch.object(main_module.llm_extractor, 'extract_transactions', return_value=fake_transactions):
        response = _upload(client, auth_headers, content=buffer.getvalue(), filename='unreadable.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
