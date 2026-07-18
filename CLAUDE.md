## Codebase Overview

Ledgerly — a local-first personal finance tracker. Users import bank CSV statements (multi-step upload → column mapping → normalize → review → confirm), categorize transactions via user-defined rules, track recurring subscriptions, view spending dashboards, and delete drafts/transactions/imports/accounts (hard deletes with staged CSV cleanup; institutions are non-deletable). No third-party bank integration, budgets, or cloud sync.

**Stack**: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL (psycopg3) + Pydantic v2 backend; Next.js 15 (App Router, all Client Components) + React 19 + TypeScript frontend, no CSS framework (hand-written `globals.css`). Cookie-based JWT session auth.

**Structure**: `backend/app/{api,core,models.py,schemas.py,services}` (routers → services → SQLAlchemy models); `frontend/src/app/(app)/*` page-per-route with `lib/api.ts` as the sole backend client; `scripts/` holds dev launcher (`dev.sh`) and production deploy/update tooling (`deploy.sh`, `update.sh`, `lib/deploy_common.sh`).

For detailed architecture, data model, request/deploy flows, and gotchas, see [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).
