"""
Shared open-source-model client for every AI-powered feature in this app
(chat_advisor, goal_advisor, llm_extractor) - no Anthropic/OpenAI paid API
involved anywhere.

Local development: AI_PROVIDER defaults to "ollama", talking to a local
Ollama server (`ollama serve`, default http://localhost:11434) running an
open-source model you've pulled (e.g. `ollama pull llama3.1`). Free, fully
local, no API key required - Ollama exposes an OpenAI-compatible endpoint
at /v1, which is what this module talks to.

Production: Ollama cannot be deployed to a serverless/static host like
Vercel or GitHub Pages - it's a long-running process that keeps multi-GB
model weights resident in memory and needs persistent disk, none of which
those platforms provide. Instead, set AI_PROVIDER=groq and GROQ_API_KEY:
Groq hosts the same class of open-source models (Llama 3.x, etc.) behind
a free-tier, OpenAI-compatible API with very fast inference.

Because Ollama and Groq both implement the OpenAI chat-completions wire
format, the rest of the app never needs to know which one is active -
only AI_PROVIDER/AI_BASE_URL/AI_API_KEY/AI_MODEL change between
environments, via get_client()/get_model() below. Structured extraction
(llm_extractor, goal_advisor) uses response_format={"type": "json_object"}
(JSON mode) rather than strict schema-constrained decoding, since JSON
mode is the one structured-output feature reliably supported across
Ollama, Groq, and small open-source models alike - the schema itself is
described in the prompt and the response is validated/normalized in
Python after parsing, same as before.
"""
import os
from typing import Optional

from openai import OpenAI

AI_PROVIDER = os.getenv('AI_PROVIDER', 'ollama').strip().lower()

_PROVIDER_DEFAULTS = {
    'ollama': {
        'base_url': 'http://localhost:11434/v1',
        'model': 'llama3.1',
        # Ollama's vision-capable models are separate pulls from the text
        # model above - e.g. `ollama pull llama3.2-vision`. Verify against
        # https://ollama.com/library before relying on this default, since
        # the exact tag naming can change.
        'vision_model': 'llama3.2-vision',
    },
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'model': 'openai/gpt-oss-120b',
        # Groq's model lineup changes fairly often, including full
        # decommissions of models still referenced elsewhere in their own
        # docs - verify the current name at
        # https://console.groq.com/docs/models (or /docs/vision for
        # multimodal models) and override via AI_MODEL/AI_VISION_MODEL if
        # this default has been retired.
        'vision_model': 'qwen/qwen3.6-27b',
    },
}


class AIProviderError(Exception):
    """Raised for AI_PROVIDER configuration problems (unknown provider, missing key)."""
    pass


def is_configured() -> bool:
    """
    Whether the active provider is ready to be called.

    Ollama needs no API key - a locally running server is all that's
    required, and if it isn't actually running, that surfaces as a clear
    connection error at call time rather than a static "not configured"
    check here. A hosted provider like Groq does need a real key.
    """
    if AI_PROVIDER == 'none':
        return False
    if AI_PROVIDER == 'ollama':
        return True
    if AI_PROVIDER == 'groq':
        return bool(os.getenv('GROQ_API_KEY') or os.getenv('AI_API_KEY'))
    return False


def get_model() -> str:
    """The text model name to pass to chat.completions.create, overridable via AI_MODEL."""
    default = _PROVIDER_DEFAULTS.get(AI_PROVIDER, {}).get('model', 'llama3.1')
    return os.getenv('AI_MODEL', default)


def get_vision_model() -> str:
    """
    The vision-capable model name for image-based extraction (e.g. a bank
    statement PDF with no extractable text layer - see
    services/pdf_parser.py's render_pages_as_images()). Separate from
    get_model(): most fast/cheap text models are not multimodal, so this
    is deliberately a different model, overridable via AI_VISION_MODEL.
    """
    default = _PROVIDER_DEFAULTS.get(AI_PROVIDER, {}).get('vision_model', 'llama3.2-vision')
    return os.getenv('AI_VISION_MODEL', default)


def get_client() -> OpenAI:
    """
    An OpenAI-compatible client pointed at whichever provider AI_PROVIDER
    selects. Every AI service module in this app should get its client
    through this function instead of constructing one directly, so
    switching providers is a config change, not a code change.
    """
    if AI_PROVIDER == 'ollama':
        base_url = os.getenv('AI_BASE_URL', _PROVIDER_DEFAULTS['ollama']['base_url'])
        return OpenAI(base_url=base_url, api_key='ollama')  # Ollama ignores the key; the SDK requires a non-empty string

    if AI_PROVIDER == 'groq':
        api_key = os.getenv('GROQ_API_KEY') or os.getenv('AI_API_KEY')
        if not api_key:
            raise AIProviderError('AI_PROVIDER=groq but no GROQ_API_KEY (or AI_API_KEY) is set')
        base_url = os.getenv('AI_BASE_URL', _PROVIDER_DEFAULTS['groq']['base_url'])
        return OpenAI(base_url=base_url, api_key=api_key)

    raise AIProviderError(
        f'Unknown AI_PROVIDER "{AI_PROVIDER}" - expected "ollama" or "groq" (or "none" to disable AI features)'
    )


def connection_hint(error: Exception) -> Optional[str]:
    """A friendlier hint appended to raw connection errors, based on the active provider."""
    if AI_PROVIDER == 'ollama':
        return 'Is Ollama running locally? Start it with `ollama serve` and make sure the model is pulled (`ollama pull llama3.1`).'
    if AI_PROVIDER == 'groq':
        return 'Check that GROQ_API_KEY is valid and Groq is reachable.'
    return None
