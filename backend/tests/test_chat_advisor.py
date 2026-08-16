"""
Unit tests for the AI chatbot's generate half (services/chat_advisor.py).
Retrieval (_build_chat_context) is exercised via the Flask endpoint in
test_chat_endpoint.py; this file covers history sanitization and answer
generation in isolation. The provider itself (Ollama/Groq env-var
selection) is covered by test_ai_client.py - here, ai_client.is_configured()
and ai_client.get_client() are mocked directly so these tests don't
depend on env-var/module-reload mechanics, and never call a real model.
"""
from unittest.mock import MagicMock, patch

import pytest

from services import ai_client, chat_advisor
from services.chat_advisor import ChatAdvisorError, answer_question, sanitize_history

# Note: throughout this file "sent_messages[0]" is the system message,
# where both the retrieved financial context and the language instruction
# are embedded (see answer_question()).


class TestSanitizeHistory:
    def test_none_returns_empty_list(self):
        assert sanitize_history(None) == []

    def test_keeps_well_formed_turns(self):
        history = [
            {'role': 'user', 'content': 'How much did I spend?'},
            {'role': 'assistant', 'content': 'You spent 5000.'},
        ]
        assert sanitize_history(history) == history

    def test_drops_malformed_entries(self):
        history = [
            {'role': 'user', 'content': 'ok'},
            {'role': 'system', 'content': 'not allowed'},   # bad role
            {'role': 'assistant', 'content': ''},            # empty content
            {'role': 'user', 'content': 123},                 # non-string content
            'not even a dict',
            {'role': 'assistant', 'content': '  trimmed  '},
        ]
        cleaned = sanitize_history(history)
        assert cleaned == [
            {'role': 'user', 'content': 'ok'},
            {'role': 'assistant', 'content': 'trimmed'},
        ]

    def test_caps_history_length_and_message_length(self):
        long_history = [{'role': 'user', 'content': f'msg {i}'} for i in range(50)]
        cleaned = sanitize_history(long_history)
        assert len(cleaned) == chat_advisor.MAX_HISTORY_TURNS
        assert cleaned[-1]['content'] == 'msg 49'  # most recent turns kept

        huge_message = [{'role': 'user', 'content': 'x' * 10000}]
        cleaned_long = sanitize_history(huge_message)
        assert len(cleaned_long[0]['content']) == chat_advisor.MAX_MESSAGE_LENGTH


def _make_response(content, finish_reason='stop'):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    return response


_SAMPLE_CONTEXT = {
    'today': '2026-08-16',
    'current_month': {'spent': 12000, 'income': 50000, 'savings': 38000},
    'previous_month': {'spent': 15000, 'income': 50000, 'savings': 35000},
    'category_breakdown_this_month': [{'name': 'Groceries', 'amount': 5000}],
    'top_merchants_this_month': [],
    'budget_status': [],
    'goals': [],
    'recent_transactions': [],
}


def test_answer_question_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: False)
    with pytest.raises(ChatAdvisorError, match='not configured'):
        answer_question(_SAMPLE_CONTEXT, 'How much did I spend this month?')


def test_answer_question_returns_reply_text(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response('You spent ₹12,000 this month, down from ₹15,000 last month.')

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        reply = answer_question(_SAMPLE_CONTEXT, 'How much did I spend this month?')

    assert '12,000' in reply


def test_answer_question_passes_context_in_system_and_history_in_messages(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response('Sure thing.')
    history = [{'role': 'user', 'content': 'Hi'}, {'role': 'assistant', 'content': 'Hello!'}]

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_create = mock_get_client.return_value.chat.completions.create
        mock_create.return_value = mock_response
        answer_question(_SAMPLE_CONTEXT, 'Follow-up question', history=history)

    call_kwargs = mock_create.call_args.kwargs
    sent_messages = call_kwargs['messages']
    assert sent_messages[0]['role'] == 'system'
    assert 'Groceries' in sent_messages[0]['content']  # retrieved context is grounded in the system message
    assert sent_messages[1:] == history + [{'role': 'user', 'content': 'Follow-up question'}]


def test_answer_question_raises_on_content_filter(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response(None, finish_reason='content_filter')

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(ChatAdvisorError, match='declined'):
            answer_question(_SAMPLE_CONTEXT, 'anything')


def test_answer_question_raises_on_empty_reply(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response('   ')

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(ChatAdvisorError, match='no content'):
            answer_question(_SAMPLE_CONTEXT, 'anything')


def test_answer_question_wraps_connection_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = RuntimeError('connection refused')
        with pytest.raises(ChatAdvisorError, match='request failed'):
            answer_question(_SAMPLE_CONTEXT, 'anything')


def test_answer_question_wraps_provider_config_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client', side_effect=ai_client.AIProviderError('no GROQ_API_KEY set')):
        with pytest.raises(ChatAdvisorError, match='GROQ_API_KEY'):
            answer_question(_SAMPLE_CONTEXT, 'anything')


class TestLanguageSupport:
    def test_default_language_is_auto_detect_instruction(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response('ok')

        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            answer_question(_SAMPLE_CONTEXT, 'question')

        system_content = mock_create.call_args.kwargs['messages'][0]['content']
        assert 'Detect the language' in system_content

    def test_explicit_language_is_named_in_system_prompt(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response('ok')

        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            answer_question(_SAMPLE_CONTEXT, 'question', language='hi')

        system_content = mock_create.call_args.kwargs['messages'][0]['content']
        assert 'Hindi' in system_content

    def test_marathi_language_is_named_in_system_prompt(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response('ok')

        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            answer_question(_SAMPLE_CONTEXT, 'question', language='mr')

        system_content = mock_create.call_args.kwargs['messages'][0]['content']
        assert 'Marathi' in system_content

    def test_unrecognized_language_code_falls_back_to_auto_detect(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response('ok')

        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_create = mock_get_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            # answer_question() itself is defensive here - the endpoint is what
            # actually rejects unknown codes with a 400 (see test_chat_endpoint.py)
            answer_question(_SAMPLE_CONTEXT, 'question', language='xx-not-real')

        system_content = mock_create.call_args.kwargs['messages'][0]['content']
        assert 'Detect the language' in system_content

    def test_every_supported_language_produces_a_named_instruction(self):
        for code, label in chat_advisor.SUPPORTED_LANGUAGES.items():
            instruction = chat_advisor._language_instruction(code)
            if code == 'auto':
                assert 'Detect the language' in instruction
            else:
                assert label in instruction  # e.g. "Hindi"
