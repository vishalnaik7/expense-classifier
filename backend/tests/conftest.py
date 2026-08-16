"""
Shared pytest fixtures for the backend test suite.

The Flask app in main.py reads its database URL from the DATABASE_URL
environment variable at import time, so it must be set to an in-memory
SQLite database *before* main is imported.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['JWT_SECRET_KEY'] = 'test-secret-key'
# AI_PROVIDER defaults to "ollama" (see services/ai_client.py), which is
# always "configured" with no key needed - that's right for local dev,
# but would make the test suite try real network calls to localhost:11434
# for any AI codepath a test forgets to mock. Force it off by default here;
# individual tests opt back in explicitly via monkeypatch on is_configured()
# and a mocked ai_client.get_client(), never a real provider call.
os.environ['AI_PROVIDER'] = 'none'

import pytest

import main as main_module


@pytest.fixture()
def app():
    flask_app = main_module.app
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        main_module.init_db()  # creates tables and seeds default categories
        yield flask_app
        main_module.db.session.remove()
        main_module.db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    """Sign up a fresh user and return Authorization headers for it."""
    response = client.post('/api/auth/signup', json={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'Passw0rd!'
    })
    token = response.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}
