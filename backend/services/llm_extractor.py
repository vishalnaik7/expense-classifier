"""
LLM-based fallback extraction for bank statement files the deterministic
CSVParser cannot make sense of (unusual layouts, embedded metadata rows
CSVParser's header-detection window didn't catch, non-standard column
naming). Used only as a fallback after CSVParser.parse() raises.

Privacy note: this path sends the raw (truncated) file text to whichever
open-source model services/ai_client.py is pointed at (Ollama locally,
Groq in production - see that module's docstring), never to a paid
Anthropic/OpenAI API. It is opt-in via ai_client.is_configured() - if the
active provider isn't ready, is_configured() returns False and callers
should skip straight to the deterministic error.
"""
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

EXTRACTION_SYSTEM_PROMPT = """You are an expert AI data extraction engine specializing in messy financial documents and CSV bank statements.

### Problem Context:
The uploaded file's raw text may contain metadata, empty rows, or non-standard headers at the top (e.g. "STATEMENT OF ACCOUNT", account summaries, bank details, "Unnamed" columns).

### Instructions:
1. Ignore any top-level bank metadata, account summaries, or irrelevant header rows.
2. Locate the actual transaction table containing financial records.
3. Identify and extract every individual transaction. Even if column names are missing or messy, map the data intelligently to the required fields.
4. Normalize every date to YYYY-MM-DD format.
5. Classify each transaction strictly as "CREDIT" (money in) or "DEBIT" (money out).
6. If a running balance column exists, extract it; otherwise use null.
7. If you cannot confidently find a transaction table in the text, return an empty transactions array - do not invent data."""


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


def extract_transactions(file_content: bytes) -> List[Dict]:
    """
    Ask the configured open-source model to extract transactions from a
    bank statement CSV that the deterministic parser couldn't handle.

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
            + ('Set GROQ_API_KEY.' if ai_client.AI_PROVIDER == 'groq' else 'Check AI_PROVIDER.')
        )

    try:
        text = file_content.decode('utf-8', errors='replace')
    except Exception as e:
        raise LLMExtractionError(f'Could not read file as text: {e}')

    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]

    system = (
        f'{EXTRACTION_SYSTEM_PROMPT}\n\n'
        'Respond with ONLY a single JSON object matching exactly this JSON Schema '
        f'(no markdown fences, no extra text):\n{json.dumps(_TRANSACTION_SCHEMA, indent=2)}'
    )

    try:
        client = ai_client.get_client()
        response = client.chat.completions.create(
            model=ai_client.get_model(),
            max_tokens=16000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Extract every transaction from this bank statement file:\n\n{text}"},
            ],
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
