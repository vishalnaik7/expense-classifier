"""
LLM-based fallback extraction for bank statement files the deterministic
CSVParser/pdf_parser cannot make sense of (unusual layouts, non-standard
column naming, or - for PDFs - no extractable text layer at all). Used
only as a fallback after the deterministic parser raises.

Two extraction modes, sharing the same schema/prompt/normalization:
- extract_transactions() - text-based, for CSVs and PDFs that have a text
  layer but an unrecognized structure.
- extract_transactions_from_images() - vision-based, for PDFs with zero
  extractable text (e.g. some HDFC statements draw "text" as vector glyph
  outlines with no underlying character data - see pdf_parser.py's
  has_extractable_text()), where there is no text to extract at all and a
  vision-capable model must read the rendered page images directly.

Privacy note: this sends the raw (truncated) file text or page images to
whichever open-source model services/ai_client.py is pointed at (Ollama
locally, Groq in production - see that module's docstring), never to a
paid Anthropic/OpenAI API. It is opt-in via ai_client.is_configured() -
if the active provider isn't ready, is_configured() returns False and
callers should skip straight to the deterministic error.
"""
import base64
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional

from services import ai_client

# Keep latency bounded and stay well under the model's context window. A
# personal bank statement CSV (capped at 10MB by the upload endpoint) is
# usually far smaller than this in practice; very large files are truncated
# and may not be fully covered by the fallback. Extracted rows are still
# validated per-row by _normalize() below - small open-source models are
# more prone to imperfect extraction than Claude was, so an empty/
# all-invalid result correctly falls through to LLMExtractionError rather
# than being trusted blindly.
MAX_INPUT_CHARS = 60000

# Vision models commonly cap how many images can go in a single request
# (e.g. Groq's qwen/qwen3.6-27b allows at most 3) - batch page images into
# groups of this size and merge the extracted transactions across
# requests, rather than sending every rendered page at once.
MAX_IMAGES_PER_REQUEST = 3

EXTRACTION_SYSTEM_PROMPT = """You are an expert AI data extraction engine specializing in messy financial documents and bank statements.

### Problem Context:
The uploaded statement's content may contain metadata, empty rows, or non-standard headers at the top (e.g. "STATEMENT OF ACCOUNT", account summaries, bank details, "Unnamed" columns). Column names vary by bank - a debit/withdrawal column might be labeled "Debit", "Withdrawal", "Withdrawal Amt.", "Paid Out", or similar; a credit/deposit column might be labeled "Credit", "Deposit", "Deposit Amt.", "Paid In", or similar.

### Instructions:
1. Ignore any top-level bank metadata, account summaries, or irrelevant header rows.
2. Locate the actual transaction table containing financial records.
3. Identify and extract every individual transaction. Even if column names are missing, messy, or unfamiliar, map the data intelligently to the required fields based on their meaning, not exact wording.
4. Normalize every date to YYYY-MM-DD format.
5. Classify each transaction strictly as "CREDIT" (money in) or "DEBIT" (money out).
6. If a running balance column exists, extract it; otherwise use null.
7. If you cannot confidently find a transaction table, return an empty transactions array - do not invent data."""

_VISION_INSTRUCTIONS = """

### Additional Instructions for Reading Images:
You are given one or more images of bank statement pages (in reading order - read them in the order given, top to bottom, left to right within each page). Read the table exactly as printed, including numbers with commas/decimals. If a row's narration wraps across multiple lines within the same table row, treat it as one transaction, not several."""


class LLMExtractionError(Exception):
    """Raised when the LLM fallback cannot produce usable transactions."""
    pass


def is_configured() -> bool:
    """Whether the AI fallback is enabled (the active provider is ready)."""
    return ai_client.is_configured()


_TRANSACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Transaction date normalized to YYYY-MM-DD"},
                    "description": {"type": "string", "description": "Narration, merchant, or remarks"},
                    "amount": {"type": "number", "description": "Absolute transaction amount"},
                    "type": {"type": "string", "enum": ["CREDIT", "DEBIT"]},
                    "balance": {"type": ["number", "null"], "description": "Running balance after this transaction, if available"},
                },
                "required": ["date", "description", "amount", "type", "balance"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["transactions"],
    "additionalProperties": False,
}


def _build_system_prompt(vision: bool = False) -> str:
    base = EXTRACTION_SYSTEM_PROMPT + (_VISION_INSTRUCTIONS if vision else '')
    return (
        f'{base}\n\n'
        'Respond with ONLY a single JSON object matching exactly this JSON Schema '
        f'(no markdown fences, no extra text):\n{json.dumps(_TRANSACTION_SCHEMA, indent=2)}'
    )


