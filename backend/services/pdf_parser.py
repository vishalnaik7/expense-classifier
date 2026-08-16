"""
PDF bank statement support.

Real bank statement PDFs (IDFC FIRST, HDFC, ICICI, SBI, ...) are almost
always the same shape underneath the branding: a gridded table with a
Transaction/Value Date, a Particulars/Narration column, a Debit/Credit or
single Amount column, and a running Balance, repeated across pages with
the header row printed again on every page, usually preceded by a small
Opening/Total Debit/Total Credit/Closing Balance summary block that is
NOT the transaction table.

Rather than re-implementing date parsing, Debit/Credit resolution, and
row validation a second time for PDFs, this module extracts that table
with pdfplumber and reconstructs it as CSV text, then hands it to the
already-hardened CSVParser (services/csv_parser.py) - so a PDF statement
gets exactly the same date-format support, duplicate hashing, and
CSV-injection sanitization as a CSV upload, with only one place that
logic needs to be correct.

extract_raw_text() is the first fallback path: when the deterministic
table extraction above couldn't confidently find/recognize a transaction
table (an unfamiliar bank's column naming), the caller should fall back
to the existing LLM extractor (services/llm_extractor.py) with this raw
text, exactly as it already does for CSVs the deterministic parser can't
make sense of.

render_pages_as_images() is the second fallback path, for a case plain
text extraction cannot help with at all: some bank statement PDFs (seen
in practice from HDFC) have vector-drawn table grid lines but ZERO
extractable text characters - the "text" is rendered as glyph outlines
rather than actual character data, so `page.chars` is empty and
`extract_text()`/`extract_tables()` cell values come back blank even
though the statement is perfectly readable when the page is rendered
visually. This is functionally identical to a scanned image for
data-extraction purposes (even though there's no single large embedded
raster image to point at - it's the whole vector page that has no text
layer), so it needs vision-based extraction: render each page to a PNG
and let a vision-capable model (services/llm_extractor.py's
extract_transactions_from_images()) read it directly.
"""
import csv
import io
from typing import List, Optional

import pdfplumber

from .csv_parser import CSVParser, CSVParsingError


class PDFParsingError(Exception):
    """Raised when no transaction table can be found/parsed in the PDF."""
    pass


def _looks_like_header_row(row: List[Optional[str]]) -> bool:
    """
    Does this extracted table row look like the transaction table's header
    (not the small Opening/Total Debit/Total Credit/Closing Balance summary
    block that most bank statement PDFs print above it)?

    Different banks name the amount and narration columns differently -
    IDFC FIRST uses "Debit"/"Credit" and "Particulars", HDFC uses
    "Withdrawal Amt."/"Deposit Amt." and "Narration", SBI uses "Credit"/
    "Debit" and "Transaction Reference" - so this checks a broader set of
    synonyms rather than one bank's exact wording, to avoid silently
    failing to even recognize the header on a format this hasn't
    specifically been tested against before. "transaction reference" is
    matched as the exact phrase, not bare "reference", since a separate
    "Ref.No./Chq.No." column must not be mistaken for the narration.
    """
    cells = [str(c or '').strip().lower() for c in row]
    has_date = any('date' in c for c in cells)
    has_amount = any(
        h in c for c in cells
        for h in ('debit', 'credit', 'amount', 'withdrawal', 'deposit')
    )
    has_description = any(
        h in c for c in cells
        for h in ('particulars', 'narration', 'description', 'transaction reference')
    )
    return has_date and has_amount and has_description


