# Complete File Structure & Documentation

## 📁 Project Layout

```
fullstack-auth-app/                    (Root directory)
│
├── backend/                           (Python Flask Backend)
│   ├── app/                          (Application package)
│   │   ├── __init__.py               (Flask app factory - creates and configures app)
│   │   ├── extensions.py             (Flask extensions - SQLAlchemy, JWT, CORS)
│   │   │
│   │   ├── models/                   (Database models)
│   │   │   ├── __init__.py
│   │   │   └── user.py               (User & RefreshTokenBlacklist models with bcrypt)
│   │   │
│   │   ├── routes/                   (API endpoints - blueprints)
│   │   │   ├── __init__.py
│   │   │   └── auth.py               (Auth endpoints: signup, login, refresh, logout, etc)
│   │   │
│   │   ├── services/                 (Business logic layer)
│   │   │   ├── __init__.py
│   │   │   └── auth_service.py       (Authentication service - register, login, tokens)
│   │   │
│   │   ├── validators/               (Input validation)
│   │   │   ├── __init__.py
│   │   │   └── user_validator.py     (Validate username, email, password, etc)
│   │   │
│   │   ├── utils/                    (Utility functions)
│   │   │   ├── __init__.py
│   │   │   ├── decorators.py         (Error handling, validation decorators)
│   │   │   └── helpers.py            (Response formatting, logging)
│   │   │
│   │   └── middleware/               (Middleware - optional)
│   │       └── __init__.py
│   │
│   ├── config/                       (Configuration management)
│   │   ├── __init__.py
│   │   └── settings.py               (Development, Production, Testing configs)
│   │
│   ├── tests/                        (Unit & integration tests - optional)
│   │   ├── __init__.py
│   │   ├── conftest.py              (Pytest configuration)
│   │   ├── test_auth.py             (Auth endpoint tests)
│   │   ├── test_validators.py       (Validator tests)
│   │   └── test_services.py         (Service layer tests)
│   │
│   ├── logs/                        (Application logs - generated at runtime)
│   │   └── app.log
│   │
│   ├── migrations/                  (Database migrations - Flask-Migrate)
│   │   └── versions/
│   │
│   ├── main.py                      (Application entry point - run this!)
│   ├── requirements.txt             (Python dependencies)
│   ├── .env.example                 (Environment template)
│   ├── Dockerfile                   (Docker configuration)
│   └── README.md                    (Backend specific docs)
│
├── frontend/                        (React Frontend)
│   ├── public/                      (Static files)
│   │   └── index.html              (HTML template)
│   │
│   ├── src/                        (React source code)
│   │   ├── App.jsx                 (Main component with routing)
│   │   ├── index.jsx               (React entry point)
│   │   ├── index.css               (Global styles + Tailwind)
│   │   │
│   │   ├── components/             (Reusable components)
│   │   │   ├── FormInput.jsx       (Input component with validation)
│   │   │   └── ProtectedRoute.jsx  (Route guard for auth)
│   │   │
│   │   ├── pages/                  (Page components)
│   │   │   ├── Login.jsx           (Login page - form, validation, API call)
│   │   │   ├── SignUp.jsx          (Sign up page - comprehensive form)
│   │   │   └── Dashboard.jsx       (Dashboard - user profile, edit profile)
│   │   │
│   │   ├── store/                  (State management - Zustand)
│   │   │   └── authStore.js        (Auth state - login, signup, token management)
│   │   │
│   │   └── utils/                  (Utility functions)
│   │       ├── api.js              (Axios API client with interceptors)
│   │       └── validators.js       (Form validation rules)
│   │
│   ├── package.json                (NPM dependencies & scripts)
│   ├── tailwind.config.js          (Tailwind CSS configuration)
│   ├── .env.example                (Environment template)
│   ├── Dockerfile                  (Docker configuration)
│   └── README.md                   (Frontend specific docs)
│
├── docker-compose.yml              (Docker Compose - run all services)
├── Makefile                        (Common commands - make help)
├── .gitignore                      (Git ignore rules)
│
├── README.md                       (Main project documentation)
├── QUICKSTART.md                   (Quick start guide - 5 min setup)
├── API.md                          (Detailed API documentation)
└── FILE_STRUCTURE.md              (This file!)
```

## 📋 File Descriptions

### Backend Files

#### Core Application (`backend/app/`)

| File | Purpose | Key Components |
|------|---------|-----------------|
| `__init__.py` | App Factory | Creates Flask app, registers blueprints, configures JWT |
| `extensions.py` | Flask Extensions | Initializes: SQLAlchemy, JWT, CORS, Flask-Migrate |
| `config/settings.py` | Configuration | Environment-specific settings (dev, prod, test) |

