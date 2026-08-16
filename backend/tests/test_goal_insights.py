"""
Integration tests for the retrieval-augmented goal-insight endpoint
(GET /api/goals/<id>/insights): the SQL-based retrieval in
_build_goal_context, the always-available math projection, and the
optional AI advice generation on top of it.
"""
import io
from datetime import datetime
from unittest.mock import patch

import pytest

import main as main_module

# The app consistently defines "today" as datetime.utcnow().date() (see
# _current_month_range/_build_goal_context in main.py), which can differ
# from the local machine's date.today() near a UTC day boundary (e.g. late
# night in IST) - match that definition here so fixtures land in-window.
TODAY = datetime.utcnow().date().strftime('%Y-%m-%d')

MIXED_CSV = (
    b'Date,Description,Debit,Credit\n'
    + f'{TODAY},Salary Credit,,60000\n'.encode()
    + f'{TODAY},Grocery Shopping BigBasket,20000,\n'.encode()
)


def _create_goal(client, headers, target_amount=120000, current_amount=0, target_date=None):
    payload = {'name': 'Emergency Fund', 'target_amount': target_amount, 'current_amount': current_amount}
    if target_date:
        payload['target_date'] = target_date
    return client.post('/api/goals', json=payload, headers=headers).get_json()['data']['id']


def test_insights_404_for_goal_you_do_not_own(client, auth_headers, monkeypatch):
    goal_id = _create_goal(client, auth_headers)

    client.post('/api/auth/signup', json={'username': 'other5', 'email': 'other5@example.com', 'password': 'Passw0rd!'})
    token_b = client.post('/api/auth/login', json={'email': 'other5@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

    response = client.get(f'/api/goals/{goal_id}/insights', headers={'Authorization': f'Bearer {token_b}'})
    assert response.status_code == 404


def test_insights_without_any_transactions_is_not_feasible_but_does_not_error(client, auth_headers, monkeypatch):
    goal_id = _create_goal(client, auth_headers)

    response = client.get(f'/api/goals/{goal_id}/insights', headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['projection']['feasible'] is False
    assert data['projection']['realistic'] is None
    assert data['context']['avg_monthly_savings'] == 0
    assert data['context']['history_months_analyzed'] == 0
    assert data['ai_available'] is False
    assert data['ai_advice'] is None


def test_insights_projection_reflects_real_spending(client, auth_headers, monkeypatch):
    goal_id = _create_goal(client, auth_headers, target_amount=120000)

    client.post('/api/uploads', data={'file': (io.BytesIO(MIXED_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    response = client.get(f'/api/goals/{goal_id}/insights', headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()['data']

    # 60000 income - 20000 spend = 40000 net for the one month with data
    assert data['context']['avg_monthly_savings'] == 40000.0
    assert data['context']['savings_rate_percent'] == pytest.approx(66.7, abs=0.1)
    # 120000 remaining / 40000 per month = 3 months, rounded up
    assert data['projection']['realistic']['months_needed'] == 3
    assert data['projection']['feasible'] is True
    # only one month of history -> zero volatility -> all three bands agree
    assert data['projection']['optimistic']['months_needed'] == 3
    assert data['projection']['pessimistic']['months_needed'] == 3

    category = next(c for c in data['context']['top_spending_categories'] if c['name'] == 'Groceries')
    assert category['spend_type'] == 'essential'


def test_insights_reports_combined_requirement_across_goals(client, auth_headers, monkeypatch):
    from dateutil.relativedelta import relativedelta
    two_months_out = (datetime.utcnow().date() + relativedelta(months=2)).strftime('%Y-%m-%d')

    goal_id = _create_goal(client, auth_headers, target_amount=50000, target_date=two_months_out)
    _create_goal(client, auth_headers, target_amount=30000, target_date=two_months_out)  # a second competing goal

    response = client.get(f'/api/goals/{goal_id}/insights', headers=auth_headers)
    data = response.get_json()['data']

    assert len(data['context']['other_active_goals']) == 1
    # this goal needs 50000/2=25000/mo, the other needs 30000/2=15000/mo -> combined 40000/mo
    assert data['context']['goal']['monthly_required_for_target_date'] == 25000.0
    assert data['context']['other_active_goals'][0]['monthly_required'] == 15000.0
    assert data['context']['combined_monthly_required_across_goals'] == 40000.0


def test_insights_isolated_per_user(client, auth_headers):
    goal_id = _create_goal(client, auth_headers)
    client.post('/api/uploads', data={'file': (io.BytesIO(MIXED_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    client.post('/api/auth/signup', json={'username': 'other6', 'email': 'other6@example.com', 'password': 'Passw0rd!'})
    token_b = client.post('/api/auth/login', json={'email': 'other6@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']
    goal_id_b = _create_goal(client, {'Authorization': f'Bearer {token_b}'})

    response = client.get(f'/api/goals/{goal_id_b}/insights', headers={'Authorization': f'Bearer {token_b}'})
    data = response.get_json()['data']
    # user B has no transactions of their own - user A's spending must not leak in
    assert data['context']['avg_monthly_savings'] == 0
    assert data['context']['top_spending_categories'] == []


def test_insights_includes_ai_advice_when_configured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.goal_advisor, 'is_configured', lambda: True)
    goal_id = _create_goal(client, auth_headers)

    fake_advice = {'summary': 'Looking solid.', 'tips': ['Trim dining out'], 'suggested_monthly_savings': None}
    with patch.object(main_module.goal_advisor, 'generate_insight', return_value=fake_advice):
        response = client.get(f'/api/goals/{goal_id}/insights', headers=auth_headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['ai_available'] is True
    assert data['ai_advice'] == fake_advice
    assert data['ai_error'] is None


def test_insights_ai_failure_still_returns_math_projection(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.goal_advisor, 'is_configured', lambda: True)
    goal_id = _create_goal(client, auth_headers)

    with patch.object(
        main_module.goal_advisor, 'generate_insight',
        side_effect=main_module.GoalInsightError('AI advice request failed: network down')
    ):
        response = client.get(f'/api/goals/{goal_id}/insights', headers=auth_headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['ai_advice'] is None
    assert 'network down' in data['ai_error']
    assert data['projection'] is not None  # deterministic half of the pipeline is unaffected
