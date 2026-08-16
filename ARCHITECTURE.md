# Architecture — Fintech Expense Classification & Reporting Tool

## 1. System Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                         BROWSER (React SPA)                        │
│                                                                     │
│  Login / SignUp ──▶ authStore (Zustand, JWT in localStorage)       │
│                                                                     │
│  Upload.jsx  ──drag/drop CSV/PDF──▶  expenseAPI.uploadCSV()         │
│  Dashboard.jsx ──period filter──▶ expenseAPI.getAnalyticsSummary() │
│                ──export────────▶ expenseAPI.exportCSV/PDF()        │
│                                                                     │
│  apiClient (axios) attaches "Authorization: Bearer <token>"        │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ HTTPS / JSON + multipart
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                    BACKEND (Flask, backend/main.py)                │
│                                                                     │
│  Auth routes        /api/auth/signup, /login, /me                  │
│  Upload route        /api/uploads  (POST, multipart)                │
│    └─▶ services/csv_parser.py   (parse, header-detect, hash rows)   │
│    └─▶ services/pdf_parser.py   (PDF table → CSV, reuses csv_parser)│
│    └─▶ services/llm_extractor.py (AI fallback, opt-in via API key)  │
│    └─▶ services/categorizer.py  (keyword/regex rule engine)         │
│  Transaction routes  /api/transactions (GET, PUT)                   │
│  Analytics route     /api/analytics/summary (period filters)        │
│  Export routes       /api/export/csv, /api/export/pdf               │
│                                                                     │
│  Cross-cutting: Flask-JWT-Extended (auth), Flask-CORS,               │
│  SQLAlchemy ORM (parameterized queries), bcrypt password hashing    │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ SQL (SQLAlchemy)
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL 15, Docker)                 │
│   users │ categories │ uploads │ transactions                       │
└───────────────────────────────────────────────────────────────────┘

Deployment: docker-compose orchestrates postgres + backend (gunicorn) +
frontend (static build) as three containers on a shared bridge network.
```

## 2. Component Responsibilities

- **Frontend (React + Tailwind + Recharts)** — auth screens, drag-and-drop
  upload with progress/duplicate/error feedback, a dashboard with pie/bar
  charts and a time-period filter, and CSV/PDF export triggers. All API
  calls go through a single axios client (`frontend/src/utils/api.js`) that
  attaches the JWT and centralizes the base URL.
- **Backend (Flask)** — a single application module (`backend/main.py`)
  exposing REST endpoints, backed by two standalone service modules:
  - `services/csv_parser.py` — header normalization across bank formats,
    date-format detection, per-row validation, SHA-256 hashing for
    duplicate detection, and CSV-injection sanitization.
  - `services/pdf_parser.py` — extracts a bank statement PDF's transaction
    table (via `pdfplumber`, across pages, de-duplicating repeated
    per-page headers) and reconstructs it as CSV text so it can be parsed
    by the same `csv_parser.py` a `.csv` upload uses, instead of
    duplicating validation logic for a second file format.
  - `services/categorizer.py` — a three-tier rule engine (exact keyword →
    regex pattern → substring) that assigns a category and a confidence
    score to each transaction.
- **Database (PostgreSQL in production, SQLite for local dev)** — see
  schema below. SQLAlchemy's query builder parameterizes all queries,
  so there is no raw SQL string concatenation anywhere in the app.

## 3. Database Schema

```sql
users
  id            VARCHAR(36) PK
  username      VARCHAR(100) UNIQUE NOT NULL
  email         VARCHAR(120) UNIQUE NOT NULL
  password_hash VARCHAR(500) NOT NULL   -- bcrypt
  first_name    VARCHAR(100)
  last_name     VARCHAR(100)
  created_at    TIMESTAMP
  updated_at    TIMESTAMP

categories
  id          VARCHAR(36) PK
  name        VARCHAR(100) NOT NULL          -- Groceries, Transport, ...
  description TEXT
  icon        VARCHAR(50)
  color       VARCHAR(7)
  user_id     VARCHAR(36) FK -> users.id, NULLABLE
              -- NULL = shared/default category (visible to everyone).
              -- Set = a custom category owned by (and only visible to) that user.

