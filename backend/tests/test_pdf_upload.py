"""
Integration tests for uploading a PDF bank statement through
POST /api/uploads, exercised end to end through the Flask test client -
same endpoint CSV uploads go through, now branching on file extension.
"""
import io
from unittest.mock import patch

import pytest

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
    monkeypatch.setattr(main_module.bedrock_vision, 'is_configured', lambda: True)
    image_only_pdf = _build_image_only_pdf(['Date Narration Withdrawal Deposit', '05/05/26 ACH D 11611.00'])

    fake_transactions = [{
        'date': '2026-05-05',
        'description': 'ACH D- HDFC BANK LTD',
        'amount': 11611.0,
        'type': 'debit',
        'hash': 'fakevisionhash123',
        'raw_amount': 11611.0,
    }]

    with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', return_value=(fake_transactions, False)) as mock_vision, \
            patch.object(main_module.llm_extractor, 'extract_transactions') as mock_text:
        response = _upload(client, auth_headers, content=image_only_pdf, filename='hdfc_no_text.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
    assert body['data']['used_fallback_model'] is False
    mock_vision.assert_called_once()
    mock_text.assert_not_called()  # text-based fallback would have nothing to read, so it must be skipped

    transactions = client.get('/api/transactions', headers=auth_headers).get_json()['data']
    assert any('HDFC BANK' in t['description'] for t in transactions)


def test_pdf_vision_fallback_used_when_text_fallback_also_fails(client, auth_headers, monkeypatch):
    # A PDF that DOES have some text, but where the text-based AI attempt
    # still can't find a transaction table, should still get a vision
    # attempt as a last resort before giving up entirely.
    monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)
    monkeypatch.setattr(main_module.bedrock_vision, 'is_configured', lambda: True)
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
            patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', return_value=(fake_transactions, False)) as mock_vision:
        response = _upload(client, auth_headers, content=buffer.getvalue(), filename='unreadable.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
    mock_vision.assert_called_once()


def test_upload_warns_when_nova_lite_fallback_model_was_used(client, auth_headers, monkeypatch):
    # When bedrock_vision reports it had to fall back to Nova Lite
    # (Claude failed), the upload should surface that as a lower-
    # confidence warning rather than treating it like an ordinary
    # AI-assisted parse.
    monkeypatch.setattr(main_module.bedrock_vision, 'is_configured', lambda: True)
    image_only_pdf = _build_image_only_pdf(['Date Narration Withdrawal Deposit', '05/05/26 ACH D 11611.00'])

    fake_transactions = [{
        'date': '2026-05-05',
        'description': 'ACH D- HDFC BANK LTD',
        'amount': 11611.0,
        'type': 'debit',
        'hash': 'fakevisionhash789',
        'raw_amount': 11611.0,
    }]

    with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', return_value=(fake_transactions, True)):
        response = _upload(client, auth_headers, content=image_only_pdf, filename='hdfc_no_text.pdf')

    assert response.status_code == 201
    body = response.get_json()
    assert body['data']['used_ai_fallback'] is True
    assert body['data']['used_fallback_model'] is True
    assert 'Nova Lite' in body['data']['upload']['error_message']
    assert 'double-check' in body['data']['upload']['error_message']


class TestVisionFallbackChain:
    """
    Unit tests for _vision_extract_with_fallbacks() and
    vision_extraction_available() directly - the chain that tries AWS
    Bedrock (Claude, then Nova Lite) first, then Gemini and Mistral via
    ai_client, used by both branches of _ai_fallback_parse().
    """

    def test_uses_bedrock_result_when_it_succeeds(self, monkeypatch):
        with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', return_value=([{'d': 1}], False)) as mock_bedrock, \
                patch.object(main_module.llm_extractor, 'extract_transactions_from_images') as mock_llm_extractor:
            transactions, used_fallback_model = main_module._vision_extract_with_fallbacks([b'page'])

        assert transactions == [{'d': 1}]
        assert used_fallback_model is False
        mock_bedrock.assert_called_once()
        mock_llm_extractor.assert_not_called()

    def test_falls_back_to_gemini_when_bedrock_fails(self, monkeypatch):
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: provider == 'gemini')

        with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', side_effect=main_module.LLMExtractionError('bedrock down')), \
                patch.object(main_module.llm_extractor, 'extract_transactions_from_images', return_value=[{'d': 1}]) as mock_llm_extractor:
            transactions, used_fallback_model = main_module._vision_extract_with_fallbacks([b'page'])

        assert transactions == [{'d': 1}]
        assert used_fallback_model is True
        mock_llm_extractor.assert_called_once_with([b'page'], provider='gemini')

    def test_falls_back_to_mistral_when_bedrock_and_gemini_fail(self, monkeypatch):
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: provider in ('gemini', 'mistral'))

        def fake_extract(images, provider):
            if provider == 'gemini':
                raise main_module.LLMExtractionError('gemini down')
            return [{'d': 'from mistral'}]

        with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', side_effect=main_module.LLMExtractionError('bedrock down')), \
                patch.object(main_module.llm_extractor, 'extract_transactions_from_images', side_effect=fake_extract):
            transactions, used_fallback_model = main_module._vision_extract_with_fallbacks([b'page'])

        assert transactions == [{'d': 'from mistral'}]
        assert used_fallback_model is True

    def test_skips_unconfigured_fallback_providers(self, monkeypatch):
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: False)

        with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', side_effect=main_module.LLMExtractionError('bedrock down')), \
                patch.object(main_module.llm_extractor, 'extract_transactions_from_images') as mock_llm_extractor:
            with pytest.raises(main_module.LLMExtractionError, match='bedrock down'):
                main_module._vision_extract_with_fallbacks([b'page'])

        mock_llm_extractor.assert_not_called()

    def test_raises_last_error_when_every_tier_fails(self, monkeypatch):
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: True)

        def fake_extract(images, provider):
            raise main_module.LLMExtractionError(f'{provider} failed')

        with patch.object(main_module.bedrock_vision, 'extract_transactions_from_images', side_effect=main_module.LLMExtractionError('bedrock failed')), \
                patch.object(main_module.llm_extractor, 'extract_transactions_from_images', side_effect=fake_extract):
            with pytest.raises(main_module.LLMExtractionError, match='mistral failed'):
                main_module._vision_extract_with_fallbacks([b'page'])

    def test_vision_extraction_available_true_when_any_tier_configured(self, monkeypatch):
        monkeypatch.setattr(main_module.bedrock_vision, 'is_configured', lambda: False)
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: provider == 'mistral')
        assert main_module.vision_extraction_available() is True

    def test_vision_extraction_available_false_when_nothing_configured(self, monkeypatch):
        monkeypatch.setattr(main_module.bedrock_vision, 'is_configured', lambda: False)
        monkeypatch.setattr(main_module.ai_client, 'is_configured_for', lambda provider: False)
        assert main_module.vision_extraction_available() is False
