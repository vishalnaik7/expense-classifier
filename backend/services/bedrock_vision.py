"""
AWS Bedrock vision extraction for bank statement PDFs with no extractable
text layer. Used specifically for this one fallback tier - every other AI
feature in the app (chat, goal advice, text-based extraction) still goes
through services/ai_client.py's Ollama/Groq/Gemini/Mistral abstraction;
this module is a separate, narrower path for image-based PDF extraction
only, using the Bedrock Converse API (boto3's bedrock-runtime client).

Tries Claude 3.5 Sonnet v2 first, then falls back to Amazon Nova Lite if
that fails for any reason - notably, third-party models like Claude go
through an AWS Marketplace subscription that can fail independently of
IAM permissions (e.g. INVALID_PAYMENT_INSTRUMENT), while Amazon's own
first-party models are not subject to that and keep working regardless.

Credentials are picked up by boto3's standard chain (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY env vars, or an EC2 instance role) - never handled
directly in this module.

Region note: in ap-south-1 (Mumbai), these models require a cross-region
inference profile ID rather than the bare model ID for on-demand
invocation (confirmed via `aws bedrock list-inference-profiles` - the
bare model IDs are listed but not directly invocable on-demand in this
region). Override BEDROCK_MODEL_ID/BEDROCK_FALLBACK_MODEL_ID/AWS_REGION
if deploying from a region where this differs.
"""
import json
import os
from typing import Dict, List, Tuple

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
BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'apac.anthropic.claude-3-5-sonnet-20241022-v2:0')
BEDROCK_FALLBACK_MODEL_ID = os.getenv('BEDROCK_FALLBACK_MODEL_ID', 'apac.amazon.nova-lite-v1:0')

_IMAGE_FORMAT = 'png'
_MAX_TOKENS = 8000


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


def _invoke(model_id: str, content: List[Dict]) -> List[Dict]:
    """Calls one Bedrock model and returns normalized transactions, or raises LLMExtractionError."""
    try:
        response = _client().converse(
            modelId=model_id,
            system=[{"text": _system_prompt()}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": _MAX_TOKENS},
        )
    except (BotoCoreError, ClientError) as e:
        raise LLMExtractionError(f'AWS Bedrock request failed ({model_id}): {e}')

    stop_reason = response.get('stopReason')
    if stop_reason in ('content_filtered', 'guardrail_intervened'):
        raise LLMExtractionError(f'AWS Bedrock declined to process this file ({model_id})')

    text_block = ''.join(
        block['text'] for block in response.get('output', {}).get('message', {}).get('content', [])
        if 'text' in block
    ).strip()
    if not text_block:
        raise LLMExtractionError(f'AWS Bedrock returned no extractable content ({model_id})')

    try:
        payload = json.loads(text_block)
    except json.JSONDecodeError as e:
        raise LLMExtractionError(f'AWS Bedrock returned malformed JSON ({model_id}): {e}')

    if not isinstance(payload, dict):
        raise LLMExtractionError(f'AWS Bedrock returned an unexpected response shape ({model_id})')

    raw_rows = payload.get('transactions', [])
    if not raw_rows:
        raise LLMExtractionError('AI could not find a transaction table in this file')

    transactions = [t for t in (normalize_extracted_row(row) for row in raw_rows) if t is not None]

    if not transactions:
        raise LLMExtractionError(f'AI-extracted rows were not in a usable format ({model_id})')

    return transactions


def extract_transactions_from_images(image_pages: List[bytes]) -> Tuple[List[Dict], bool]:
    """
    Ask a Bedrock model to extract transactions directly from rendered
    bank statement page images - Claude 3.5 Sonnet v2 first, falling back
    to Amazon Nova Lite if that fails for any reason (see module
    docstring).

    Unlike llm_extractor.extract_transactions_from_images() (same error
    type, but a plain list return), this returns a (transactions,
    used_fallback_model) tuple - Nova Lite is a much smaller model than
    Claude and, in testing, was observed to hallucinate a full fake
    transaction table from a blank test image rather than reliably
    reporting "no table found" the way Claude does. Callers should treat
    used_fallback_model=True as lower-confidence and warn accordingly
    rather than trusting the result silently.

    Raises:
        LLMExtractionError: if Bedrock isn't configured, no images were
        given, or both models failed - the error from the fallback model
        (Nova Lite), since it's the more informative one when the primary
        model failure was just the marketplace/payment issue.
    """
    if not is_configured():
        raise LLMExtractionError(
            'AWS Bedrock is not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.'
        )
    if not image_pages:
        raise LLMExtractionError('No page images were provided for vision-based extraction')

    content = [{"text": "Extract every transaction visible in these bank statement page images, in the order given:"}]
    for image_bytes in image_pages:
        content.append({"image": {"format": _IMAGE_FORMAT, "source": {"bytes": image_bytes}}})

    try:
        return _invoke(BEDROCK_MODEL_ID, content), False
    except LLMExtractionError as primary_error:
        if BEDROCK_FALLBACK_MODEL_ID == BEDROCK_MODEL_ID:
            raise
        try:
            return _invoke(BEDROCK_FALLBACK_MODEL_ID, content), True
        except LLMExtractionError as fallback_error:
            raise LLMExtractionError(
                f'{primary_error} Fallback model also failed: {fallback_error}'
            )
