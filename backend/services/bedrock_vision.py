"""
AWS Bedrock (Claude) vision extraction for bank statement PDFs with no
extractable text layer. Used specifically for this one fallback tier -
every other AI feature in the app (chat, goal advice, text-based
extraction) still goes through services/ai_client.py's Ollama/Groq/
Gemini/Mistral abstraction; this module is a separate, narrower path for
image-based PDF extraction only, using the Bedrock Converse API (boto3's
bedrock-runtime client) with Claude 3.5 Sonnet v2 instead.

Credentials are picked up by boto3's standard chain (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY env vars, or an EC2 instance role) - never handled
directly in this module.

Region note: in ap-south-1 (Mumbai), Anthropic models on Bedrock require
a cross-region inference profile ID rather than the bare model ID for
on-demand invocation (confirmed via `aws bedrock list-inference-profiles`
- the bare `anthropic.claude-3-5-sonnet-20241022-v2:0` model ID is listed
but not directly invocable on-demand in this region). Override
BEDROCK_MODEL_ID/AWS_REGION if deploying from a region where this
differs.
"""
import json
import os
from typing import Dict, List

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


def extract_transactions_from_images(image_pages: List[bytes]) -> List[Dict]:
    """
    Ask Claude (via Bedrock's Converse API) to extract transactions
    directly from rendered bank statement page images. Same return shape
    and error type as llm_extractor.extract_transactions_from_images(),
    which this replaces for the vision fallback specifically.

    Raises:
        LLMExtractionError: if Bedrock isn't configured, no images were
        given, the request fails, the model declines, or no usable
        transactions come back.
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
        response = _client().converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": _system_prompt()}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": _MAX_TOKENS},
        )
    except (BotoCoreError, ClientError) as e:
        raise LLMExtractionError(f'AWS Bedrock request failed: {e}')

    stop_reason = response.get('stopReason')
    if stop_reason in ('content_filtered', 'guardrail_intervened'):
        raise LLMExtractionError('AWS Bedrock declined to process this file')

    text_block = ''.join(
        block['text'] for block in response.get('output', {}).get('message', {}).get('content', [])
        if 'text' in block
    ).strip()
    if not text_block:
        raise LLMExtractionError('AWS Bedrock returned no extractable content')

    try:
        payload = json.loads(text_block)
    except json.JSONDecodeError as e:
        raise LLMExtractionError(f'AWS Bedrock returned malformed JSON: {e}')

    if not isinstance(payload, dict):
        raise LLMExtractionError('AWS Bedrock returned an unexpected response shape')

    raw_rows = payload.get('transactions', [])
    if not raw_rows:
        raise LLMExtractionError('AI could not find a transaction table in this file')

    transactions = [t for t in (normalize_extracted_row(row) for row in raw_rows) if t is not None]

    if not transactions:
        raise LLMExtractionError('AI-extracted rows were not in a usable format')

    return transactions
