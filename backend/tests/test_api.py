"""Integration tests for the Flask API, exercised through the test client."""
import io
from unittest.mock import patch

import main as main_module

SAMPLE_CSV = (
    b'Date,Description,Amount\n'
    b'2024-01-15,Grocery Shopping BigBasket,1500\n'
    b'2024-01-16,Electricity Bill,2000\n'
    b'2024-01-17,Uber Ride,450\n'
)


def _upload(client, headers, content=SAMPLE_CSV, filename='statement.csv'):
    return client.post(
        '/api/uploads',
        data={'file': (io.BytesIO(content), filename)},
        headers=headers,
        content_type='multipart/form-data'
    )


class TestHealthCheck:
    def test_health_check_is_unauthenticated_and_reports_ok(self, client):
        response = client.get('/api/health')
        assert response.status_code == 200
        body = response.get_json()
        assert body['success'] is True
        assert body['data']['status'] == 'ok'
        assert body['data']['database'] == 'ok'


class TestAuth:
    def test_signup_creates_user_and_returns_tokens(self, client):
        response = client.post('/api/auth/signup', json={
            'username': 'alice', 'email': 'alice@example.com', 'password': 'Passw0rd!'
        })
        body = response.get_json()
        assert response.status_code == 201
        assert body['success'] is True
        assert 'access_token' in body['data']

    def test_duplicate_email_rejected(self, client):
        client.post('/api/auth/signup', json={
            'username': 'bob', 'email': 'bob@example.com', 'password': 'Passw0rd!'
        })
        response = client.post('/api/auth/signup', json={
            'username': 'bob2', 'email': 'bob@example.com', 'password': 'Passw0rd!'
        })
        assert response.status_code == 409

    def test_login_with_wrong_password_rejected(self, client):
        client.post('/api/auth/signup', json={
            'username': 'carol', 'email': 'carol@example.com', 'password': 'Passw0rd!'
        })
        response = client.post('/api/auth/login', json={
            'email': 'carol@example.com', 'password': 'WrongPassword!'
        })
        assert response.status_code == 401

    def test_protected_route_requires_token(self, client):
        response = client.get('/api/transactions')
        assert response.status_code == 401


class TestUpload:
    def test_upload_parses_and_categorizes(self, client, auth_headers):
        response = _upload(client, auth_headers)
        body = response.get_json()

        assert response.status_code == 201
        assert body['data']['inserted'] == 3
        assert body['data']['upload']['status'] == 'completed'

    def test_duplicate_upload_is_skipped(self, client, auth_headers):
        _upload(client, auth_headers)
        response = _upload(client, auth_headers)
        body = response.get_json()

        assert response.status_code == 201
        assert body['data']['inserted'] == 0
        assert body['data']['duplicates_skipped'] == 3

    def test_malformed_csv_returns_422(self, client, auth_headers):
        response = _upload(client, auth_headers, content=b'not,a,valid,file\n1,2\n', filename='bad.csv')
        assert response.status_code == 422
        assert response.get_json()['success'] is False

    def test_empty_file_rejected(self, client, auth_headers):
        response = _upload(client, auth_headers, content=b'', filename='empty.csv')
        assert response.status_code == 400

    def test_non_csv_extension_rejected(self, client, auth_headers):
        response = _upload(client, auth_headers, content=b'hello', filename='statement.txt')
        assert response.status_code == 400

    def test_upload_requires_authentication(self, client):
        response = client.post(
            '/api/uploads', data={'file': (io.BytesIO(SAMPLE_CSV), 'statement.csv')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 401

    def test_uploads_list_reflects_history(self, client, auth_headers):
        _upload(client, auth_headers)
        response = client.get('/api/uploads', headers=auth_headers)
        assert response.status_code == 200
        assert len(response.get_json()['data']) == 1

    def test_malformed_csv_without_ai_fallback_configured_returns_original_error(self, client, auth_headers, monkeypatch):
        # Test env defaults AI_PROVIDER=none (see conftest.py) - the endpoint
        # must degrade gracefully to the deterministic error, unchanged.
        monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: False)
        response = _upload(client, auth_headers, content=b'not,a,valid,file\n1,2\n', filename='bad.csv')
        assert response.status_code == 422
        body = response.get_json()
        assert body['success'] is False
        assert 'ai_fallback_error' not in body

    def test_ai_fallback_used_when_deterministic_parser_fails(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)
        fake_transactions = [{
            'date': '2026-06-01',
            'description': 'AI extracted transaction',
            'amount': 999.0,
            'type': 'debit',
            'hash': 'fakehash123',
            'raw_amount': 999.0,
        }]

        with patch.object(main_module.llm_extractor, 'extract_transactions', return_value=fake_transactions):
            response = _upload(client, auth_headers, content=b'totally,unparseable\n1,2\n', filename='messy.csv')

        assert response.status_code == 201
        body = response.get_json()
        assert body['data']['inserted'] == 1
        assert body['data']['used_ai_fallback'] is True

        history = client.get('/api/uploads', headers=auth_headers).get_json()['data']
        assert history[0]['status'] == 'completed'
        assert 'AI-assisted' in history[0]['error_message']

    def test_ai_fallback_failure_reports_both_errors(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(main_module.llm_extractor, 'is_configured', lambda: True)

        with patch.object(
            main_module.llm_extractor, 'extract_transactions',
            side_effect=main_module.LLMExtractionError('AI could not find a transaction table in this file')
        ):
            response = _upload(client, auth_headers, content=b'totally,unparseable\n1,2\n', filename='messy.csv')

        assert response.status_code == 422
        body = response.get_json()
        assert body['success'] is False
        assert 'ai_fallback_error' in body


class TestDataIsolation:
    def test_users_cannot_see_each_others_transactions(self, client):
        client.post('/api/auth/signup', json={'username': 'userA', 'email': 'a@example.com', 'password': 'Passw0rd!'})
        token_a = client.post('/api/auth/login', json={'email': 'a@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        client.post('/api/auth/signup', json={'username': 'userB', 'email': 'b@example.com', 'password': 'Passw0rd!'})
        token_b = client.post('/api/auth/login', json={'email': 'b@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        _upload(client, {'Authorization': f'Bearer {token_a}'})

        response_a = client.get('/api/transactions', headers={'Authorization': f'Bearer {token_a}'})
        response_b = client.get('/api/transactions', headers={'Authorization': f'Bearer {token_b}'})

        assert len(response_a.get_json()['data']) == 3
        assert len(response_b.get_json()['data']) == 0


class TestAnalyticsAndExport:
    def test_summary_reflects_uploaded_transactions(self, client, auth_headers):
        _upload(client, auth_headers)
        response = client.get('/api/analytics/summary', headers=auth_headers)
        body = response.get_json()['data']

        assert response.status_code == 200
        assert body['totalTransactions'] == 3
        assert body['totalSpent'] == 3950.0
        assert len(body['categoryBreakdown']) > 0

    def test_summary_with_bad_date_returns_400(self, client, auth_headers):
        response = client.get('/api/analytics/summary?date_from=not-a-date', headers=auth_headers)
        assert response.status_code == 400

    def test_export_csv_downloads_file(self, client, auth_headers):
        _upload(client, auth_headers)
        response = client.get('/api/export/csv', headers=auth_headers)
        assert response.status_code == 200
        assert response.content_type.startswith('text/csv')
        assert b'Grocery Shopping BigBasket' in response.data

    def test_export_pdf_downloads_file(self, client, auth_headers):
        _upload(client, auth_headers)
        response = client.get('/api/export/pdf', headers=auth_headers)
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data[:4] == b'%PDF'
