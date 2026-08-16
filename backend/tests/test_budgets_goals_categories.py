"""Integration tests for categories CRUD, budgets, goals, and the enriched analytics summary."""
import io


SAMPLE_CSV = (
    b'Date,Description,Amount\n'
    b'2024-01-15,Grocery Shopping BigBasket,1500\n'
    b'2024-01-16,Electricity Bill,2000\n'
)


def _get_category_id(client, headers, name):
    response = client.get('/api/categories', headers=headers)
    for cat in response.get_json()['data']:
        if cat['name'] == name:
            return cat['id']
    raise AssertionError(f'Category "{name}" not found in seeded categories')


class TestCategories:
    def test_default_categories_include_transfer_and_salary(self, client, auth_headers):
        response = client.get('/api/categories', headers=auth_headers)
        names = {c['name'] for c in response.get_json()['data']}
        assert 'Transfer' in names
        assert 'Salary' in names
        assert all(c['is_custom'] is False for c in response.get_json()['data'])

    def test_create_custom_category(self, client, auth_headers):
        response = client.post('/api/categories', json={'name': 'Pet Care', 'icon': '🐾', 'color': '#f97316'}, headers=auth_headers)
        assert response.status_code == 201
        body = response.get_json()['data']
        assert body['name'] == 'Pet Care'
        assert body['is_custom'] is True

    def test_duplicate_category_name_rejected(self, client, auth_headers):
        client.post('/api/categories', json={'name': 'Pet Care'}, headers=auth_headers)
        response = client.post('/api/categories', json={'name': 'Pet Care'}, headers=auth_headers)
        assert response.status_code == 409

    def test_cannot_edit_shared_category(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        response = client.put(f'/api/categories/{groceries_id}', json={'name': 'Hacked'}, headers=auth_headers)
        assert response.status_code == 404

    def test_edit_own_custom_category(self, client, auth_headers):
        create = client.post('/api/categories', json={'name': 'Pet Care'}, headers=auth_headers)
        category_id = create.get_json()['data']['id']
        response = client.put(f'/api/categories/{category_id}', json={'name': 'Pet Expenses'}, headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()['data']['name'] == 'Pet Expenses'

    def test_delete_custom_category_reassigns_transactions_to_other(self, client, auth_headers):
        create = client.post('/api/categories', json={'name': 'Pet Care'}, headers=auth_headers)
        category_id = create.get_json()['data']['id']

        client.post('/api/uploads', data={'file': (io.BytesIO(SAMPLE_CSV), 'statement.csv')}, headers=auth_headers, content_type='multipart/form-data')
        txns = client.get('/api/transactions', headers=auth_headers).get_json()['data']
        client.put(f"/api/transactions/{txns[0]['id']}", json={'category_id': category_id}, headers=auth_headers)

        response = client.delete(f'/api/categories/{category_id}', headers=auth_headers)
        assert response.status_code == 200

        txns_after = client.get('/api/transactions', headers=auth_headers).get_json()['data']
        moved = next(t for t in txns_after if t['id'] == txns[0]['id'])
        assert moved['category']['name'] == 'Other'

    def test_categories_are_not_visible_to_other_users(self, client, auth_headers):
        client.post('/api/categories', json={'name': 'Pet Care'}, headers=auth_headers)

        client.post('/api/auth/signup', json={'username': 'other', 'email': 'other@example.com', 'password': 'Passw0rd!'})
        token_b = client.post('/api/auth/login', json={'email': 'other@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        response = client.get('/api/categories', headers={'Authorization': f'Bearer {token_b}'})
        names = {c['name'] for c in response.get_json()['data']}
        assert 'Pet Care' not in names


class TestBudgets:
    def test_create_and_list_budget_with_real_spend(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': 5000}, headers=auth_headers)

        response = client.get('/api/budgets', headers=auth_headers)
        assert response.status_code == 200
        budget = response.get_json()['data'][0]
        assert budget['monthly_limit'] == 5000.0
        assert budget['spent'] == 0.0
        assert budget['remaining'] == 5000.0

    def test_setting_budget_twice_updates_not_duplicates(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': 5000}, headers=auth_headers)
        client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': 7000}, headers=auth_headers)

        response = client.get('/api/budgets', headers=auth_headers)
        budgets = response.get_json()['data']
        assert len(budgets) == 1
        assert budgets[0]['monthly_limit'] == 7000.0

    def test_negative_budget_limit_rejected(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        response = client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': -100}, headers=auth_headers)
        assert response.status_code == 400

    def test_delete_budget(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        create = client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': 5000}, headers=auth_headers)
        budget_id = create.get_json()['data']['id']

        response = client.delete(f'/api/budgets/{budget_id}', headers=auth_headers)
        assert response.status_code == 200
        assert client.get('/api/budgets', headers=auth_headers).get_json()['data'] == []

    def test_budgets_are_isolated_per_user(self, client, auth_headers):
        groceries_id = _get_category_id(client, auth_headers, 'Groceries')
        client.post('/api/budgets', json={'category_id': groceries_id, 'monthly_limit': 5000}, headers=auth_headers)

        client.post('/api/auth/signup', json={'username': 'other2', 'email': 'other2@example.com', 'password': 'Passw0rd!'})
        token_b = client.post('/api/auth/login', json={'email': 'other2@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        response = client.get('/api/budgets', headers={'Authorization': f'Bearer {token_b}'})
        assert response.get_json()['data'] == []


class TestGoals:
    def test_create_goal(self, client, auth_headers):
        response = client.post('/api/goals', json={
            'name': 'Emergency Fund', 'target_amount': 100000, 'target_date': '2026-12-31'
        }, headers=auth_headers)
        assert response.status_code == 201
        body = response.get_json()['data']
        assert body['current_amount'] == 0.0
        assert body['percent_complete'] == 0.0
        assert body['is_complete'] is False

    def test_contribute_updates_progress(self, client, auth_headers):
        create = client.post('/api/goals', json={'name': 'Vacation', 'target_amount': 20000}, headers=auth_headers)
        goal_id = create.get_json()['data']['id']

        response = client.post(f'/api/goals/{goal_id}/contribute', json={'amount': 5000}, headers=auth_headers)
        assert response.status_code == 200
        assert response.get_json()['data']['current_amount'] == 5000.0
        assert response.get_json()['data']['percent_complete'] == 25.0

    def test_goal_marks_complete_at_target(self, client, auth_headers):
        create = client.post('/api/goals', json={'name': 'Small Goal', 'target_amount': 100}, headers=auth_headers)
        goal_id = create.get_json()['data']['id']
        client.post(f'/api/goals/{goal_id}/contribute', json={'amount': 150}, headers=auth_headers)

        response = client.get('/api/goals', headers=auth_headers)
        goal = response.get_json()['data'][0]
        assert goal['is_complete'] is True
        assert goal['percent_complete'] == 100.0  # capped, not 150%

    def test_negative_target_amount_rejected(self, client, auth_headers):
        response = client.post('/api/goals', json={'name': 'Bad Goal', 'target_amount': -5}, headers=auth_headers)
        assert response.status_code == 400

    def test_delete_goal(self, client, auth_headers):
        create = client.post('/api/goals', json={'name': 'Temp Goal', 'target_amount': 1000}, headers=auth_headers)
        goal_id = create.get_json()['data']['id']
        response = client.delete(f'/api/goals/{goal_id}', headers=auth_headers)
        assert response.status_code == 200
        assert client.get('/api/goals', headers=auth_headers).get_json()['data'] == []

    def test_goals_are_isolated_per_user(self, client, auth_headers):
        client.post('/api/goals', json={'name': 'Emergency Fund', 'target_amount': 100000}, headers=auth_headers)

        client.post('/api/auth/signup', json={'username': 'other3', 'email': 'other3@example.com', 'password': 'Passw0rd!'})
        token_b = client.post('/api/auth/login', json={'email': 'other3@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        response = client.get('/api/goals', headers={'Authorization': f'Bearer {token_b}'})
        assert response.get_json()['data'] == []

    def test_cannot_contribute_to_another_users_goal(self, client, auth_headers):
        create = client.post('/api/goals', json={'name': 'Vacation', 'target_amount': 20000}, headers=auth_headers)
        goal_id = create.get_json()['data']['id']

        client.post('/api/auth/signup', json={'username': 'other4', 'email': 'other4@example.com', 'password': 'Passw0rd!'})
        token_b = client.post('/api/auth/login', json={'email': 'other4@example.com', 'password': 'Passw0rd!'}).get_json()['data']['access_token']

        response = client.post(f'/api/goals/{goal_id}/contribute', json={'amount': 5000}, headers={'Authorization': f'Bearer {token_b}'})
        assert response.status_code == 404


class TestAnalyticsIncomeSpendingSplit:
    def _upload_mixed(self, client, headers):
        csv_bytes = (
            b'Date,Description,Debit,Credit\n'
            b'2024-01-15,Grocery Shopping,1500,\n'
            b'2024-01-16,Salary Credit,,50000\n'
            b'2024-01-17,Uber Ride,450,\n'
        )
        client.post('/api/uploads', data={'file': (io.BytesIO(csv_bytes), 'mixed.csv')}, headers=headers, content_type='multipart/form-data')

    def test_total_spent_excludes_income(self, client, auth_headers):
        self._upload_mixed(client, auth_headers)
        response = client.get('/api/analytics/summary', headers=auth_headers)
        body = response.get_json()['data']
        assert body['totalSpent'] == 1950.0
        assert body['totalIncome'] == 50000.0
        assert body['savings'] == 50000.0 - 1950.0

    def test_category_breakdown_excludes_credit_transactions(self, client, auth_headers):
        self._upload_mixed(client, auth_headers)
        response = client.get('/api/analytics/summary', headers=auth_headers)
        category_names = {c['name'] for c in response.get_json()['data']['categoryBreakdown']}
        # Salary Credit (income) must not appear in the *spending* breakdown
        assert sum(c['value'] for c in response.get_json()['data']['categoryBreakdown']) == 1950.0

    def test_top_merchants_present(self, client, auth_headers):
        self._upload_mixed(client, auth_headers)
        response = client.get('/api/analytics/summary', headers=auth_headers)
        assert 'topMerchants' in response.get_json()['data']
        assert len(response.get_json()['data']['topMerchants']) > 0

    def test_percent_change_present_for_named_period(self, client, auth_headers):
        self._upload_mixed(client, auth_headers)
        response = client.get('/api/analytics/summary?period=current_month', headers=auth_headers)
        assert 'change' in response.get_json()['data']
        assert set(response.get_json()['data']['change'].keys()) == {'spending', 'income', 'transactions'}
