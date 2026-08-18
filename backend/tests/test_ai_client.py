"""Unit tests for the shared open-source-model provider abstraction (services/ai_client.py)."""
import importlib

import pytest

from services import ai_client


def _reload():
    """AI_PROVIDER is read at import time, so reload the module after changing env vars."""
    return importlib.reload(ai_client)


class TestOllamaProvider:
    def test_is_configured_true_with_no_key_needed(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'ollama')
        monkeypatch.delenv('GROQ_API_KEY', raising=False)
        mod = _reload()
        assert mod.is_configured() is True

    def test_default_base_url_and_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'ollama')
        monkeypatch.delenv('AI_BASE_URL', raising=False)
        monkeypatch.delenv('AI_MODEL', raising=False)
        mod = _reload()
        client = mod.get_client()
        assert str(client.base_url).rstrip('/') == 'http://localhost:11434/v1'
        assert mod.get_model() == 'llama3.1'

    def test_overrides_respected(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'ollama')
        monkeypatch.setenv('AI_BASE_URL', 'http://localhost:9999/v1')
        monkeypatch.setenv('AI_MODEL', 'mistral')
        mod = _reload()
        client = mod.get_client()
        assert str(client.base_url).rstrip('/') == 'http://localhost:9999/v1'
        assert mod.get_model() == 'mistral'

    def test_default_vision_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'ollama')
        monkeypatch.delenv('AI_VISION_MODEL', raising=False)
        mod = _reload()
        assert mod.get_vision_model() == 'llama3.2-vision'

    def test_vision_model_override(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'ollama')
        monkeypatch.setenv('AI_VISION_MODEL', 'llava')
        mod = _reload()
        assert mod.get_vision_model() == 'llava'


class TestGroqProvider:
    def test_not_configured_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.delenv('GROQ_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        assert mod.is_configured() is False

    def test_configured_with_groq_api_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        mod = _reload()
        assert mod.is_configured() is True

    def test_default_base_url_and_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        monkeypatch.delenv('AI_BASE_URL', raising=False)
        monkeypatch.delenv('AI_MODEL', raising=False)
        mod = _reload()
        client = mod.get_client()
        assert str(client.base_url).rstrip('/') == 'https://api.groq.com/openai/v1'
        assert mod.get_model() == 'openai/gpt-oss-120b'

    def test_get_client_raises_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.delenv('GROQ_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='GROQ_API_KEY'):
            mod.get_client()

    def test_default_vision_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        monkeypatch.delenv('AI_VISION_MODEL', raising=False)
        mod = _reload()
        assert mod.get_vision_model() == 'qwen/qwen3.6-27b'


class TestGeminiProvider:
    def test_not_configured_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'gemini')
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        assert mod.is_configured() is False

    def test_default_base_url_and_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'gemini')
        monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
        monkeypatch.delenv('AI_BASE_URL', raising=False)
        monkeypatch.delenv('AI_MODEL', raising=False)
        mod = _reload()
        client = mod.get_client()
        assert str(client.base_url).rstrip('/') == 'https://generativelanguage.googleapis.com/v1beta/openai'
        assert mod.get_model() == 'gemini-3.7-flash'
        assert mod.get_vision_model() == 'gemini-3.7-flash'

    def test_get_client_raises_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'gemini')
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='GEMINI_API_KEY'):
            mod.get_client()


class TestMistralProvider:
    def test_not_configured_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'mistral')
        monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        assert mod.is_configured() is False

    def test_default_base_url_and_model(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'mistral')
        monkeypatch.setenv('MISTRAL_API_KEY', 'test-key')
        monkeypatch.delenv('AI_BASE_URL', raising=False)
        monkeypatch.delenv('AI_MODEL', raising=False)
        mod = _reload()
        client = mod.get_client()
        assert str(client.base_url).rstrip('/') == 'https://api.mistral.ai/v1'
        assert mod.get_model() == 'mistral-large-latest'
        assert mod.get_vision_model() == 'mistral-large-latest'

    def test_get_client_raises_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'mistral')
        monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='MISTRAL_API_KEY'):
            mod.get_client()


class TestExplicitProviderFunctions:
    """
    The *_for(provider_name) variants let a caller try a specific
    provider explicitly, independent of whichever one AI_PROVIDER points
    at - used by a vision extraction fallback chain that tries several
    providers in turn regardless of the deployment's main AI_PROVIDER.
    """

    def test_is_configured_for_checks_the_named_providers_own_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)
        monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        assert mod.is_configured_for('groq') is True
        assert mod.is_configured_for('gemini') is False
        assert mod.is_configured_for('mistral') is False

        monkeypatch.setenv('MISTRAL_API_KEY', 'test-key')
        mod = _reload()
        assert mod.is_configured_for('mistral') is True

    def test_get_client_for_uses_the_named_providers_key_and_url(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        monkeypatch.setenv('MISTRAL_API_KEY', 'mistral-test-key')
        monkeypatch.delenv('AI_BASE_URL', raising=False)
        mod = _reload()

        client = mod.get_client_for('mistral')
        assert str(client.base_url).rstrip('/') == 'https://api.mistral.ai/v1'

    def test_get_client_for_raises_when_named_provider_has_no_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('GROQ_API_KEY', 'gsk-test-key')
        monkeypatch.delenv('GEMINI_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='GEMINI_API_KEY'):
            mod.get_client_for('gemini')

    def test_get_vision_model_for_returns_named_providers_default(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.delenv('AI_VISION_MODEL', raising=False)
        mod = _reload()
        assert mod.get_vision_model_for('mistral') == 'mistral-large-latest'
        assert mod.get_vision_model_for('gemini') == 'gemini-3.7-flash'
        # AI_VISION_MODEL only overrides the currently-active AI_PROVIDER,
        # not an explicitly-named other one.
        assert mod.get_vision_model_for('groq') == 'qwen/qwen3.6-27b'

    def test_ai_vision_model_override_applies_only_to_active_provider(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.setenv('AI_VISION_MODEL', 'custom-vision-model')
        mod = _reload()
        assert mod.get_vision_model_for('groq') == 'custom-vision-model'
        assert mod.get_vision_model_for('mistral') == 'mistral-large-latest'


class TestUnknownProvider:
    def test_is_configured_false_for_none(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'none')
        mod = _reload()
        assert mod.is_configured() is False

    def test_get_client_raises_for_unknown_provider(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'something-else')
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='Unknown provider'):
            mod.get_client()
