"""
AWS Bedrock (Amazon Nova Lite) vision extraction for bank statement PDFs
with no extractable text layer. This is a lower-confidence fallback tier,
tried after services/textract_extractor.py (Textract's OCR-based table
detection is the trusted first attempt for such a PDF) - every other AI
feature in the app (chat, goal advice, text-based extraction) still goes
through services/ai_client.py's Ollama/Groq/Gemini/Mistral abstraction;
this module is a separate, narrower path for image-based PDF extraction
only, using the Bedrock Converse API (boto3's bedrock-runtime client).

Nova Lite specifically, not one of Bedrock's Claude models, because
Claude's Bedrock access goes through an AWS Marketplace subscription that
can fail (INVALID_PAYMENT_INSTRUMENT) independent of IAM permissions or
API access, while Nova Lite is an Amazon first-party model and isn't
subject to that.

Pages are sent a few at a time rather than all at once (see
MAX_PAGES_PER_REQUEST): a dense multi-page statement's transaction list
can easily exceed a single response's max output tokens, and Nova Lite's
hard limit (10000 tokens) is too small to safely fit an entire
statement's JSON in one response - going over produces a truncated,
unparseable response rather than a clean error.

Credentials are picked up by boto3's standard chain (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY env vars, or an EC2 instance role) - never handled
directly in this module.

Region note: in ap-south-1 (Mumbai), this model needs a cross-region
inference profile ID rather than the bare model ID for on-demand
invocation - the bare model ID is listed by `aws bedrock
list-foundation-models` but isn't directly invocable here; check `aws
bedrock list-inference-profiles --region <region>` for the right ID.
Override BEDROCK_MODEL_ID/AWS_REGION if deploying from a region where
this differs.
"""
import json
import os
import re
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from services.llm_extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    VISION_INSTRUCTIONS,
    TRANSACTION_SCHEMA,
    normalize_extracted_row,
    LLMExtractionError,
)

AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'apac.amazon.nova-lite-v1:0')

_IMAGE_FORMAT = 'png'
_MAX_TOKENS = 8000
MAX_PAGES_PER_REQUEST = 2


def is_configured() -> bool:
    """Whether AWS credentials for Bedrock are present."""
    return bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'))


def _client():
    return boto3.client('bedrock-runtime', region_name=AWS_REGION)


def _system_prompt() -> str:
    return (
        EXTRACTION_SYSTEM_PROMPT + VISION_INSTRUCTIONS + '\n\n'
        'Respond with ONLY a single JSON object matching exactly this JSON Schema '
        f'(no markdown fences, no extra text):\n{json.dumps(TRANSACTION_SCHEMA, indent=2)}'
    )


def _build_content(image_batch: List[bytes]) -> List[Dict]:
    content = [{"text": "Extract every transaction visible in these bank statement page images, in the order given:"}]
    for image_bytes in image_batch:
        content.append({"image": {"format": _IMAGE_FORMAT, "source": {"bytes": image_bytes}}})
    return content


def _invoke(content: List[Dict]) -> List[Dict]:
    """Calls Bedrock on one batch of page images and returns normalized transactions, or raises LLMExtractionError."""
    try:
        response = _client().converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": _system_prompt()}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": _MAX_TOKENS},
        )
    except (BotoCoreError, ClientError) as e:
        raise LLMExtractionError(f'AWS Bedrock request failed ({BEDROCK_MODEL_ID}): {e}')

    stop_reason = response.get('stopReason')
    if stop_reason in ('content_filtered', 'guardrail_intervened'):
        raise LLMExtractionError(f'AWS Bedrock declined to process this file ({BEDROCK_MODEL_ID})')

    text_block = ''.join(
        block['text'] for block in response.get('output', {}).get('message', {}).get('content', [])
        if 'text' in block
    ).strip()
    if not text_block:
        raise LLMExtractionError(f'AWS Bedrock returned no extractable content ({BEDROCK_MODEL_ID})')

    # Nova Lite sometimes wraps the JSON in a markdown code fence anyway,
    # despite the system prompt explicitly saying not to - strip it
    # defensively rather than failing outright.
    if text_block.startswith('```'):
        text_block = re.sub(r'^```(?:json)?\s*', '', text_block)
        text_block = re.sub(r'\s*```$', '', text_block)

    try:
        payload = json.loads(text_block)
    except json.JSONDecodeError as e:
        if stop_reason == 'max_tokens':
            raise LLMExtractionError(
                f'AWS Bedrock response from {BEDROCK_MODEL_ID} was cut off before finishing '
                f'(hit the {_MAX_TOKENS}-token limit)'
            )
        raise LLMExtractionError(f'AWS Bedrock returned malformed JSON ({BEDROCK_MODEL_ID}): {e}')

    if not isinstance(payload, dict):
        raise LLMExtractionError(f'AWS Bedrock returned an unexpected response shape ({BEDROCK_MODEL_ID})')

    raw_rows = payload.get('transactions', [])
    if not raw_rows:
        raise LLMExtractionError('AI could not find a transaction table in this file')

    transactions = [t for t in (normalize_extracted_row(row) for row in raw_rows) if t is not None]

    if not transactions:
        raise LLMExtractionError(f'AI-extracted rows were not in a usable format ({BEDROCK_MODEL_ID})')

    return transactions


def extract_transactions_from_images(image_pages: List[bytes]) -> List[Dict]:
    """
    Ask Amazon Nova Lite (via Bedrock's Converse API) to extract
    transactions directly from rendered bank statement page images.
    Pages are processed a few at a time (MAX_PAGES_PER_REQUEST) to stay
    within the model's max output tokens, and results are merged across
    batches; a batch that fails is skipped rather than failing the whole
    statement, as long as at least one batch succeeds.

    This is always a lower-confidence result - Nova Lite is a small
    model, prone to hallucinating a full fake transaction table from a
    blank or unclear image and to garbling real statement data (wrong
    dates, corrupted merchant text) on a dense multi-page statement.
    Callers should treat any result from this module as lower-confidence
    and warn accordingly rather than trusting it silently - see main.py's
    _vision_extract_with_fallbacks().

    Raises:
        LLMExtractionError: if Bedrock isn't configured, no images were
        given, or every batch failed.
    """
    if not is_configured():
        raise LLMExtractionError(
            'AWS Bedrock is not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.'
        )
    if not image_pages:
        raise LLMExtractionError('No page images were provided for vision-based extraction')

    all_transactions: List[Dict] = []
    last_error: Optional[LLMExtractionError] = None

    for start in range(0, len(image_pages), MAX_PAGES_PER_REQUEST):
        batch = image_pages[start:start + MAX_PAGES_PER_REQUEST]
        try:
            all_transactions.extend(_invoke(_build_content(batch)))
        except LLMExtractionError as e:
            last_error = e

    if not all_transactions:
        raise last_error or LLMExtractionError('AI could not find a transaction table in this file')

    return all_transactions