#### Models (`backend/app/models/`)

| File | Purpose | Models |
|------|---------|--------|
| `user.py` | Database Models | `User` (main user model), `RefreshTokenBlacklist` (token revocation) |

**User Model Features:**
- UUID primary key
- Unique username & email (indexed)
- bcrypt password hashing (12 rounds)
- Account status (active/verified)
- Timestamps (created, updated, last_login)
- Methods: `set_password()`, `verify_password()`, `to_dict()`, `update_last_login()`

#### Routes (`backend/app/routes/`)

| File | Purpose | Endpoints |
|------|---------|-----------|
| `auth.py` | Auth API | POST /signup, /login, /refresh, /logout; GET /me; PUT /profile |

**Response Format:**
```json
{
  "success": true,
  "message": "...",
  "data": {},
  "timestamp": "ISO 8601"
}
```

#### Services (`backend/app/services/`)

| File | Purpose | Functions |
|------|---------|-----------|
| `auth_service.py` | Auth Business Logic | register_user(), login_user(), create_tokens(), refresh_access_token(), revoke_token() |

#### Validators (`backend/app/validators/`)

| File | Purpose | Validations |
|------|---------|------------|
| `user_validator.py` | Input Validation | username, email, password strength, name fields |

**Validation Rules:**
- Username: 3-80 chars, alphanumeric + underscore
- Email: Valid email format
- Password: Min 8 chars, uppercase, lowercase, digit, special char
- Name: Letters and spaces only

#### Utilities (`backend/app/utils/`)

| File | Purpose | Decorators/Functions |
|------|---------|---------------------|
| `decorators.py` | Error Handling | `@handle_errors`, `@validate_json`, `@require_data_keys`, `@rate_limit` |
| `helpers.py` | Helper Functions | `send_response()`, `log_error()`, `sanitize_input()` |

#### Entry Point

| File | Purpose |
|------|---------|
| `main.py` | Starts Flask server on `http://localhost:5000` |

---

### Frontend Files

#### Main Application (`frontend/src/`)

| File | Purpose |
|------|---------|
| `App.jsx` | Main component - routing, layout |
| `index.jsx` | React DOM render point |
| `index.css` | Global styles, Tailwind imports, animations |

#### Components (`frontend/src/components/`)

| File | Purpose | Props |
|------|---------|-------|
| `FormInput.jsx` | Input component | name, type, label, value, error, touched, etc |
| `ProtectedRoute.jsx` | Route guard | children, checks authentication |

#### Pages (`frontend/src/pages/`)

| File | Purpose | Features |
|------|---------|----------|
| `Login.jsx` | Login page | Email/password form, remember me, validation, error display |
| `SignUp.jsx` | Sign up page | Full registration form, password confirmation, field validation |
| `Dashboard.jsx` | Dashboard | User profile display, edit profile, logout, status badges |

#### State Management (`frontend/src/store/`)

| File | Purpose | Methods |
|------|---------|---------|
| `authStore.js` | Zustand Store | signup(), login(), logout(), refreshToken(), updateProfile(), getCurrentUser() |

**Store State:**
- user: Current user object
- tokens: { access_token, refresh_token }
- isAuthenticated: Boolean
- loading: Boolean
- error: Error message

#### Utilities (`frontend/src/utils/`)

| File | Purpose | Exports |
|------|---------|---------|
| `api.js` | Axios API Client | authAPI object with all endpoints, interceptors |
| `validators.js` | Form Validators | validators object with email, username, password functions |

---

### Configuration Files

| File | Purpose |
|------|---------|
| `.env.example` | Template for environment variables |
| `requirements.txt` | Python package dependencies |
| `package.json` | Node.js dependencies and scripts |
| `docker-compose.yml` | Multi-container Docker setup |
| `Dockerfile` (backend) | Backend container image |
| `Dockerfile` (frontend) | Frontend container image |
| `Makefile` | Common development commands |
| `.gitignore` | Git ignore patterns |

---

## 🔄 Data Flow

### Sign Up Flow

```
Frontend (SignUp.jsx)
    ↓
Form Validation (validators.js)
    ↓
authStore.signup() (Zustand)
    ↓
API POST /auth/signup (axios)
    ↓
Backend: auth_bp.signup()
    ↓
UserValidator.validate_signup_data()
    ↓
AuthService.register_user()
    ↓
User Model created → Database
    ↓
Tokens created (JWT)
    ↓
Response with tokens
    ↓
Frontend: Store user & tokens in localStorage
    ↓
Redirect to Dashboard
```

### Login Flow

