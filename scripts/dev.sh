#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and update the local values." >&2
  exit 1
fi

set -a
source .env
set +a

required=(DATABASE_HOST DATABASE_PORT DATABASE_NAME DATABASE_USER DATABASE_PASSWORD SECRET_KEY FRONTEND_HOST FRONTEND_PORT BACKEND_HOST BACKEND_PORT NEXT_PUBLIC_API_BASE_URL)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 1
  fi
done

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing Python environment. Run: python3 -m venv .venv && ./.venv/bin/python -m pip install -r backend/requirements.txt" >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "Missing frontend dependencies. Run: npm --prefix frontend install" >&2
  exit 1
fi

./.venv/bin/python scripts/check_db.py
./scripts/run_migrations.sh

cleanup() {
  trap - EXIT INT TERM
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"

reload_args=()
if [[ "${BACKEND_RELOAD:-false}" == "true" ]]; then reload_args=(--reload); fi
(
  cd backend
  exec ../.venv/bin/python -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" "${reload_args[@]}"
) &
BACKEND_PID=$!

npm --prefix frontend run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

wait -n "$BACKEND_PID" "$FRONTEND_PID"