def _request_and_normalize(model: str, messages: List[Dict], max_tokens: int = 16000) -> List[Dict]:
    """Shared request/response handling for both the text and vision extraction requests below."""
    try:
        client = ai_client.get_client()
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except ai_client.AIProviderError as e:
        raise LLMExtractionError(str(e))
    except Exception as e:
        hint = ai_client.connection_hint(e)
        raise LLMExtractionError(f'AI extraction request failed: {e}' + (f' ({hint})' if hint else ''))

    choice = response.choices[0] if response.choices else None
    if choice is None or choice.finish_reason == 'content_filter':
        raise LLMExtractionError('AI declined to process this file')

    text_block = (choice.message.content or '').strip()
    if not text_block:
        raise LLMExtractionError('AI returned no extractable content')

    try:
        payload = json.loads(text_block)
    except json.JSONDecodeError as e:
        raise LLMExtractionError(f'AI returned malformed JSON: {e}')

    if not isinstance(payload, dict):
        raise LLMExtractionError('AI returned an unexpected response shape')

    raw_rows = payload.get('transactions', [])
    if not raw_rows:
        raise LLMExtractionError('AI could not find a transaction table in this file')

    transactions = [t for t in (_normalize(row) for row in raw_rows) if t is not None]

    if not transactions:
        raise LLMExtractionError('AI-extracted rows were not in a usable format')

    return transactions


def extract_transactions(file_content: bytes) -> List[Dict]:
    """
    Ask the configured open-source model to extract transactions from a
    bank statement file (CSV, or a PDF's extracted text) that the
    deterministic parser couldn't handle.

    Returns:
        List of transaction dicts in the same shape CSVParser produces
        (date, description, amount, type, hash, raw_amount).

    Raises:
        LLMExtractionError: if the fallback isn't configured, the request
        fails, the model declines, or no usable transactions come back.
    """
    if not is_configured():
        raise LLMExtractionError(
            'AI-assisted parsing is not configured. '
            + ai_client.not_configured_hint()
        )

    try:
        text = file_content.decode('utf-8', errors='replace')
    except Exception as e:
        raise LLMExtractionError(f'Could not read file as text: {e}')

    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]

    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": f"Extract every transaction from this bank statement file:\n\n{text}"},
    ]
    return _request_and_normalize(ai_client.get_model(), messages)


def extract_transactions_from_images(image_pages: List[bytes]) -> List[Dict]:
    """
    Ask a vision-capable open-source model to extract transactions
    directly from rendered bank statement page images. This is the last
    resort for a PDF with no extractable text layer at all (see
    pdf_parser.py's has_extractable_text() / render_pages_as_images()),
    where extract_transactions() has no text to work with in the first
    place - vision models generally require a different, larger model
    than the fast text model used elsewhere (services/ai_client.py's
    get_vision_model()), and this is opt-in on top of AI extraction
    already being opt-in: it only runs when both the deterministic parser
    and the text-based AI fallback have nothing to work with.

    Returns:
        List of transaction dicts in the same shape CSVParser produces.

    Raises:
        LLMExtractionError: if the fallback isn't configured, no images
        were provided, the request fails, the model declines, or no
        usable transactions come back.
    """
    if not is_configured():
        raise LLMExtractionError(
            'AI-assisted parsing is not configured. '
            + ai_client.not_configured_hint()
        )
    if not image_pages:
        raise LLMExtractionError('No page images were provided for vision-based extraction')

    model = ai_client.get_vision_model()
    transactions: List[Dict] = []
    last_error: Optional[LLMExtractionError] = None

    for start in range(0, len(image_pages), MAX_IMAGES_PER_REQUEST):
        batch = image_pages[start:start + MAX_IMAGES_PER_REQUEST]
        content = [{
            "type": "text",
            "text": "Extract every transaction visible in these bank statement page images, in the order given:",
        }]
        for image_bytes in batch:
            encoded = base64.b64encode(image_bytes).decode('ascii')
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})

        messages = [
            {"role": "system", "content": _build_system_prompt(vision=True)},
            {"role": "user", "content": content},
        ]
        try:
            transactions.extend(_request_and_normalize(model, messages))
        except LLMExtractionError as e:
            last_error = e

    if not transactions:
        raise last_error or LLMExtractionError('AI could not find a transaction table in this file')

    return transactions


def _normalize(row: Dict) -> Optional[Dict]:
    """Convert one LLM-extracted row into CSVParser's transaction shape, or None if unusable."""
    try:
        date_str = str(row['date']).strip()
        datetime.strptime(date_str, '%Y-%m-%d')
    except (KeyError, ValueError, TypeError):
        return None

    description = str(row.get('description', '')).strip()
    if not description:
        return None

    try:
        amount = abs(float(row['amount']))
    except (KeyError, TypeError, ValueError):
        return None
    if amount <= 0:
        return None

    txn_type = 'debit' if str(row.get('type', '')).strip().upper() == 'DEBIT' else 'credit'
    raw_amount = amount if txn_type == 'debit' else -amount

    # Same hash formula as CSVParser._create_hash, so duplicate detection
    # stays consistent regardless of which path parsed a transaction.
    tx_hash = hashlib.sha256(f'{date_str}|{description}|{amount}'.encode('utf-8')).hexdigest()

    return {
        'date': date_str,
        'description': description,
        'amount': amount,
        'type': txn_type,
        'hash': tx_hash,
        'raw_amount': raw_amount,
    }