def _rows_to_csv_text(header: List[str], rows: List[List[Optional[str]]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        # Multi-line cells (a narration that wrapped inside its table cell)
        # come back from pdfplumber with embedded newlines - flatten them
        # to spaces so each transaction stays exactly one CSV row.
        writer.writerow(['' if cell is None else str(cell).replace('\n', ' ').strip() for cell in row])
    return buffer.getvalue()


def extract_transaction_csv(file_content: bytes) -> str:
    """
    Find the transaction table across every page of the PDF and
    reconstruct it as CSV text (one header row + the real data rows,
    with repeated per-page headers and non-matching rows dropped).

    Raises:
        PDFParsingError: if no page contains a recognizable transaction
        table, or the file itself can't be opened as a PDF.
    """
    if not file_content:
        raise PDFParsingError('File content is empty')

    header: Optional[List[str]] = None
    data_rows: List[List[Optional[str]]] = []

    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    for row in table:
                        if not row or all(not str(cell or '').strip() for cell in row):
                            continue
                        if _looks_like_header_row(row):
                            if header is None:
                                header = [str(cell or '').strip() for cell in row]
                            continue  # a repeated header on a later page, not a data row
                        if header is not None and len(row) == len(header):
                            data_rows.append(row)
    except PDFParsingError:
        raise
    except Exception as e:
        raise PDFParsingError(f'Could not read PDF file: {e}')

    if header is None or not data_rows:
        raise PDFParsingError('Could not find a transaction table in this PDF')

    return _rows_to_csv_text(header, data_rows)


def extract_raw_text(file_content: bytes) -> str:
    """
    Best-effort extraction for the AI fallback path, used when
    extract_transaction_csv() couldn't confidently locate/recognize a
    transaction table on its own (e.g. an unfamiliar bank's column
    naming). Prefers each page's raw table-cell grid - preserving column
    alignment, even for a header this module's own heuristic doesn't
    recognize - over plain linearized text, since a language model can
    map an unfamiliar header like "Withdrawal Amt." to a debit column far
    more reliably than word-position-based text extraction can, but only
    if it can actually see the columns rather than a jumbled line of text
    where a wide table's cells were interleaved out of order. Falls back
    to plain text extraction only for pages with no detectable table grid
    at all (e.g. a scanned/flattened layout).
    """
    if not file_content:
        raise PDFParsingError('File content is empty')
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            page_blocks = []
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if tables:
                    lines = [f'--- Page {page_num} ---']
                    for table in tables:
                        for row in table:
                            cells = ['' if cell is None else str(cell).replace('\n', ' ').strip() for cell in row]
                            if any(cells):
                                lines.append(' | '.join(cells))
                    page_blocks.append('\n'.join(lines))
                else:
                    text = (page.extract_text() or '').strip()
                    if text:
                        page_blocks.append(f'--- Page {page_num} ---\n{text}')
            return '\n\n'.join(page_blocks)
    except Exception as e:
        raise PDFParsingError(f'Could not read PDF file: {e}')


def has_extractable_text(file_content: bytes) -> bool:
    """
    Whether this PDF has any real character-level text data at all, on
    any page. Some bank-generated statement PDFs draw their "text" as
    vector glyph outlines with no underlying character data (see the
    module docstring) - for those, `page.chars` is empty and every text-
    or table-based extraction path (extract_transaction_csv,
    extract_raw_text) is fundamentally unable to help, no matter how the
    header-matching heuristics are tuned, so the caller should skip
    straight to render_pages_as_images() + vision-based extraction
    instead of wasting a text-based AI fallback call on empty input.
    """
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            return any(len(page.chars) > 0 for page in pdf.pages)
    except Exception:
        return False


# Vision requests grow expensive fast with many high-resolution images -
# cap both how many pages get rendered and the resolution, enough to keep
# a statement's numbers legible without ballooning request size/latency.
MAX_VISION_PAGES = 6
VISION_IMAGE_RESOLUTION = 150


def render_pages_as_images(file_content: bytes, max_pages: int = MAX_VISION_PAGES) -> List[bytes]:
    """
    Rasterizes up to `max_pages` pages of the PDF to PNG image bytes, for
    vision-based extraction (services/llm_extractor.py's
    extract_transactions_from_images()). This renders the page's full
    visual content - including vector-drawn "text" that has no
    extractable character data - so it works even where every text-layer
    extraction path in this module cannot.

    Raises:
        PDFParsingError: if the file can't be opened/rendered as a PDF.
    """
    if not file_content:
        raise PDFParsingError('File content is empty')
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            images = []
            for page in pdf.pages[:max_pages]:
                png_buffer = io.BytesIO()
                page.to_image(resolution=VISION_IMAGE_RESOLUTION).original.save(png_buffer, format='PNG')
                images.append(png_buffer.getvalue())
            return images
    except PDFParsingError:
        raise
    except Exception as e:
        raise PDFParsingError(f'Could not render PDF pages as images: {e}')


def parse(file_content: bytes) -> List[dict]:
    """
    Deterministic PDF parsing entry point: extract the transaction table
    and run it through the same CSVParser used for .csv uploads, so date
    formats, Debit/Credit resolution, continuation handling, and
    validation are identical either way.

    Raises:
        PDFParsingError: if no transaction table could be found, or the
        extracted table failed CSVParser's own validation.
    """
    csv_text = extract_transaction_csv(file_content)
    try:
        return CSVParser(csv_text.encode('utf-8')).parse()
    except CSVParsingError as e:
        raise PDFParsingError(str(e))