budgets
  id            VARCHAR(36) PK
  user_id       VARCHAR(36) FK -> users.id
  category_id   VARCHAR(36) FK -> categories.id
  monthly_limit NUMERIC(10,2) NOT NULL
  created_at    TIMESTAMP
  updated_at    TIMESTAMP
  UNIQUE (user_id, category_id)   -- one budget per category per user

goals
  id             VARCHAR(36) PK
  user_id        VARCHAR(36) FK -> users.id
  name           VARCHAR(200) NOT NULL
  target_amount  NUMERIC(12,2) NOT NULL
  current_amount NUMERIC(12,2) NOT NULL DEFAULT 0
  target_date    DATE NULLABLE
  icon           VARCHAR(10)
  created_at     TIMESTAMP
  updated_at     TIMESTAMP

uploads
  id                VARCHAR(36) PK
  user_id           VARCHAR(36) FK -> users.id
  filename          VARCHAR(255) NOT NULL
  file_size         INTEGER
  upload_date       TIMESTAMP
  status            VARCHAR(50)   -- processing | completed | failed
  parsed_count      INTEGER       -- rows actually inserted
  duplicate_count   INTEGER       -- rows skipped as duplicates
  invalid_row_count INTEGER
  error_message     TEXT

transactions
  id               VARCHAR(36) PK
  user_id          VARCHAR(36) FK -> users.id
  upload_id        VARCHAR(36) FK -> uploads.id (nullable)
  transaction_date DATE NOT NULL
  description      VARCHAR(500) NOT NULL
  amount           NUMERIC(10,2) NOT NULL
  category_id      VARCHAR(36) FK -> categories.id
  transaction_type VARCHAR(20)    -- debit | credit
  confidence       FLOAT          -- categorizer confidence, 0-1
  tx_hash          VARCHAR(64) NOT NULL   -- sha256(date|description|amount)
  created_at       TIMESTAMP

  UNIQUE (user_id, tx_hash)   -- duplicate-transaction guard, enforced in DB
