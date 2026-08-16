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

extract_raw_text() is the fallback path: when the PDF has no
machine-readable table grid (e.g. it's a flattened/scanned layout),
CSVParser has nothing to parse, so the caller should fall back to the
existing LLM extractor (services/llm_extractor.py) with this raw text
instead, exactly as it already does for CSVs the deterministic parser
can't make sense of.
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
    """
    cells = [str(c or '').strip().lower() for c in row]
    has_date = any('date' in c for c in cells)
    has_amount = any(h in c for c in cells for h in ('debit', 'credit', 'amount'))
    has_description = any(h in c for c in cells for h in ('particulars', 'narration', 'description'))
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
    """Plain-text extraction across all pages, for the AI fallback path when table extraction fails."""
    if not file_content:
        raise PDFParsingError('File content is empty')
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except Exception as e:
        raise PDFParsingError(f'Could not read PDF file: {e}')


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
