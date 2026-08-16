"""
Unit tests for the goal-insight RAG pipeline's generate/augment half.
Retrieval (_build_goal_context) is exercised via the Flask endpoint in
test_goal_insights.py; this file covers the pure-math projection and the
AI advice generation in isolation. The provider itself (Ollama/Groq
env-var selection) is covered by test_ai_client.py - here,
ai_client.is_configured()/get_client() are mocked directly, and no real
model is ever called.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services import ai_client, goal_advisor
from services.goal_advisor import GoalInsightError, generate_insight, is_configured, project_completion


def test_not_configured_delegates_to_ai_client(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: False)
    assert is_configured() is False


def test_configured_delegates_to_ai_client(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    assert is_configured() is True


class TestProjectCompletion:
    def test_goal_already_reached(self):
        result = project_completion(remaining_amount=0, avg_monthly_savings=500, savings_volatility=100, target_date_iso=None)
        assert result['feasible'] is True
        assert result['on_track'] is True
        for band in ('realistic', 'optimistic', 'pessimistic'):
            assert result[band]['months_needed'] == 0

    def test_negative_or_zero_savings_rate_is_not_feasible(self):
        result = project_completion(remaining_amount=10000, avg_monthly_savings=0, savings_volatility=0, target_date_iso=None)
        assert result['feasible'] is False
        assert result['realistic'] is None
        assert result['on_track'] is None

        result_negative = project_completion(remaining_amount=10000, avg_monthly_savings=-200, savings_volatility=0, target_date_iso=None)
        assert result_negative['feasible'] is False

    def test_computes_months_needed_and_rounds_up(self):
        # 10000 remaining / 3000 per month = 3.33 -> rounds up to 4 months
        result = project_completion(remaining_amount=10000, avg_monthly_savings=3000, savings_volatility=0, target_date_iso=None)
        assert result['realistic']['months_needed'] == 4
        assert result['feasible'] is True
        assert result['realistic']['projected_completion_date'] is not None

    def test_volatility_widens_optimistic_and_pessimistic_bands(self):
        # realistic uses 3000/mo (4 months); optimistic uses 3000+1000=4000/mo (3 months);
        # pessimistic uses 3000-1000=2000/mo (5 months)
        result = project_completion(remaining_amount=10000, avg_monthly_savings=3000, savings_volatility=1000, target_date_iso=None)
        assert result['realistic']['months_needed'] == 4
        assert result['optimistic']['months_needed'] == 3
        assert result['pessimistic']['months_needed'] == 5

    def test_pessimistic_band_is_none_when_volatility_would_make_it_negative(self):
        # 3000 avg - 5000 volatility = negative rate -> no pessimistic estimate is possible
        result = project_completion(remaining_amount=10000, avg_monthly_savings=3000, savings_volatility=5000, target_date_iso=None)
        assert result['pessimistic'] is None
        assert result['realistic'] is not None  # the realistic band is unaffected

    def test_on_track_when_projection_beats_target_date(self):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        far_future = (date.today() + relativedelta(years=5)).isoformat()
        result = project_completion(remaining_amount=1000, avg_monthly_savings=1000, savings_volatility=0, target_date_iso=far_future)
        assert result['on_track'] is True

    def test_not_on_track_when_target_date_is_too_soon(self):
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        result = project_completion(remaining_amount=100000, avg_monthly_savings=1000, savings_volatility=0, target_date_iso=tomorrow)
        assert result['on_track'] is False


def _make_response(payload, finish_reason='stop'):
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    return response


_SAMPLE_CONTEXT = {
    'goal': {'name': 'Emergency Fund', 'target_amount': 100000, 'current_amount': 20000, 'remaining': 80000, 'target_date': None, 'monthly_required_for_target_date': None},
    'history_months_analyzed': 1,
    'monthly_history': [{'month': 'Jul 2026', 'income': 50000, 'spending': 30000, 'net_savings': 20000}],
    'avg_monthly_income': 50000,
    'avg_monthly_savings': 20000,
    'savings_rate_percent': 40.0,
    'savings_volatility': 0.0,
    'savings_trend': None,
    'top_spending_categories': [{'name': 'Groceries', 'amount': 15000, 'spend_type': 'essential', 'trend': None}],
    'budget_status': [],
    'other_active_goals': [],
    'combined_monthly_required_across_goals': None,
}


def test_generate_insight_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: False)
    with pytest.raises(GoalInsightError, match='not configured'):
        generate_insight(_SAMPLE_CONTEXT)


def test_generate_insight_returns_parsed_advice(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response({
        'summary': 'You are saving well and on pace for this goal.',
        'tips': ['Cut Groceries spend by 10%', 'Automate a monthly transfer'],
        'suggested_monthly_savings': None,
        'goal_priority_note': None,
    })

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        advice = generate_insight(_SAMPLE_CONTEXT)

    assert advice['summary'].startswith('You are saving well')
    assert len(advice['tips']) == 2


def test_generate_insight_requests_json_mode(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response({
        'summary': 'ok', 'tips': ['tip one'], 'suggested_monthly_savings': None, 'goal_priority_note': None,
    })

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_create = mock_get_client.return_value.chat.completions.create
        mock_create.return_value = mock_response
        generate_insight(_SAMPLE_CONTEXT)

    assert mock_create.call_args.kwargs['response_format'] == {'type': 'json_object'}


def test_generate_insight_raises_on_content_filter(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
    mock_response = _make_response({}, finish_reason='content_filter')

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.return_value = mock_response
        with pytest.raises(GoalInsightError, match='declined'):
            generate_insight(_SAMPLE_CONTEXT)


def test_generate_insight_wraps_connection_errors(monkeypatch):
    monkeypatch.setattr(ai_client, 'is_configured', lambda: True)

    with patch.object(ai_client, 'get_client') as mock_get_client:
        mock_get_client.return_value.chat.completions.create.side_effect = RuntimeError('network down')
        with pytest.raises(GoalInsightError, match='request failed'):
            generate_insight(_SAMPLE_CONTEXT)


class TestNormalizeInsight:
    def test_rejects_missing_summary(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response({'tips': ['a tip'], 'suggested_monthly_savings': None, 'goal_priority_note': None})
        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_get_client.return_value.chat.completions.create.return_value = mock_response
            with pytest.raises(GoalInsightError, match='summary'):
                generate_insight(_SAMPLE_CONTEXT)

    def test_rejects_missing_tips(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response({'summary': 'ok', 'suggested_monthly_savings': None, 'goal_priority_note': None})
        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_get_client.return_value.chat.completions.create.return_value = mock_response
            with pytest.raises(GoalInsightError, match='tips'):
                generate_insight(_SAMPLE_CONTEXT)

    def test_caps_tips_at_five_and_coerces_optional_fields(self, monkeypatch):
        monkeypatch.setattr(ai_client, 'is_configured', lambda: True)
        mock_response = _make_response({
            'summary': 'ok',
            'tips': [f'tip {i}' for i in range(8)],
            'suggested_monthly_savings': '5000',  # wrong type from a sloppier open-source model
            'goal_priority_note': '   ',            # blank -> should become None
        })
        with patch.object(ai_client, 'get_client') as mock_get_client:
            mock_get_client.return_value.chat.completions.create.return_value = mock_response
            advice = generate_insight(_SAMPLE_CONTEXT)

        assert len(advice['tips']) == 5
        assert advice['suggested_monthly_savings'] is None  # non-numeric type is dropped, not coerced
        assert advice['goal_priority_note'] is None
