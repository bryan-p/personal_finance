# Ledgerly — local personal finance manager

Ledgerly is a local-first web app that turns bank and credit-card CSV exports into a single
reviewed transaction ledger. FastAPI handles auth, normalization, rules, duplicate detection,
recurring suggestions, and reporting; Next.js provides the dashboard and import workflow;
PostgreSQL stores all user data locally.

The MVP includes:

- Email/password registration, cookie sessions, and per-user data isolation.
- Parent financial accounts plus optional cards, authorized users, and profiles.
- Starter categories/subcategories, custom categories, provider category mappings, and rules.
- Resumable imports with file hashes, header/provider detection, reusable mappings, draft rows,
  safe card attribution, duplicate flags, inline review, confirmation, and cancellation.
- Confirmed transaction search/edit/filter, filtered CSV export, monthly dashboard, and recurring
  charge suggestions that always require approval.

It does not include budgets, bank APIs, Plaid, PDF/OCR imports, cloud sync, backups, investments,
mobile clients, household sharing, 2FA, rate limiting, or automatic cross-account transfer matching.

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- An already-running PostgreSQL server (the app never starts PostgreSQL)
- A PostgreSQL role that can create the configured database for first-time setup

## Configure `.env`

The repository includes `.env.example`; `.env` is intentionally ignored. Copy the example if
needed and set the local database credentials and a long random `SECRET_KEY`:

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Keep the expected service values unless the ports are already in use:

```env
FRONTEND_HOST=localhost
FRONTEND_PORT=5000
NEXT_PUBLIC_API_BASE_URL=http://localhost:9999
BACKEND_HOST=localhost
BACKEND_PORT=9999
DATABASE_NAME=personal_finance_sol
```

`UPLOAD_STORAGE_DIR` points to ignored local CSV storage. Uploaded originals are never sent to a
third party.

## Install dependencies

One-time setup:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend install
```

## Create the PostgreSQL database

The safe helper reads the database name and credentials from `.env`, connects to the standard
`postgres` maintenance database, and creates only the configured database:

```bash
./.venv/bin/python scripts/create_db.py
```

Equivalent manual command (substitute your configured role and database):

```bash
createdb --host=localhost --port=5432 --username=postgres personal_finance_sol
```

## Run migrations

```bash
./scripts/run_migrations.sh
```

Alembic owns the schema. Add future revisions under `backend/migrations/versions/` and do not use
runtime `create_all` calls in the application.

## Start both services

```bash
./scripts/dev.sh
```

The script validates `.env`, checks required variables and PostgreSQL connectivity, runs pending
migrations, starts both development services, prints their URLs, and stops both when interrupted.

- Frontend: <http://localhost:5000>
- Backend: <http://localhost:9999>
- API docs: <http://localhost:9999/docs>

## Import an unknown provider

1. Add the parent account under **Accounts**.
2. Open **Import CSV**, select the account, and upload the export.
3. Ledgerly parses the header/sample rows, checks the file hash, looks for a saved header signature,
   and otherwise proposes a generic mapping.
4. Confirm or rename the provider, account type, amount convention, required columns, and optional
   category/ID/card/profile columns.
5. Save the mapping. Its normalized header signature is reused for future files with the same
   format; saved mappings can be renamed, reassigned to a provider, or deleted from **Import CSV**.
6. Review every draft row, including rule-applied values, duplicates, exclusions, and card/profile
   assignments, then confirm the import.

Generic mappings handle signed amounts, charge-positive/negative conventions, separate debit and
credit columns, dates, descriptions, merchants, provider categories, IDs, notes, and card/profile
identifiers. Code is only needed for genuinely non-tabular exports, preambles, unrelated tables,
unsupported encodings, PDFs, or custom binary formats.

## Credit card accounts with multiple cards/profiles

Create one parent credit-card account for the statement account, then add each physical card or
authorized user as an instrument beneath it. Do not create a separate financial account per card.
During import, map a masked card number, last-four, cardholder, or account suffix. Ledgerly reduces
identifiers to a masked value/last four, matches an existing instrument, or creates a disabled
`Imported card…` suggestion that can be reviewed and renamed. Full card numbers are not retained.

## Add sample CSV files safely

Put sanitized files under `backend/tests/fixtures/local/`. The folder is ignored to prevent accidental
commits of bank data. Preserve representative headers and replace all transactions, names, dates,
IDs, and card numbers with fictional values. Pure generic formats can be tested directly in the UI;
provider-specific parsers should receive focused fixtures and tests.

Run checks with:

```bash
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
npm audit
```

## Design assumptions

- One local installation may contain multiple login accounts, but every owned row is scoped by
  `user_id`; household sharing is intentionally absent.
- Amounts are positive `NUMERIC(14,2)` values; `direction` carries inflow/outflow meaning.
- Spending is outflow `expense` activity not explicitly excluded. Transfers, card payments, and
  adjustments are excluded automatically when their type is set.
- Exact provider transaction IDs are preferred for deduplication. Otherwise the key combines the
  user, account, optional instrument, dates, amount, direction, and normalized description.
- Exact duplicate files are blocked unless the user explicitly opts to continue. Duplicate rows
  remain visible and are skipped unless explicitly approved.
- Generic keyword detection is intentionally conservative. Ambiguous transactions are drafts and
  are never silently finalized.
- Imported, previously unseen card identifiers create disabled instrument suggestions. This avoids
  silently treating an unverified profile as active.
- Recurring suggestions require at least three similar expenses with a recognizable cadence and
  reasonably stable amount. Suggestions are never auto-approved.
- Calendar months are the MVP reporting period; statement-cycle fields exist for a future view.

## Known limitations

- Provider similarity currently requires an exact normalized header signature; fuzzy saved-mapping
  matching is a next refinement.
- Rules apply the first priority match rather than composing multiple matching rules.
- Merchant-history categorization and cross-account transfer matching are not implemented.
- Batch review supports the API, while richer frontend multi-select controls remain to be added.
- The recurring detector groups normalized merchant/description text exactly; advanced merchant
  aliases are future work.
- The first migration creates the baseline schema from SQLAlchemy metadata. Future schema changes
  should use explicit Alembic operations.
- Development cookies are HTTP-only with `SameSite=Lax` and no `Secure` flag because the app runs on
  local HTTP. If deployed beyond localhost, add HTTPS, secure cookies, CSRF hardening, and rate limits.

## Suggested next development steps

1. Add browser-level tests for registration, account/card creation, and the full import-review flow.
2. Add sanitized real-world CSV fixtures and fuzzy header-signature matching.
3. Add a saved-mapping manager and “create rule from correction” review interaction.
4. Add merchant alias/history categorization and better recurring-series editing.
5. Add explicit Alembic operations for the next schema revision and integration tests against a
   disposable PostgreSQL database.
6. Add statement-cycle reporting, then budgeting and encrypted local backups as separate modules.
