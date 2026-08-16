"""
Integration tests for uploading a PDF bank statement through
POST /api/uploads, exercised end to end through the Flask test client -
same endpoint CSV uploads go through, now branching on file extension.
"""
import io
from unittest.mock import patch

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
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


def _build_image_only_pdf(lines):
    """
    A PDF with zero extractable text (whole page is one embedded raster
    image) - stands in for the real-world case where a bank's PDF
    generator draws "text" as vector glyph outlines with no character
    data (e.g. some HDFC statements). Both cases hit page.chars == 0,
    which is what routes the upload to vision-based extraction.
    """
    from PIL import Image, ImageDraw

    img = Image.new('RGB', (600, 200), 'white')
    draw = ImageDraw.Draw(img)
    y = 10
    for line in lines:
        draw.text((10, y), line, fill='black')
        y += 20
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)

    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    c.drawImage(ImageReader(img_buffer), 50, 500, width=500, height=150)
    c.save()
    return pdf_buffer.getvalue()


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


def test_pdf_with_no_extractable_text_goes_straight_to_vision_fallback(client, auth_headers, monkeypatch):
    # A PDF with zero character-level text (e.g. some HDFC statements) has
    # nothing for a text-based AI fallback to read - the endpoint should
    # skip straight to vision-based extraction rather than making a
    # doomed text-based attempt first.
    monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)
    image_only_pdf = _build_image_only_pdf(['Date Narration Withdrawal Deposit', '05/05/26 ACH D 11611.00'])

    fake_transactions = [{
        'date': '2026-05-05',
        'description': 'ACH D- HDFC BANK LTD',
        'amount': 11611.0,
        'type': 'debit',
        'hash': 'fakevisionhash123',
        'raw_amount': 11611.0,
    }]

    with patch.object(main_module.llm_extractor, 'extract_transactions_from_images', return_value=fake_transactions) as mock_vision, \
            patch.object(main_module.llm_extractor, 'extract_transactions') as mock_text:
        response = _upload(client, auth_headers, content=image_only_pdf, filename='hdfc_no_text.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
    mock_vision.assert_called_once()
    mock_text.assert_not_called()  # text-based fallback would have nothing to read, so it must be skipped

    transactions = client.get('/api/transactions', headers=auth_headers).get_json()['data']
    assert any('HDFC BANK' in t['description'] for t in transactions)


def test_pdf_vision_fallback_used_when_text_fallback_also_fails(client, auth_headers, monkeypatch):
    # A PDF that DOES have some text, but where the text-based AI attempt
    # still can't find a transaction table, should still get a vision
    # attempt as a last resort before giving up entirely.
    monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([['Foo', 'Bar'], ['1', '2']], style=_GRID_STYLE)])

    fake_transactions = [{
        'date': '2026-06-01',
        'description': 'Recovered via vision',
        'amount': 100.0,
        'type': 'debit',
        'hash': 'fakevisionhash456',
        'raw_amount': 100.0,
    }]

    with patch.object(main_module.llm_extractor, 'extract_transactions', side_effect=main_module.LLMExtractionError('AI could not find a transaction table in this file')), \
            patch.object(main_module.llm_extractor, 'extract_transactions_from_images', return_value=fake_transactions) as mock_vision:
        response = _upload(client, auth_headers, content=buffer.getvalue(), filename='unreadable.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
    mock_vision.assert_called_once()
