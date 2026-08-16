# Fintech Expense Classification & Reporting Tool

A secure full-stack web application for uploading bank statements (CSV or
PDF), automatically categorizing every transaction, and visualizing
spending patterns over customizable time periods. Built with **React**,
**Flask (Python)**, and **SQLite/PostgreSQL**, with optional AI features
(chat assistant, savings advice) powered entirely by **open-source
language models** (Ollama locally, Groq in production) rather than a
paid third-party API.

Many people in India use UPI, debit cards, and net banking for daily
transactions - groceries, electricity bills, movie tickets. This app lets
a user upload their bank statement and automatically get it sorted into
categories (food, travel, utilities, shopping, and more), with clear
charts and summaries, so they can understand their spending habits, set
budgets, and make better financial decisions.

## Assignment Deliverables Checklist

This project was built against the "Fintech Expense Classification &
Reporting Tool" assignment brief. Each required deliverable and where to
find it:

| Deliverable | Where |
|---|---|
| User authentication (sign-up, login, logout) | `backend/main.py` auth routes; `frontend/src/pages/Login.jsx`, `SignUp.jsx` |
| CSV upload interface (drag-and-drop) | `frontend/src/pages/Upload.jsx` |
| Backend CSV/PDF parsing, categorization, storage | `backend/services/csv_parser.py`, `pdf_parser.py`, `categorizer.py` |
| Interactive, responsive dashboard with charts | `frontend/src/pages/Dashboard.jsx`, `Reports.jsx` |
| Export as CSV or PDF report | `GET /api/export/csv`, `GET /api/export/pdf` |
| Meaningful error and edge case handling | See "Edge Cases & Testing" below and [SELF_ASSESSMENT.md](SELF_ASSESSMENT.md) |
| Architecture diagram & explanation | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Database schema (users, transactions, categories, uploads) | [ARCHITECTURE.md#3-database-schema](ARCHITECTURE.md#3-database-schema) |
| REST API endpoint specification | [API.md](API.md) |
| Technology stack description | "Technology Stack" section below |
| Automated unit/integration tests | `backend/tests/` - 155 tests, see "Testing" below |
| Deployment to a freely accessible environment | "Deployment" section below (Railway) |
| Self-assessment write-up | [SELF_ASSESSMENT.md](SELF_ASSESSMENT.md) |

## Live Demo

- Frontend: _add your deployed frontend URL here after deployment_
- Backend API: _add your deployed backend URL here after deployment_

(See the "Deployment" section for how this project is deployed to
Railway for free.)

## Features

**Authentication**
- User registration, login, and logout with JWT access + refresh tokens
- Password hashing with bcrypt
- Protected routes and per-user session management

**Statement Upload & Categorization**
- Drag-and-drop upload for **both CSV and PDF** bank statements
- Deterministic parsing that auto-detects the real header row even when a
  bank export has metadata/account-summary rows above it, handles
  multiple date formats, and resolves split Debit/Credit or single
  Amount columns
- PDF statements are parsed by extracting the transaction table (across
  multi-page statements, with repeated per-page headers correctly
  de-duplicated) and reusing the same validated CSV parsing pipeline
- Optional AI-assisted parsing fallback (open-source model) for
  statement layouts the deterministic parser cannot read
- Rule-based auto-categorization (Groceries, Transport, Food & Dining,
  Utilities, Entertainment, Shopping, Health & Medical, Education,
  Insurance, Investment, Salary, Transfer, Other) with a confidence score
- Duplicate-transaction prevention via a SHA-256 content hash, enforced
  both within a single file and across all of a user's past uploads

**Dashboard & Reporting**
- Spending summary, category breakdown (donut chart), monthly
  spending/income trend, top merchants, and period filters
- Dedicated Transactions, Categories, Budgets, Goals, and Reports pages
- Export categorized transactions as CSV or a summary PDF report
- Upload history with per-file status and error detail

**Budgets & Goals**
- Per-category monthly budgets with real spend-to-date tracking
- Savings goals with a retrieval-augmented completion projection: a
  realistic/optimistic/pessimistic date range computed from the user's
  actual historical savings volatility (not a single falsely-precise
  guess), plus optional AI-generated, quantified savings tips

**AI Assistant (open-source models only)**
- A chat assistant grounded in the user's real transaction/budget/goal
  data (retrieval-augmented, not free-form guessing)
- Runs on Ollama locally (free, fully local, no API key) or Groq in
  production (free-tier, OpenAI-compatible API for the same class of
  open-source models) - see "Technology Stack" below
- Multi-language replies: auto-detects the user's language, or the user
  can pin a specific reply language (English, Hindi, Marathi, Tamil,
  Telugu, Bengali, Gujarati, Kannada, Malayalam, Punjabi)

**Platform**
- Strict per-user data isolation, enforced at the database query level
  on every endpoint (not just the UI)
- CORS support, responsive UI (Tailwind CSS)
- Dockerized (Postgres + backend + frontend)
- 155 automated backend tests (pytest) covering parsing, categorization,
  deduplication, per-user isolation, and API integration

## Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18, React Router 6, Tailwind CSS, Recharts, Zustand, Axios | Component-driven SPA, utility-first styling, small dependency footprint |
| Backend | Flask 3, SQLAlchemy, Flask-JWT-Extended | Simple, well-understood, sufficient for this scope without framework overhead |
| Database | SQLite (local dev, zero setup) / PostgreSQL (Docker/production) | SQLite removes any local setup friction; Postgres for concurrent production use |
| AI / LLM | Open-source models only, via [Ollama](https://ollama.com) (local) or [Groq](https://console.groq.com) (production, free tier) | Avoids a paid Anthropic/OpenAI dependency entirely - see [ARCHITECTURE.md](ARCHITECTURE.md) "AI Provider Architecture" |
| PDF parsing | pdfplumber | Extracts real table grids from bank-generated PDF statements |
| PDF export | ReportLab | Generates the downloadable summary PDF report |
| Containerization | Docker, docker-compose | Reproducible local Postgres + backend + frontend stack |
| Testing | pytest, pytest-cov | 155 automated backend tests |
| Hosting (free tier) | Railway (backend), Vercel/Netlify (frontend) | See "Deployment" below |

## Project Structure

```
fullstack/
├── backend/
│   ├── main.py                      Flask app: auth, uploads, transactions,
│   │                                 categories, budgets, goals, analytics,
│   │                                 export, AI chat/insights - entry point
│   ├── services/
│   │   ├── csv_parser.py            CSV parsing, header normalization, dedup hashing
│   │   ├── pdf_parser.py            PDF table extraction, reuses csv_parser
│   │   ├── categorizer.py           Rule-based expense categorization
│   │   ├── ai_client.py             Shared Ollama/Groq client (open-source models)
│   │   ├── llm_extractor.py         AI-assisted parsing fallback
│   │   ├── goal_advisor.py          Goal completion projection + AI savings advice
│   │   └── chat_advisor.py          AI Assistant chat (multi-language)
│   ├── tests/                       155 pytest tests
│   ├── .env.example                 Environment variable template
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── public/index.html
│   ├── src/
│   │   ├── App.jsx                  Routes
│   │   ├── components/              Sidebar, Layout, shared UI
│   │   ├── pages/                   Login, SignUp, Dashboard, Upload,
│   │   │                            Transactions, Categories, Budgets, Goals,
│   │   │                            Reports, Assistant, Settings, Help
│   │   ├── store/authStore.js       Zustand auth store
│   │   └── utils/api.js             Axios client for all API calls
│   ├── package.json
│   └── .env.example
│
├── docker-compose.yml
├── ARCHITECTURE.md                  System diagram, schema, AI provider
│                                     architecture, security design
├── SELF_ASSESSMENT.md               Design trade-offs, edge cases, known limitations
├── API.md                           Full endpoint reference
└── README.md                        This file
```

## Getting Started

### Prerequisites

- **Backend**: Python 3.10+
- **Frontend**: Node.js 18+, npm
- **AI features (optional)**: [Ollama](https://ollama.com) installed locally

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# SQLite is the default local database - no setup required.
# AI_PROVIDER defaults to "ollama"; leave it as-is for local development.

python main.py
# Backend runs on http://localhost:5000
```

To enable the AI Assistant and AI-assisted parsing locally:
```bash
ollama pull llama3.1
ollama serve
```

### Frontend Setup

```bash
cd frontend
npm install

cp .env.example .env
# Set REACT_APP_API_URL=http://localhost:5000/api

npm start
# Frontend runs on http://localhost:3000
```

## API Endpoints

Full reference with request/response examples: [API.md](API.md).

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/auth/me` |
| Uploads | `POST /api/uploads` (CSV or PDF), `GET /api/uploads` |
| Transactions | `GET /api/transactions`, `PUT /api/transactions/<id>` |
| Categories | `GET/POST /api/categories`, `PUT/DELETE /api/categories/<id>` |
| Budgets | `GET/POST /api/budgets`, `PUT/DELETE /api/budgets/<id>` |
| Goals | `GET/POST /api/goals`, `PUT/DELETE /api/goals/<id>`, `POST /api/goals/<id>/contribute`, `GET /api/goals/<id>/insights` |
| Analytics | `GET /api/analytics/summary` |
| Export | `GET /api/export/csv`, `GET /api/export/pdf` |
| AI Assistant | `POST /api/chat`, `GET /api/chat/languages` |

## Database Schema

Full schema with relationships and rationale: [ARCHITECTURE.md#3-database-schema](ARCHITECTURE.md#3-database-schema)
(`users`, `categories`, `uploads`, `transactions`, `budgets`, `goals`).
Every user-owned table filters by `user_id` taken from the JWT, on every
query - per-user data isolation is enforced at the database layer, not
just the UI.

## Edge Cases & Testing

Handled and covered by automated tests:
- Malformed or corrupt CSV/PDF files (`422` with a specific error, never
  a raw stack trace)
- Bank exports with metadata/account-summary rows above the real header
- Multiple date formats, and split Debit/Credit vs. single Amount columns
- Duplicate or overlapping transactions, both within one file and across
  multiple uploads (SHA-256 content hash + a DB-level unique constraint)
- Multi-page PDF statements with a repeated header on every page
- Oversized uploads (rejected before parsing)
- Session/token expiration mid-upload
- Cross-user data isolation (verified by dedicated isolation tests for
  transactions, categories, budgets, goals, and AI chat context)

```bash
cd backend
pytest tests/ -v                            # Run all 155 tests
pytest tests/ --cov=services --cov=main      # With coverage report
```

## Deployment

This project is designed to be deployable at (close to) ₹0/month:

- **Backend** → [Railway](https://railway.com) - connect this GitHub
  repository, deploy the `backend/` service with `gunicorn -w 2 -b
  0.0.0.0:$PORT main:app`, and set the environment variables listed in
  `backend/.env.example` (`DATABASE_URL`, `JWT_SECRET_KEY`,
  `CORS_ORIGINS`, `AI_PROVIDER=groq`, `GROQ_API_KEY`). See
  `backend/railway.json` / `backend/Procfile` in this repo.
- **Database** → Railway's built-in PostgreSQL plugin, or a free
  [Neon](https://neon.tech) Postgres instance.
- **Frontend** → [Vercel](https://vercel.com) or
  [Netlify](https://netlify.com) (free static hosting), with
  `REACT_APP_API_URL` pointed at the deployed backend URL. Railway can
  also host the frontend as a second service if you prefer keeping
  everything under one platform.
- **AI provider** → [Groq](https://console.groq.com) (free tier) -
  Ollama cannot run on Railway or any serverless/managed platform, since
  it requires a long-running process with model weights on local disk.

Full step-by-step deployment instructions: see the "Free (~₹0/month)
Deployment" section in [INSTALLATION.md](INSTALLATION.md).

## Security Considerations

Full write-up: [ARCHITECTURE.md#6-security-considerations](ARCHITECTURE.md).
Summary: JWT-based auth with bcrypt password hashing, per-user data
isolation enforced at the query level, SQLAlchemy ORM parameterized
queries (no raw SQL string building), CSV-injection sanitization,
upload size/type limits, and CORS restricted to the configured frontend
origin. AI features send data to a third party (Groq) only in
production and only when a feature is actually used; local development
with Ollama sends nothing off the machine.

## Self-Assessment

Design choices, trade-offs, what worked well, what could be improved,
and how specific edge cases were resolved: [SELF_ASSESSMENT.md](SELF_ASSESSMENT.md).

## License

This project is licensed under the MIT License - see the LICENSE file
for details.
