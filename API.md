# API Documentation

## Base URL

```
http://localhost:5000/api
```

## Authentication

All authenticated endpoints require an `Authorization` header:

```
Authorization: Bearer <access_token>
```

## Response Format

All responses follow this format:

```json
{
  "success": true|false,
  "message": "Human readable message",
  "data": {
    // Response data
  },
  "timestamp": "ISO 8601 timestamp"
}
```

## Error Handling

### Validation Errors (422)
```json
{
  "success": false,
  "message": "Validation failed",
  "data": {
    "errors": {
      "field_name": ["Error message 1", "Error message 2"]
    }
  }
}
```

### Authentication Errors (401)
```json
{
  "success": false,
  "message": "Authorization required|Invalid token|Token has expired",
  "data": null
}
```

### Server Errors (500)
```json
{
  "success": false,
  "message": "Internal server error",
  "data": null
}
```

## Endpoints

### 1. Sign Up

Create a new user account.

**Endpoint:** `POST /auth/signup`

**Authentication:** ❌ Not required

**Request Body:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| username | string | ✅ | 3-80 characters, alphanumeric + underscore |
| email | string | ✅ | Valid email address |
| password | string | ✅ | Min 8 chars, must include uppercase, lowercase, digit, special char |
| confirm_password | string | ✅ | Must match password |
| first_name | string | ❌ | Letters and spaces only |
| last_name | string | ❌ | Letters and spaces only |

**Success Response (201):**
```json
{
  "success": true,
  "message": "User registered successfully",
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "is_active": true,
      "is_verified": false,
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:30:00",
      "last_login": null
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

**Error Response (422):**
```json
{
  "success": false,
  "message": "Validation failed",
  "data": {
    "errors": {
      "username": ["Username already exists"],
      "email": ["Email already exists"],
      "password": ["Password must contain at least one uppercase letter"]
    }
  }
}
```

**curl Example:**
```bash
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "first_name": "John",
    "last_name": "Doe"
  }'
```

---

### 2. Login

Authenticate user and receive tokens.

**Endpoint:** `POST /auth/login`

**Authentication:** ❌ Not required

**Request Body:**
```json
{
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| email | string | ✅ | Valid email address |
| password | string | ✅ | User password |

**Success Response (200):**
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "is_active": true,
      "is_verified": false,
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:30:00",
      "last_login": "2024-01-15T10:35:00"
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

**Error Response (401):**
```json
{
  "success": false,
  "message": "Login failed",
  "data": {
    "errors": {
      "email": ["Email not found"],
      "password": ["Invalid password"]
    }
  }
}
```

**curl Example:**
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "SecurePass123!"
  }'
```

---

### 3. Refresh Token

Get a new access token using refresh token.

**Endpoint:** `POST /auth/refresh`

**Authentication:** ✅ Required (Refresh Token)

**Request Body:** Empty

**Success Response (200):**
```json
{
  "success": true,
  "message": "Token refreshed successfully",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

**Error Response (401):**
```json
{
  "success": false,
  "message": "Token has expired",
  "data": null
}
```

**curl Example:**
```bash
curl -X POST http://localhost:5000/api/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"
```

---

### 4. Logout

Revoke refresh token and logout user.

**Endpoint:** `POST /auth/logout`

**Authentication:** ✅ Required (Access Token)

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Logout successful",
  "data": null
}
```

**curl Example:**
```bash
curl -X POST http://localhost:5000/api/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

---

### 5. Get Current User

Retrieve authenticated user's information.

**Endpoint:** `GET /auth/me`

**Authentication:** ✅ Required (Access Token)

**Request Body:** Empty

**Success Response (200):**
```json
{
  "success": true,
  "message": "User retrieved successfully",
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "is_active": true,
      "is_verified": false,
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:30:00",
      "last_login": "2024-01-15T10:35:00"
    }
  }
}
```

**Error Response (404):**
```json
{
  "success": false,
  "message": "User not found",
  "data": null
}
```

**curl Example:**
```bash
curl -X GET http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

### 6. Update Profile

Update user profile information.

**Endpoint:** `PUT /auth/profile`

**Authentication:** ✅ Required (Access Token)

**Request Body:**
```json
{
  "first_name": "Johnny",
  "last_name": "Smith"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| first_name | string | ❌ | Letters and spaces only |
| last_name | string | ❌ | Letters and spaces only |

**Success Response (200):**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "john_doe",
      "email": "john@example.com",
      "first_name": "Johnny",
      "last_name": "Smith",
      "is_active": true,
      "is_verified": false,
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:40:00",
      "last_login": "2024-01-15T10:35:00"
    }
  }
}
```

**Error Response (422):**
```json
{
  "success": false,
  "message": "Validation failed",
  "data": {
    "errors": {
      "first_name": ["First name can only contain letters and spaces"]
    }
  }
}
```

**curl Example:**
```bash
curl -X PUT http://localhost:5000/api/auth/profile \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Johnny",
    "last_name": "Smith"
  }'
```

---

### 7. Health Check

Check if API is running.

**Endpoint:** `GET /health`

**Authentication:** ❌ Not required

**Success Response (200):**
```json
{
  "success": true,
  "message": "Server is running",
  "data": {
    "status": "healthy"
  }
}
```

**curl Example:**
```bash
curl -X GET http://localhost:5000/api/health
```

---

## Token Expiration

- **Access Token**: 1 hour
- **Refresh Token**: 30 days

## Rate Limiting

Currently not enforced by default. Can be enabled using the `@rate_limit` decorator:

```python
@app.route('/endpoint')
@rate_limit(max_requests=100, window_seconds=3600)
def endpoint():
    pass
