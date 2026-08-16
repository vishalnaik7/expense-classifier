"""
Integration tests for the AI chatbot endpoint (POST /api/chat): request
validation, the "not configured" 503, grounding in retrieved per-user
data, and strict isolation between users.
"""
import io
from datetime import datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

import main as main_module

MIXED_CSV = (
    b'Date,Description,Debit,Credit\n'
    b'2026-08-01,Salary Credit,,60000\n'
    b'2026-08-02,Grocery Shopping BigBasket,4500,\n'
)


def test_chat_requires_message(client, auth_headers):
    response = client.post('/api/chat', json={}, headers=auth_headers)
    assert response.status_code == 400


def test_chat_rejects_overlong_message(client, auth_headers):
    response = client.post('/api/chat', json={'message': 'x' * 3000}, headers=auth_headers)
    assert response.status_code == 400


def test_chat_returns_503_when_not_configured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: False)
    response = client.post('/api/chat', json={'message': 'How much did I spend this month?'}, headers=auth_headers)
    assert response.status_code == 503
    assert 'not configured' in response.get_json()['error'].lower()


def test_chat_returns_ai_reply_when_configured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)
    client.post('/api/uploads', data={'file': (io.BytesIO(MIXED_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='You spent ₹4,500 on groceries this month.'):
        response = client.post('/api/chat', json={'message': 'How much did I spend on groceries?'}, headers=auth_headers)

    assert response.status_code == 200
    assert 'groceries' in response.get_json()['data']['reply'].lower()


def test_chat_grounds_context_in_real_transaction_data(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)
    client.post('/api/uploads', data={'file': (io.BytesIO(MIXED_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        client.post('/api/chat', json={'message': 'Summarize my spending'}, headers=auth_headers)

    context_arg = mock_answer.call_args.args[0]
    assert context_arg['current_month']['spent'] == 4500.0
    assert context_arg['current_month']['income'] == 60000.0
    category_names = {c['name'] for c in context_arg['category_breakdown_this_month']}
    assert 'Groceries' in category_names


def test_chat_ai_failure_returns_502(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)

    with patch.object(
        main_module.chat_advisor, 'answer_question',
        side_effect=main_module.ChatAdvisorError('AI Assistant request failed: network down')
    ):
        response = client.post('/api/chat', json={'message': 'anything'}, headers=auth_headers)

    assert response.status_code == 502
    assert 'network down' in response.get_json()['error']


def test_chat_context_is_isolated_per_user(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)
    client.post('/api/uploads', data={'file': (io.BytesIO(MIXED_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    client.post('/api/auth/signup', json={'username': 'chatuser2', 'email': 'chatuser2@example.com', 'password': 'Passw0rd!'})
    token_b = client.post('/api/auth/login', json={'email': 'chatuser2@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        client.post('/api/chat', json={'message': 'Summarize my spending'}, headers={'Authorization': f'Bearer {token_b}'})

    context_arg = mock_answer.call_args.args[0]
    # user B has no transactions of their own - user A's spending must not leak in
    assert context_arg['current_month']['spent'] == 0
    assert context_arg['category_breakdown_this_month'] == []


def test_chat_passes_sanitized_history_through(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        client.post('/api/chat', json={
            'message': 'Follow up',
            'history': [
                {'role': 'user', 'content': 'Hi'},
                {'role': 'assistant', 'content': 'Hello!'},
                {'role': 'system', 'content': 'ignored - not a valid role'},
            ],
        }, headers=auth_headers)

    history_arg = mock_answer.call_args.args[2]
    assert history_arg == [{'role': 'user', 'content': 'Hi'}, {'role': 'assistant', 'content': 'Hello!'}]


def test_chat_context_includes_monthly_history_for_a_past_month(client, auth_headers, monkeypatch):
    # Regression test: chat used to only see current+previous month, so a
    # question about an older month ("how much did I spend in May?") had no
    # data to answer from and the model would guess/hallucinate from
    # unrelated transactions. monthly_history now covers up to 12 months.
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)
    three_months_ago = datetime.utcnow().date() - relativedelta(months=3)
    old_month_label = three_months_ago.strftime('%b %Y')
    old_csv = (
        b'Date,Description,Debit,Credit\n'
        + f'{three_months_ago.isoformat()},Uber Travel Booking,782,\n'.encode()
    )
    client.post('/api/uploads', data={'file': (io.BytesIO(old_csv), 'old_statement.csv')}, headers=auth_headers, content_type='multipart/form-data')

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        client.post('/api/chat', json={'message': f'How much did I spend in {old_month_label}?'}, headers=auth_headers)

    context_arg = mock_answer.call_args.args[0]
    months = {m['month']: m for m in context_arg['monthly_history']}
    assert old_month_label in months
    assert months[old_month_label]['spending'] == 782.0
    category_names = {c['name'] for c in months[old_month_label]['category_breakdown']}
    assert 'Transport' in category_names


def test_chat_languages_endpoint_lists_supported_codes(client, auth_headers):
    response = client.get('/api/chat/languages', headers=auth_headers)
    assert response.status_code == 200
    codes = {row['code'] for row in response.get_json()['data']}
    assert {'auto', 'en', 'hi', 'mr', 'ta', 'te', 'bn', 'gu', 'kn', 'ml', 'pa'} == codes


def test_chat_defaults_to_auto_language(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        response = client.post('/api/chat', json={'message': 'hello'}, headers=auth_headers)

    assert mock_answer.call_args.kwargs['language'] == 'auto'
    assert response.get_json()['data']['language'] == 'auto'


def test_chat_passes_explicit_language_through(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)

    with patch.object(main_module.chat_advisor, 'answer_question', return_value='ok') as mock_answer:
        response = client.post('/api/chat', json={'message': 'kitna kharch hua?', 'language': 'hi'}, headers=auth_headers)

    assert response.status_code == 200
    assert mock_answer.call_args.kwargs['language'] == 'hi'
    assert response.get_json()['data']['language'] == 'hi'


def test_chat_rejects_unsupported_language_code(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module.chat_advisor, 'is_configured', lambda: True)
    response = client.post('/api/chat', json={'message': 'hello', 'language': 'fr'}, headers=auth_headers)
    assert response.status_code == 400
    assert 'language' in response.get_json()['error'].lower()
