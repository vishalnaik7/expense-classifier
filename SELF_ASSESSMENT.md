# Self-Assessment

## Key design choices and trade-offs

**Single-file Flask backend over the blueprint scaffold.** The repository
already contained two partial backends: a blueprint-based package
(`backend/app/`) with only auth wired up, and a self-contained
`backend/main.py` that already had working auth, transactions, and
analytics endpoints and was the one actually referenced by the frontend and
`docker-compose`. Rather than reconciling both into the "cleaner" package
structure — which risked breaking the working auth flow for a large
mechanical refactor — I extended the version that was actually running.
The trade-off is that `main.py` is a large single file; the mitigation was
to keep genuinely reusable logic (CSV parsing, categorization) in their own
`services/` modules rather than inlining everything.

**Synchronous CSV processing.** Parsing, deduplication, and categorization
all happen inline in the `POST /api/uploads` request rather than being
handed off to a background worker. For a personal/family bank-statement
tool with a 10MB upload cap, this keeps the system simple to run and reason
about, and the user gets an immediate pass/fail result instead of having to
poll a job status. The explicit trade-off: a much larger CSV (tens of MB,
enterprise-scale) would block a worker thread for the duration of parsing.
Celery/RQ with a job-status endpoint is the natural next step if file sizes
grow.

**Deterministic parsing first, LLM extraction only as an opt-in fallback -
and on an open-source model, not a paid API.** Real bank exports (tested
against an IDFC FIRST Bank statement) often have title/account-summary
rows above the actual header, which the original parser couldn't skip.
Rather than routing every upload through an LLM - which would be
non-deterministic, slower, and would send every user's raw statement text
off-server by default - the parser first tries to auto-detect the real
header row within the first 25 lines (`services/csv_parser.py`). Only
when that still fails, and only if the configured AI provider is ready
(`services/ai_client.py` - Ollama locally, Groq in production, see
`ARCHITECTURE.md`), does the upload fall through to
`services/llm_extractor.py`, which asks the model to extract the
transaction table via a JSON-mode-constrained request. The two paths
produce identically-shaped transaction dicts (same hash formula), so
duplicate detection and categorization behave the same regardless of
which one parsed a given file. The trade-off is real and disclosed in
`ARCHITECTURE.md`: the production fallback path sends statement text
off-server to Groq, which matters for a fintech app - hence opt-in rather
than default-on, and fully local (no third party at all) in development.

**Rule-based categorization over ML.** A keyword/regex rule engine
(`services/categorizer.py`) was already in place and is deterministic,
explainable (each result carries a confidence score), and requires no
training data or model hosting — appropriate for a personal finance tool
where users need to trust *why* something was categorized a certain way.
The trade-off is it won't generalize to merchants outside its keyword
lists; the `confidence` score on each transaction is exposed specifically
so a future "review low-confidence transactions" UI is possible without
a schema change.

**Duplicate detection via content hash, not upload metadata.** Transactions
are deduplicated by `sha256(date|description|amount)`, checked both within
a single file and against everything already stored for that user, with a
DB-level unique constraint as a final backstop against races. This means
re-uploading the same statement (a very common real-world action) is safe
and idempotent, and overlapping date ranges across two exports from the
same bank don't create duplicate spending totals.

## What worked well

- Reusing the already-written `CSVParser`/`TransactionCategorizer` classes
  paid off immediately — they were well-structured and only needed to be
  wired up, not rewritten.
- The hash-based duplicate detection is simple and testable in isolation
  (no DB required) and composes cleanly with the DB-level constraint.
- Keeping export (`/api/export/csv`, `/api/export/pdf`) and analytics
  sharing the same period/date-range filter logic (`_resolve_period_range`)
  meant "download exactly what I'm looking at" behavior came for free.

## What can be improved

- **Background processing** for large uploads, as noted above.
- **Category correction feedback loop:** `PUT /api/transactions/<id>`
  already lets a user re-categorize a transaction, but nothing currently
  learns from those corrections to improve future categorization of
  similar merchants for that user.
- **Refresh-token revocation on logout** is stubbed (`backend/app/routes/auth.py`
  has a blacklist table) but the live `main.py` backend doesn't currently
  implement token revocation — logout is client-side only (tokens are
  discarded, not invalidated server-side) until the access token naturally
  expires (1 hour).