```

## CORS

Configured to accept requests from:
- `http://localhost:3000` (default)
- Configure in `CORS_ORIGINS` environment variable

## Security Headers

Recommended headers to add in production:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
```

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request succeeded |
| 201 | Created - Resource created successfully |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Authentication required/failed |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource already exists |
| 422 | Unprocessable Entity - Validation failed |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Server error |

## Best Practices

1. **Always use HTTPS in production**
2. **Store tokens securely** (httpOnly cookies or secure storage)
3. **Refresh tokens before expiration**
4. **Handle token refresh errors gracefully**
5. **Validate input on both client and server**
6. **Use strong passwords** (enforce password requirements)
7. **Implement logout everywhere** when token is revoked
8. **Monitor failed login attempts**
9. **Log all authentication events**
10. **Use environment variables for sensitive data**

## Examples

### JavaScript (Fetch)

```javascript
// Sign Up
const response = await fetch('http://localhost:5000/api/auth/signup', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    username: 'john_doe',
    email: 'john@example.com',
    password: 'SecurePass123!',
    confirm_password: 'SecurePass123!',
  }),
});
const data = await response.json();

// Login
const loginResponse = await fetch('http://localhost:5000/api/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'john@example.com',
    password: 'SecurePass123!',
  }),
});
const loginData = await loginResponse.json();
const accessToken = loginData.data.tokens.access_token;

// Authenticated Request
const userResponse = await fetch('http://localhost:5000/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});
const userData = await userResponse.json();
```

### Python (Requests)

```python
import requests

BASE_URL = 'http://localhost:5000/api'

# Sign Up
signup_data = {
    'username': 'john_doe',
    'email': 'john@example.com',
    'password': 'SecurePass123!',
    'confirm_password': 'SecurePass123!',
}
response = requests.post(f'{BASE_URL}/auth/signup', json=signup_data)
print(response.json())

# Login
login_data = {
    'email': 'john@example.com',
    'password': 'SecurePass123!',
}
response = requests.post(f'{BASE_URL}/auth/login', json=login_data)
tokens = response.json()['data']['tokens']
access_token = tokens['access_token']

# Authenticated Request
headers = {'Authorization': f'Bearer {access_token}'}
response = requests.get(f'{BASE_URL}/auth/me', headers=headers)
print(response.json())
```

---

---

## Expense Management API (as actually served by `backend/main.py`)

> **Note on response envelope:** the sections above describe the blueprint-based
> scaffold under `backend/app/`, which is not the server that runs. The app that
> `docker-compose` and `python main.py` actually start is the single-file Flask
> app in `backend/main.py`; its responses use a slightly simpler envelope:
> `{"success": bool, "data"?: ..., "error"?: "message", "message"?: "message"}`
> (no `timestamp` field). All endpoints below are auth-scoped to the requesting
> user via the JWT `sub` claim — no cross-user data is ever returned.

### Upload a bank statement

```
POST /api/uploads
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <statement.csv>
```

- Parses the CSV (flexible header matching: `Date`/`Transaction Date`, `Description`/`Narration`, `Amount` or `Debit`), auto-categorizes each row, and skips duplicates (hash of date + description + amount, unique per user).
- `413` if the file exceeds 10MB, `400` if it's missing/empty/not a `.csv`, `422` if the file can't be parsed (malformed CSV, missing columns, unreadable data).

```json
{
  "success": true,
  "message": "Uploaded 3 new transaction(s)",
  "data": {
    "upload": { "id": "...", "filename": "statement.csv", "status": "completed", "parsed_count": 3, "duplicate_count": 1 },
    "inserted": 3,
    "duplicates_skipped": 1
  }
}
```

### List upload history

```
GET /api/uploads
Authorization: Bearer <access_token>
```

### List transactions

```
GET /api/transactions?page=1&per_page=50&category=<id>&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
Authorization: Bearer <access_token>
```

### Update a transaction's category

```
PUT /api/transactions/<id>
Authorization: Bearer <access_token>
Content-Type: application/json

{ "category_id": "<category-id>" }
```

### Spending summary / analytics

```
GET /api/analytics/summary?period=current_month
GET /api/analytics/summary?date_from=2024-01-01&date_to=2024-03-31
Authorization: Bearer <access_token>
```

`period` accepts `current_month`, `last_3_months`, `last_6_months`, `ytd`, or is omitted for all-time. `date_from`/`date_to` override `period` with a custom range.

```json
{
  "success": true,
  "data": {
    "totalSpent": 3950.0,
    "totalTransactions": 3,
    "averageTransaction": 1316.67,
    "categoryBreakdown": [{ "name": "Utilities", "value": 2000.0 }],
    "monthlyTrends": [{ "month": "Jan 2024", "amount": 1500.0 }],
    "topCategories": [{ "name": "Utilities", "value": 2000.0 }],
    "period": { "from": null, "to": null }
  }
}
```

### List categories

```
GET /api/categories
```

### Export data

```
GET /api/export/csv?period=current_month
GET /api/export/pdf?period=current_month
Authorization: Bearer <access_token>
```

Both accept the same `period`/`date_from`/`date_to`/`category` filters as the summary endpoint and stream back a file download (`text/csv` or `application/pdf`) rather than JSON.

---

## Support

For API issues or questions, please open an issue in the repository.