```
Frontend (Login.jsx)
    ↓
Form Validation
    ↓
authStore.login()
    ↓
API POST /auth/login
    ↓
Backend: auth_bp.login()
    ↓
UserValidator.validate_login_data()
    ↓
AuthService.login_user()
    ↓
Verify email & password
    ↓
Update last_login timestamp
    ↓
Create tokens
    ↓
Response with tokens
    ↓
Frontend: Store & set Authorization header
    ↓
Redirect to Dashboard
```

### Protected Request Flow

```
Frontend
    ↓
Read token from localStorage
    ↓
Set Authorization header: Bearer <access_token>
    ↓
API GET /auth/me
    ↓
Backend: @jwt_required() checks token
    ↓
If valid: Process request
If expired: Return 401
    ↓
Frontend: Intercept 401, call refresh endpoint
    ↓
Get new access token
    ↓
Retry original request
    ↓
On logout: Clear localStorage & token
```

---

## 🗄️ Database Schema

### users table
```sql
CREATE TABLE users (
  id VARCHAR(36) PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  email VARCHAR(120) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  first_name VARCHAR(50),
  last_name VARCHAR(50),
  is_active BOOLEAN DEFAULT TRUE,
  is_verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP,
  INDEX idx_username (username),
  INDEX idx_email (email)
);
```

### refresh_token_blacklist table
```sql
CREATE TABLE refresh_token_blacklist (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL,
  jti VARCHAR(255) UNIQUE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX idx_user_id (user_id),
  INDEX idx_jti (jti)
);
```

---

## 🔐 Security Implementation

### Password Security
- Bcrypt hashing with 12 salt rounds
- Password validation: uppercase, lowercase, digit, special char
- Minimum 8 characters, maximum 128 characters

### Token Security
- JWT with HS256 algorithm
- Access token: 1 hour expiration
- Refresh token: 30 days expiration
- Automatic token refresh with interceptors
- Token blacklisting for logout

### Input Validation
- Frontend: Real-time validation
- Backend: Server-side validation on all inputs
- SQL Injection prevention via ORM
- Input sanitization

### HTTP Security
- CORS configuration per environment
- Secure headers (httpOnly, Secure, SameSite)
- Rate limiting support
- HTTPS ready

---

## 📊 File Statistics

```
Backend:
- Python files: 15+
- Lines of code: ~1500+
- Test coverage: Extensible test structure

Frontend:
- React components: 6+
- JavaScript files: 4+
- Total files: 10+
- Styled with Tailwind CSS
```

---

## 🚀 Getting Started

1. **Read QUICKSTART.md** - 5 minute setup guide
2. **Run `docker-compose up`** - If Docker installed
3. **Or follow manual setup** - In README.md
4. **Visit http://localhost:3000** - Frontend
5. **API at http://localhost:5000/api** - Backend

---

## 📚 Documentation Files

| File | Contains |
|------|----------|
| `README.md` | Complete project overview, features, setup |
| `QUICKSTART.md` | Quick start guide with Docker & manual setup |
| `API.md` | Detailed API endpoint documentation |
| `FILE_STRUCTURE.md` | This file - complete file reference |
| `backend/` | Backend-specific documentation |
| `frontend/` | Frontend-specific documentation |

---

## 🔧 Development Workflow

```bash
# 1. Install dependencies
make install

# 2. Start services
make docker-up        # OR
make run             # Manual setup (needs 2 terminals)

# 3. Access applications
# Frontend: http://localhost:3000
# Backend:  http://localhost:5000/api

# 4. Make changes
# - Backend changes auto-reload (debug mode)
# - Frontend changes hot-reload

# 5. Run tests
make test

# 6. Format code
make format

# 7. Stop services
make docker-down
```

---

## 💡 Key Features by File

### Most Important Files for Understanding the App

1. **`backend/app/__init__.py`** - App initialization & configuration
2. **`backend/app/routes/auth.py`** - All API endpoints
3. **`backend/app/models/user.py`** - Database schema
4. **`backend/app/services/auth_service.py`** - Core business logic
5. **`frontend/src/store/authStore.js`** - State management
6. **`frontend/src/pages/Login.jsx`** - Frontend login flow
7. **`frontend/src/pages/Dashboard.jsx`** - Protected route example

---

## 🎯 Next Steps After Setup

1. ✅ Create user account
2. ✅ Login and view dashboard
3. ✅ Update profile information
4. 📚 Read API.md for all endpoints
5. 🔧 Customize components & styling
6. 🧪 Write tests
7. 🚀 Deploy to production

---

## 📞 Support

Refer to:
- README.md for general info
- QUICKSTART.md for setup issues
- API.md for API questions
- Check frontend/src and backend/app for code examples

Happy coding! 🎉
