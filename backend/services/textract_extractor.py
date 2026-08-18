"""
Amazon Textract-based extraction for bank statement PDFs with no
extractable text layer at all (see pdf_parser.py's has_extractable_text()
/ render_pages_as_images()). This is the first extraction tier tried for
such a PDF - ahead of the vision-LLM fallbacks in bedrock_vision.py and
services/ai_client.py's Gemini/Mistral - because Textract's table
detection is OCR/layout-based rather than generative: it reads what's
actually printed on the page instead of a model reconstructing a
plausible-looking JSON from an image, which is where a generative model
can quietly get a date, a transaction count, or a credit/debit column
wrong without any error to show for it.

Textract's AnalyzeDocument (TABLES feature) returns a grid of cells per
detected table, already row/column-aligned - exactly the same shape
pdfplumber's extract_tables() gives pdf_parser.py for a PDF that DOES
have a text layer. Reusing pdf_parser.looks_like_header_row() and
rows_to_csv_text() means Textract's output goes through the exact same
CSVParser (date normalization, amount/type resolution, duplicate
hashing, CSV-injection sanitization) as every other input path, rather
than needing its own normalization logic.

Credentials are picked up by boto3's standard chain (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY env vars, or an EC2 instance role) - never handled
directly in this module. Textract is a native AWS service, not a
third-party model on Bedrock - no AWS Marketplace subscription
involved, so it isn't subject to the INVALID_PAYMENT_INSTRUMENT failure
seen there.
"""
import os
from typing import List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from services.csv_parser import CSVParser, CSVParsingError
from services.pdf_parser import PDFParsingError, looks_like_header_row, rows_to_csv_text

AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')


def is_configured() -> bool:
    """Whether AWS credentials for Textract are present."""
    return bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'))


def _client():
    return boto3.client('textract', region_name=AWS_REGION)


def _cell_text(cell: dict, block_map: dict) -> str:
    """Reconstructs one cell's text from its child WORD/SELECTION_ELEMENT blocks."""
    words = []
    for rel in cell.get('Relationships', []):
        if rel['Type'] != 'CHILD':
            continue
        for child_id in rel['Ids']:
            child = block_map.get(child_id)
            if child is None:
                continue
            if child['BlockType'] == 'WORD':
                words.append(child['Text'])
            elif child['BlockType'] == 'SELECTION_ELEMENT' and child.get('SelectionStatus') == 'SELECTED':
                words.append('X')
    return ' '.join(words).strip()


def _table_to_grid(table_block: dict, block_map: dict) -> List[List[str]]:
    """Reconstructs one TABLE block's cells into a row/column-ordered grid of strings."""
    cell_ids = [
        cid for rel in table_block.get('Relationships', []) if rel['Type'] == 'CHILD'
        for cid in rel['Ids']
    ]
    cells = [block_map[cid] for cid in cell_ids if block_map.get(cid, {}).get('BlockType') == 'CELL']
    if not cells:
        return []

    max_row = max(c['RowIndex'] for c in cells)
    max_col = max(c['ColumnIndex'] for c in cells)
    grid = [['' for _ in range(max_col)] for _ in range(max_row)]
    for cell in cells:
        grid[cell['RowIndex'] - 1][cell['ColumnIndex'] - 1] = _cell_text(cell, block_map)
    return grid


def extract_transactions_from_images(image_pages: List[bytes]) -> List[dict]:
    """
    Runs Textract's table detection on each rendered page image, keeps
    only tables whose header row looks like a transaction table (not a
    bank's account-summary/metadata table, which Textract detects just
    as readily), and merges the matching tables' rows across all pages
    into one CSV, then parses it with the existing CSVParser.

    Returns:
        List of transaction dicts in the same shape CSVParser produces.

    Raises:
        PDFParsingError: if Textract isn't configured, no images were
        given, the request fails, or no page contains a recognizable
        transaction table.
    """
    if not is_configured():
        raise PDFParsingError('AWS Textract is not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.')
    if not image_pages:
        raise PDFParsingError('No page images were provided for Textract extraction')

    header: Optional[List[str]] = None
    data_rows: List[List[str]] = []

    for image_bytes in image_pages:
        try:
            response = _client().analyze_document(Document={'Bytes': image_bytes}, FeatureTypes=['TABLES'])
        except (BotoCoreError, ClientError) as e:
            raise PDFParsingError(f'AWS Textract request failed: {e}')

        block_map = {b['Id']: b for b in response.get('Blocks', [])}
        for block in response.get('Blocks', []):
            if block['BlockType'] != 'TABLE':
                continue
            grid = _table_to_grid(block, block_map)
            for row in grid:
                if not any(cell.strip() for cell in row):
                    continue
                if looks_like_header_row(row):
                    if header is None:
                        header = row
                    continue  # a repeated header on a later page/table, not a data row
                if header is not None and len(row) == len(header):
                    data_rows.append(row)

    if header is None or not data_rows:
        raise PDFParsingError('AWS Textract could not find a transaction table in this file')

    csv_text = rows_to_csv_text(header, data_rows)
    try:
        return CSVParser(csv_text.encode('utf-8')).parse()
    except CSVParsingError as e:
        raise PDFParsingError(f'AWS Textract found a table but it could not be parsed as transactions: {e}')