```

`users(1)──(N)transactions`, `users(1)──(N)uploads`, `uploads(1)──(N)transactions`,
`categories(1)──(N)transactions`. Every query that touches `transactions` or
`uploads` is scoped with `WHERE user_id = <jwt subject>`, so data isolation
is enforced at the ORM query level, not just the UI.

## 4. Request Flow: Statement Upload (CSV or PDF)

1. Browser sends `multipart/form-data` to `POST /api/uploads` with the JWT.
   `ALLOWED_UPLOAD_EXTENSIONS` accepts `.csv` and `.pdf`.
2. Flask checks `Content-Length` against `MAX_CONTENT_LENGTH` (10MB) before
   touching the file — oversized uploads are rejected with `413` before any
   parsing work happens.
3. Parsing branches on file extension:
   - **`.csv`**: `CSVParser` first tries the file as-is (header = row 0). If
     the resulting columns don't look like a transaction table, it scans the
     first 25 raw rows for one that does — this handles real-world exports
     (e.g. IDFC FIRST Bank) that put a title/account-summary block above the
     actual header row.
   - **`.pdf`**: `services/pdf_parser.py` uses `pdfplumber` to find the
     transaction table's bordered grid across every page (skipping the
     small Opening/Total Debit/Total Credit/Closing Balance summary block
     most bank statement PDFs print above it, and de-duplicating the header
     row that gets reprinted on every page), reconstructs it as CSV text,
     and hands that straight to the same `CSVParser` a `.csv` upload uses —
     so a PDF statement gets identical date-format handling, Debit/Credit
     resolution, and validation, with no separate parsing logic to keep in
     sync. A narration that wraps onto a second line inside its own PDF
     table cell (common in real statements) comes back from `pdfplumber` as
     one cell with an embedded newline, which is flattened before handing
     off to `CSVParser` — this is a different case from the CSV
     continuation-row problem below and is handled directly in
     `pdf_parser.py`.

   Both paths converge on the same validation: date format, non-empty
   description, positive numeric amount (blank cells in a split
   Debit/Credit layout are explicitly rejected rather than silently stored
   as `NaN`), and a SHA-256 hash of `date|description|amount` per row. For
   CSV specifically, a narration wrapped onto extra plain-text rows below a
   transaction (every column blank except the description) is merged into
   the previous row rather than treated as an invalid row.
4. **If the deterministic parser still can't read the file** (a layout it
   has no rule for, or a PDF with no extractable table grid) **and the
   configured AI provider is ready** (see "AI Provider Architecture"
   below), `services/llm_extractor.py` sends the raw file text — extracted
   from the PDF via `pdf_parser.extract_raw_text()` when the upload was a
   PDF, or the CSV bytes directly otherwise — to the model with a
   JSON-mode-constrained prompt, and normalizes the result into the same
   transaction shape the deterministic parser produces, including the
   identical hash formula, so duplicate detection works the same
   regardless of which path parsed a given row. This is opt-in and
   best-effort: without a provider configured, or if the AI call itself
   fails, the endpoint returns the original deterministic parsing error
   unchanged. See the Security Considerations section below for the
   privacy trade-off this introduces.
5. **If the PDF has no extractable text at all** — `pdf_parser.has_extractable_text()`
   checks `page.chars` across every page — a text-based AI attempt has
   nothing to read, so the upload skips straight to a third tier: vision-
   based extraction. Some banks' PDF generators (observed with HDFC) draw
   the statement's "text" as vector glyph outlines with zero underlying
   character data, which is functionally identical to a scanned image for
   data-extraction purposes even though there's no single large embedded
   raster image to point at. `pdf_parser.render_pages_as_images()`
   rasterizes each page (via `pdfplumber`'s `pypdfium2`-backed renderer,
   capped at 6 pages) to a PNG, and `llm_extractor.extract_transactions_from_images()`
   sends those images to a **vision-capable** model — a separate model
   from the text model, configured via `AI_VISION_MODEL`/
   `ai_client.get_vision_model()`, since most fast text models aren't
   multimodal. For a PDF that does have some text but where the
   text-based attempt still fails, vision is tried once more as a final
   fallback before giving up.
6. `DuplicateDetector` removes duplicates within the file itself; a second
   check against `transactions.tx_hash` for that user removes duplicates
   against previously-imported data. A `(user_id, tx_hash)` unique
   constraint is the last line of defense against a race between two
   concurrent uploads.
7. `TransactionCategorizer` assigns a category + confidence to each
   surviving row.
8. Rows are bulk-inserted inside a single DB transaction; the `uploads` row
   is updated with `parsed_count`/`duplicate_count` and committed together,
   so a partial failure never leaves an `uploads` row claiming success with
   no matching transactions.

**Testing caveat**: PDF parsing is verified against synthetic bank-statement-
shaped PDFs generated with `reportlab` in `tests/test_pdf_parser.py` and
`tests/test_pdf_upload.py`, not against real customer statement files
(since none are committed to the repo) - but each fixture is built to
reproduce a specific real-world layout observed while building this
feature: a 7-column, multi-page, wrapped-narration-cell format matching
IDFC FIRST; a "Withdrawal Amt."/"Deposit Amt." header matching HDFC; and
an image-only PDF (a raster image embedded with zero real text objects)
that reproduces the same `page.chars == 0` condition seen on an actual
HDFC statement, to exercise the vision fallback without needing a real,
non-redistributable bank file. Table extraction quality on `pdfplumber`'s
default line-detection strategy depends on the PDF being genuine
selectable text with a real vector grid; a PDF with no extractable text
at all - whether a true scanned image or, as seen with HDFC, vector-drawn
glyph outlines with no character data - falls through to the vision-based
AI fallback described above (or the deterministic error, if AI isn't
configured).

## 5. AI Provider Architecture (open-source models only)

Every AI feature in this app (AI Assistant chat, goal savings advice,
CSV/PDF AI-parsing fallback) runs on an **open-source model** through a
single shared client, `services/ai_client.py` — there is no dependency on
a paid Anthropic/OpenAI API anywhere in the codebase.

- **Local development (`AI_PROVIDER=ollama`, the default):** talks to a
  locally-running [Ollama](https://ollama.com) server (`ollama serve`,
  default `http://localhost:11434`) running a model you've pulled (e.g.
  `ollama pull llama3.1`). Free, fully local, no API key, no data leaves
  your machine. If Ollama isn't running, requests fail with a clear
  connection-refused error rather than a silent fallback.
