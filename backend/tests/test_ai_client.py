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
        assert mod.get_model() == 'llama-3.3-70b-versatile'

    def test_get_client_raises_without_key(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'groq')
        monkeypatch.delenv('GROQ_API_KEY', raising=False)
        monkeypatch.delenv('AI_API_KEY', raising=False)
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='GROQ_API_KEY'):
            mod.get_client()


class TestUnknownProvider:
    def test_is_configured_false_for_none(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'none')
        mod = _reload()
        assert mod.is_configured() is False

    def test_get_client_raises_for_unknown_provider(self, monkeypatch):
        monkeypatch.setenv('AI_PROVIDER', 'something-else')
        mod = _reload()
        with pytest.raises(mod.AIProviderError, match='Unknown AI_PROVIDER'):
            mod.get_client()