- **Two backend scaffolds in one repo** is confusing for anyone new to the
  codebase. Documented clearly in `ARCHITECTURE.md`, but the cleaner fix
  would be to either delete the unused `backend/app/` package or finish
  migrating `main.py` into it.

## Difficulties and edge cases encountered

- **Malformed/corrupt CSVs:** handled by `CSVParser` raising a typed
  `CSVParsingError` with a specific message (missing columns, unparseable
  dates, non-numeric amounts); the upload endpoint catches this and returns
  `422` with the detail, and records the failure on the `uploads` row so
  it's visible in upload history rather than silently disappearing.
- **Category distribution collapsing to ~98% "Other" on a real statement:**
  investigating a user's actual bank export surfaced four independent bugs
  stacked on top of each other in `services/categorizer.py` and
  `main.py`'s category seeding:
  1. A floating-point precision bug — `0.7 + 2*0.1` evaluates to
     `0.8999999999999999` in Python, not exactly `0.9`, so any transaction
     matching exactly two keywords silently missed the `confidence >= 0.9`
     short-circuit and fell through to a much weaker match tier. Fixed by
     rounding the computed confidence before comparison.
  2. `categorize()` only trusted the keyword-match tier above that 0.9 bar;
     a single strong, specific keyword match (e.g. `"irctc"`, scoring 0.8)
     was discarded in favor of a generic pattern match from an unrelated
     category (e.g. `"upi"`, scoring a flat 0.75) purely because patterns
     were checked second. Fixed by comparing the two tiers and keeping
     whichever actually scored higher.
  3. `"icici"` and `"hdfc"` were listed as **Insurance** keywords —
     reasonable for a policy purchase, but those bank names appear in
     nearly every UPI transfer narration as the *counterparty's* bank,
     unrelated to insurance. Removed the bare bank-name keywords.
  4. Most fundamentally: `main.py`'s category-seeding list was missing
     `Transfer` and `Salary` entirely (11 of the 13 categories the
     categorizer can actually return were seeded). Since
     `_get_or_create_category` falls back to "Other" for any category name
     it can't find in the database, *every* transaction the categorizer
     correctly identified as a transfer or salary/income was silently
     downgraded to "Other" at save time — independent of the categorizer
     bugs above. This alone explains most of the effect, since UPI
     narrations contain "upi" or "transfer"-shaped hints in a large
     fraction of a statement's rows.

- **A real bug found via testing:** the original header-normalization logic
  in `CSVParser` would match a lone `"Debit"` column to the `amount` field
  and then, in a later iteration over the same rule table, silently
  re-map it to a literal `debit` column — causing the required `amount`
  column to appear "missing" for a very common bank export format. Caught
  by a unit test (`test_header_case_and_alias_normalization`) and fixed by
  making header assignment first-match-wins instead of last-match-wins.
- **Duplicate transactions across uploads:** solved with the content-hash
  approach described above, verified with an integration test that uploads
  the same file twice and asserts zero new rows on the second pass.
- **Session expiration mid-upload:** rather than forcing an immediate
  redirect (which would silently discard the user's selected file), the
  upload page catches `401` specifically, keeps the selected file in
  component state, and shows a banner explaining the session expired with
  a link to log back in and retry — instead of the generic global
  "redirect to /login on any 401" behavior used elsewhere in the app.
- **Large file / oversized upload:** enforced with `MAX_CONTENT_LENGTH` at
  the Flask layer (returns `413` before the file is even fully read into
  memory) plus a client-side size check before the upload request is sent,
  so the user gets instant feedback instead of waiting for a round trip.
- **Cross-user data leakage:** every transaction/upload/analytics query is
  filtered by the JWT-derived `user_id`; verified with an integration test
  that uploads data as one user and confirms a second user's transaction
  list stays empty.
- **Windows dev environment friction:** the existing `main.py` used emoji
  in `print()` statements, which crashes on Windows consoles using the
  default `cp1252` encoding (`UnicodeEncodeError`). Removed the emoji from
  log output so `python main.py` runs on Windows without extra environment
  configuration.