- **Production (`AI_PROVIDER=groq`):** Ollama **cannot** be deployed to a
  serverless or static host (Vercel, GitHub Pages, Netlify, etc.) — it is
  a long-running process that keeps multi-GB model weights resident in
  memory and needs persistent disk, none of which those platforms
  provide. Instead, production points at [Groq](https://console.groq.com),
  which serves the same class of open-source models (Llama 3.x, etc.)
  behind a free-tier, OpenAI-compatible API. Requires `GROQ_API_KEY`.
- Both providers implement the OpenAI chat-completions wire format, so
  `chat_advisor.py`, `goal_advisor.py`, and `llm_extractor.py` are
  provider-agnostic — only `AI_PROVIDER`/`AI_BASE_URL`/`AI_MODEL`/
  `GROQ_API_KEY` change between environments, never the service code.
- **Structured output**: instead of Anthropic-style schema-constrained
  decoding, extraction/advice prompts use `response_format:
  {"type": "json_object"}` (JSON mode) — the one structured-output
  feature reliably supported across both Ollama and Groq — with the exact
  expected shape spelled out in the prompt, and the parsed JSON validated
  in Python afterward (`_normalize()` in `llm_extractor.py`,
  `_normalize_insight()` in `goal_advisor.py`) rather than trusted
  blindly, since smaller open-source models follow an implied schema less
  reliably than a schema-constrained response did.
- Set `AI_PROVIDER=none` to disable all AI features entirely.

## 6. Security Considerations

- **Authentication:** JWT access tokens (1h) + refresh tokens (30d),
  passwords hashed with bcrypt. Every data-bearing endpoint is decorated
  with `@jwt_required()`.
- **Data isolation:** all reads/writes are filtered by `user_id` derived
  from the JWT subject claim — never from a client-supplied ID.
- **Injection safety:** SQLAlchemy's ORM parameterizes all queries (no
  string-built SQL). CSV values that start with `=`, `+`, `-`, `@` (formula
  injection vectors when a report is later opened in Excel) are stripped.
- **Upload hardening:** file extension allowlist (`.csv` and `.pdf` only),
  size cap enforced at the Flask layer, and malformed files are caught and
  reported without crashing the request (`CSVParsingError`/`PDFParsingError`
  → `422` with a message, never a raw stack trace).
- **CORS:** restricted to the configured frontend origin via `Flask-CORS`.
- **Transport:** the app is designed to sit behind HTTPS in production
  (session cookies configured `Secure`/`HttpOnly` where cookies are used);
  in this deployment JWTs are bearer tokens over HTTPS rather than cookies.
- **AI-assisted parsing/chat/advice (opt-in) sends data to a third party
  only in production.** Locally (`AI_PROVIDER=ollama`), nothing leaves
  your machine. In production (`AI_PROVIDER=groq`), when a feature is
  used, the relevant retrieved financial context or raw (truncated)
  statement text — potentially including account numbers, merchant names,
  and balances — is sent to Groq's API for that one request. This only
  happens when a feature is actually used, and is fully disabled by
  setting `AI_PROVIDER=none`. Before enabling this in a real deployment
  handling real bank data, review Groq's data-handling terms and your own
  regulatory obligations (e.g. data residency, PCI scope) for sending
  financial data to a third-party API.

## 7. Known Trade-offs (see SELF_ASSESSMENT.md for the full discussion)

- CSV parsing/categorization runs **synchronously** in the request handler.
  This is simple and fine at the file sizes a personal bank statement
  produces (capped at 10MB), but a production system ingesting much larger
  files would move this to a background worker (Celery/RQ) and poll for
  status instead.
- The repository contains an earlier blueprint-style scaffold under
  `backend/app/` (auth-only) that is **not** the server that runs — the
  live backend is the self-contained `backend/main.py`. This is called out
  explicitly so it isn't mistaken for dead/duplicate functionality.
