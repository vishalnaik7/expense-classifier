"""
Unit tests for PDF bank statement support (services/pdf_parser.py).

Builds a small synthetic multi-page bank-statement-shaped PDF with
reportlab (bordered/gridded tables, a repeated header on each page, and
an Opening Balance summary row - the same shape real bank statement PDFs
use) to verify pdfplumber-based extraction without depending on any
real, non-redistributable bank statement file.
"""
import io

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, SimpleDocTemplate, Table, TableStyle

from services.pdf_parser import (
    PDFParsingError,
    extract_raw_text,
    extract_transaction_csv,
    has_extractable_text,
    parse,
    render_pages_as_images,
)

TXN_HEADER = ['Transaction Date', 'Particulars', 'Debit', 'Credit', 'Balance']

_GRID_STYLE = TableStyle([
    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ('FONTSIZE', (0, 0), (-1, -1), 8),
])


def _build_statement_pdf(page1_rows, page2_rows=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    elements = [Table([TXN_HEADER] + page1_rows, style=_GRID_STYLE)]
    if page2_rows:
        elements.append(PageBreak())
        elements.append(Table([TXN_HEADER] + page2_rows, style=_GRID_STYLE))

    doc.build(elements)
    return buffer.getvalue()


def _build_image_only_pdf(lines, num_pages=1):
    """
    A PDF whose page content is a single embedded raster image with zero
    real text objects - page.chars comes back empty, the same as the
    real-world case this module is built to handle (some bank PDF
    generators draw "text" as vector glyph outlines with no character
    data at all). The generation technique differs from the real case,
    but the resulting property under test - zero extractable text - is
    identical, which is what has_extractable_text()/the vision fallback
    actually depend on.
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
    image_reader = ImageReader(img_buffer)

    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    for _ in range(num_pages):
        c.drawImage(image_reader, 50, 500, width=500, height=150)
        c.showPage()
    c.save()
    return pdf_buffer.getvalue()


def test_extract_transaction_csv_reconstructs_header_and_rows():
    pdf_bytes = _build_statement_pdf([
        ['', 'Opening Balance', '', '', '231789.00'],
        ['01-Jun-2026', 'UPI/DR/063110630325/CHALO/HDFC/Pay', '75.00', '', '231714.00'],
        ['08-Jun-2026', 'NEFT/Salary Credit', '', '72000.00', '303714.00'],
    ])

    csv_text = extract_transaction_csv(pdf_bytes)

    assert 'Transaction Date' in csv_text
    assert 'CHALO' in csv_text
    assert csv_text.count('Transaction Date') == 1  # header appears once, not once per row


def test_parse_produces_valid_transactions_via_csv_parser():
    pdf_bytes = _build_statement_pdf([
        ['', 'Opening Balance', '', '', '231789.00'],
        ['01-Jun-2026', 'UPI/DR/063110630325/CHALO/HDFC/Pay', '75.00', '', '231714.00'],
        ['08-Jun-2026', 'NEFT/Salary Credit', '', '72000.00', '303714.00'],
    ])

    transactions = parse(pdf_bytes)

    # The "Opening Balance" summary row has no date and is correctly dropped,
    # same as CSVParser already does for a CSV upload with a stray summary row.
    assert len(transactions) == 2
    assert transactions[0]['date'] == '2026-06-01'
    assert transactions[0]['type'] == 'debit'
    assert transactions[0]['amount'] == 75.0
    assert transactions[1]['date'] == '2026-06-08'
    assert transactions[1]['type'] == 'credit'
    assert transactions[1]['amount'] == 72000.0


def test_repeated_header_across_pages_is_deduplicated_and_both_pages_parsed():
    pdf_bytes = _build_statement_pdf(
        page1_rows=[['01-Jun-2026', 'UPI/DR/CHALO/Pay', '75.00', '', '231714.00']],
        page2_rows=[['05-Jul-2026', 'IRCTC Ticket Booking pinelab', '442.70', '', '250000.00']],
    )

    transactions = parse(pdf_bytes)

    assert len(transactions) == 2
    dates = {t['date'] for t in transactions}
    assert dates == {'2026-06-01', '2026-07-05'}


def test_irctc_transaction_is_extracted_with_full_description():
    pdf_bytes = _build_statement_pdf([
        ['11-Jul-2026', 'UPI/DR/588566388572/IRCTC Ra/YESB/IRCTC@y/Payment for 100006700229689', '442.70', '', '312968.21'],
    ])

    transactions = parse(pdf_bytes)

    assert len(transactions) == 1
    assert 'IRCTC' in transactions[0]['description']


def test_no_transaction_table_raises():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    # A table with no date/amount/description-like headers at all
    doc.build([Table([['Foo', 'Bar'], ['1', '2']], style=_GRID_STYLE)])

    with pytest.raises(PDFParsingError, match='transaction table'):
        parse(buffer.getvalue())


def test_empty_file_raises():
    with pytest.raises(PDFParsingError, match='empty'):
        parse(b'')


def test_garbage_bytes_raise_pdf_parsing_error():
    with pytest.raises(PDFParsingError):
        parse(b'this is not a pdf file at all')


def test_seven_column_layout_with_wrapped_narration_cells_like_a_real_statement():
    # Mirrors the real IDFC FIRST layout: Transaction Date | Value Date |
    # Particulars | Cheque No | Debit | Credit | Balance, with a narration
    # that wraps onto a second line *inside its own table cell* (pdfplumber
    # returns that as one cell containing an embedded newline, not a
    # separate row - unlike the CSV continuation-row problem this app
    # already handles separately for plain-text exports).
    header = ['Transaction Date', 'Value Date', 'Particulars', 'Cheque No', 'Debit', 'Credit', 'Balance']
    rows = [
        ['', '', 'Opening Balance', '', '', '', '231789.00'],
        ['01-Jun-2026', '01-Jun-2026', 'UPI/DR/063110630325/CHALO/\nHDFC/chalo1./Pay', '', '75.00', '', '231714.00'],
        ['08-Jun-2026', '08-Jun-2026', 'NEFT/IDFB6159M0047702/RAN\nDEVELOPERS PRIVATE LIMITED', '', '', '72000.00', '303714.00'],
        ['15-Jul-2026', '15-Jul-2026', 'UPI/DR/619633007769/IRCTC\nTi/pinelab/Paymentforv1', '', '782.70', '', '308385.51'],
    ]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([header] + rows, style=_GRID_STYLE)])

    transactions = parse(buffer.getvalue())

    assert len(transactions) == 3
    irctc = next(t for t in transactions if 'IRCTC' in t['description'])
    assert irctc['amount'] == 782.70
    assert irctc['type'] == 'debit'
    # the wrapped second line survived and got flattened into one description
    assert 'pinelab' in irctc['description']


def test_hdfc_style_withdrawal_deposit_headers_are_recognized():
    # HDFC statements use "Withdrawal Amt." / "Deposit Amt." instead of
    # "Debit" / "Credit" - _looks_like_header_row() must recognize this as
    # a header, and CSVParser must resolve amounts from the resulting
    # 'debit'-named column (see the matching csv_parser.py regression test).
    header = ['Date', 'Narration', 'Chq./Ref.No.', 'Value Dt', 'Withdrawal Amt.', 'Deposit Amt.', 'Closing Balance']
    rows = [
        ['05/05/26', 'ACH D- HDFC BANK LTD-459198206', '0000002039555125', '05/05/26', '11,611.00', '', '9,525.05'],
        ['09/05/26', 'UPI-VODAFONE IDEA\nMAHAR-VIINAPPMAG@YBL-\nYESB0YBLUPI-529452803453-PAYMENT FROM PHONE',
         '0000529452803453', '09/05/26', '33.00', '', '9,492.05'],
        ['31/05/26', 'UPI-VISHAL DASHARATH NAI-9821948908@YBL-\nIDFB0040101-960934191163-PAYMENT FROM PHONE',
         '0000960934191163', '31/05/26', '', '15,000.00', '24,410.00'],
    ]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([header] + rows, style=_GRID_STYLE)])

    transactions = parse(buffer.getvalue())

    assert len(transactions) == 3
    vodafone = next(t for t in transactions if 'VODAFONE' in t['description'])
    assert vodafone['amount'] == 33.0
    assert vodafone['type'] == 'debit'
    salary_like = next(t for t in transactions if t['type'] == 'credit')
    assert salary_like['amount'] == 15000.0


def test_extract_raw_text_returns_readable_text_for_ai_fallback():
    pdf_bytes = _build_statement_pdf([
        ['01-Jun-2026', 'UPI/DR/CHALO/Pay', '75.00', '', '231714.00'],
    ])
    text = extract_raw_text(pdf_bytes)
    assert 'CHALO' in text


def test_extract_raw_text_preserves_table_column_structure():
    # The AI fallback needs column alignment, not jumbled linear text, to
    # reliably map an unfamiliar bank's header to date/description/amount -
    # extract_raw_text() should render each row with its cells still
    # separated, not run together the way plain page.extract_text() would.
    header = ['Date', 'Narration', 'Withdrawal Amt.', 'Deposit Amt.']
    rows = [['05/05/26', 'ACH D- HDFC BANK LTD', '11611.00', '']]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Table([header] + rows, style=_GRID_STYLE)])

    text = extract_raw_text(buffer.getvalue())

    assert 'Withdrawal Amt.' in text
    assert 'ACH D- HDFC BANK LTD' in text
    assert '11611.00' in text
    assert ' | ' in text  # cells are still visibly column-separated, not run together


class TestHasExtractableText:
    def test_true_for_a_normal_text_based_pdf(self):
        pdf_bytes = _build_statement_pdf([
            ['01-Jun-2026', 'UPI/DR/CHALO/Pay', '75.00', '', '231714.00'],
        ])
        assert has_extractable_text(pdf_bytes) is True

    def test_false_for_an_image_only_pdf(self):
        # Stands in for the real-world HDFC case: vector-drawn glyph
        # outlines with zero character-level text data - page.chars is
        # empty exactly like it is for a page that's just one embedded image.
        pdf_bytes = _build_image_only_pdf(['Date Narration Withdrawal Deposit', '05/05/26 ACH D 11611.00'])
        assert has_extractable_text(pdf_bytes) is False

    def test_false_for_garbage_bytes(self):
        assert has_extractable_text(b'not a real pdf') is False


class TestRenderPagesAsImages:
    def test_returns_one_png_per_page(self):
        pdf_bytes = _build_statement_pdf(
            page1_rows=[['01-Jun-2026', 'UPI/DR/CHALO/Pay', '75.00', '', '231714.00']],
            page2_rows=[['05-Jul-2026', 'IRCTC Ticket Booking', '442.70', '', '250000.00']],
        )
        images = render_pages_as_images(pdf_bytes)
        assert len(images) == 2
        for png_bytes in images:
            assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'  # PNG file signature

    def test_respects_max_pages(self):
        pdf_bytes = _build_statement_pdf(
            page1_rows=[['01-Jun-2026', 'UPI/DR/CHALO/Pay', '75.00', '', '231714.00']],
            page2_rows=[['05-Jul-2026', 'IRCTC Ticket Booking', '442.70', '', '250000.00']],
        )
        images = render_pages_as_images(pdf_bytes, max_pages=1)
        assert len(images) == 1

    def test_works_on_a_page_with_no_extractable_text(self):
        # This is the whole point: rendering must succeed even where every
        # text-layer extraction path in this module has nothing to read.
        pdf_bytes = _build_image_only_pdf(['Date Narration Withdrawal Deposit', '05/05/26 ACH D 11611.00'])
        images = render_pages_as_images(pdf_bytes)
        assert len(images) == 1
        assert images[0][:8] == b'\x89PNG\r\n\x1a\n'

    def test_empty_file_raises(self):
        with pytest.raises(PDFParsingError, match='empty'):
            render_pages_as_images(b'')

    def test_garbage_bytes_raise(self):
        with pytest.raises(PDFParsingError):
            render_pages_as_images(b'not a real pdf')
