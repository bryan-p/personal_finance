#!/usr/bin/env bash

# Shared deployment functions. This file is sourced by deploy.sh and update.sh.

die() {
  echo "Error: $*" >&2
  exit 1
}

log() {
  echo
  echo "==> $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_port() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "$name must be a number"
  (( value >= 1 && value <= 65535 )) || die "$name must be between 1 and 65535"
}

validate_service_prefix() {
  [[ "$1" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "Service name may only contain letters, numbers, dots, underscores, @, and hyphens"
}

validate_systemd_value() {
  local name="$1"
  local value="$2"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *'"'* ]] || die "$name contains characters that cannot be written safely to a systemd unit"
}

run_root() {
  if (( EUID == 0 )); then
    "$@"
  else
    sudo "$@"
  fi
}

run_as_deploy_user() {
  if [[ "$(id -un)" == "$DEPLOY_USER" ]]; then
    "$@"
  elif (( EUID == 0 )); then
    runuser -u "$DEPLOY_USER" -- "$@"
  else
    sudo -u "$DEPLOY_USER" -H "$@"
  fi
}

load_app_env() {
  [[ -f "$ROOT_DIR/.env" ]] || die "Missing $ROOT_DIR/.env. Copy .env.example and configure it first."
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
}

validate_app_env() {
  local required=(DATABASE_HOST DATABASE_PORT DATABASE_NAME DATABASE_USER DATABASE_PASSWORD SECRET_KEY)
  local name
  for name in "${required[@]}"; do
    [[ -n "${!name:-}" ]] || die "Missing required .env variable: $name"
  done
  [[ ${#SECRET_KEY} -ge 12 ]] || die "SECRET_KEY must contain at least 12 characters"
}

install_app_dependencies() {
  log "Installing Python dependencies"
  if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    run_as_deploy_user python3 -m venv "$ROOT_DIR/.venv"
  fi
  run_as_deploy_user "$ROOT_DIR/.venv/bin/pip" install --upgrade pip
  run_as_deploy_user "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"

  log "Installing frontend dependencies"
  if [[ -f "$ROOT_DIR/frontend/package-lock.json" ]]; then
    run_as_deploy_user npm --prefix "$ROOT_DIR/frontend" ci
  else
    run_as_deploy_user npm --prefix "$ROOT_DIR/frontend" install
  fi
}

build_frontend() {
  log "Building the Next.js frontend"
  run_as_deploy_user env \
    NEXT_PUBLIC_API_BASE_URL="$PUBLIC_API_URL" \
    npm --prefix "$ROOT_DIR/frontend" run build
}

prepare_storage() {
  local storage_dir="${UPLOAD_STORAGE_DIR:-backend/storage/imports}"
  if [[ "$storage_dir" != /* ]]; then
    storage_dir="$ROOT_DIR/$storage_dir"
  fi
  run_as_deploy_user mkdir -p "$storage_dir"
}

verify_database_and_migrate() {
  log "Verifying PostgreSQL and running migrations"
  run_as_deploy_user env \
    APP_ENV=production \
    BACKEND_RELOAD=false \
    FRONTEND_HOST="$BIND_HOST" \
    FRONTEND_PORT="$FRONTEND_PORT" \
    BACKEND_HOST="$BIND_HOST" \
    BACKEND_PORT="$BACKEND_PORT" \
    NEXT_PUBLIC_API_BASE_URL="$PUBLIC_API_URL" \
    CORS_ORIGINS="$FRONTEND_ORIGIN" \
    "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/check_db.py"
  run_as_deploy_user env \
    APP_ENV=production \
    BACKEND_RELOAD=false \
    FRONTEND_HOST="$BIND_HOST" \
    FRONTEND_PORT="$FRONTEND_PORT" \
    BACKEND_HOST="$BIND_HOST" \
    BACKEND_PORT="$BACKEND_PORT" \
    NEXT_PUBLIC_API_BASE_URL="$PUBLIC_API_URL" \
    CORS_ORIGINS="$FRONTEND_ORIGIN" \
    "$ROOT_DIR/scripts/run_migrations.sh"
}

write_deploy_config() {
  run_as_deploy_user mkdir -p "$ROOT_DIR/.deploy"
  local temp_file
  temp_file="$(mktemp)"
  {
    printf 'DEPLOY_USER=%q\n' "$DEPLOY_USER"
    printf 'SERVICE_PREFIX=%q\n' "$SERVICE_PREFIX"
    printf 'BIND_HOST=%q\n' "$BIND_HOST"
    printf 'PUBLIC_HOST=%q\n' "$PUBLIC_HOST"
    printf 'PUBLIC_SCHEME=%q\n' "$PUBLIC_SCHEME"
    printf 'FRONTEND_PORT=%q\n' "$FRONTEND_PORT"
    printf 'BACKEND_PORT=%q\n' "$BACKEND_PORT"
    printf 'FRONTEND_ORIGIN=%q\n' "$FRONTEND_ORIGIN"
    printf 'PUBLIC_API_URL=%q\n' "$PUBLIC_API_URL"
  } > "$temp_file"
  if [[ "$(id -un)" == "$DEPLOY_USER" ]]; then
    install -m 0600 "$temp_file" "$ROOT_DIR/.deploy/config"
  else
    run_root install -o "$DEPLOY_USER" -g "$(id -gn "$DEPLOY_USER")" -m 0600 "$temp_file" "$ROOT_DIR/.deploy/config"
  fi
  rm -f "$temp_file"
}

install_systemd_services() {
  log "Installing systemd services"
  local npm_path node_dir temp_dir backend_unit frontend_unit
  npm_path="$(command -v npm)"
  node_dir="$(dirname "$(command -v node)")"
  temp_dir="$(mktemp -d)"
  backend_unit="$temp_dir/${SERVICE_PREFIX}-backend.service"
  frontend_unit="$temp_dir/${SERVICE_PREFIX}-frontend.service"

  cat > "$backend_unit" <<EOF
[Unit]
Description=${SERVICE_PREFIX} FastAPI backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${DEPLOY_USER}
WorkingDirectory=${ROOT_DIR}/backend
EnvironmentFile=${ROOT_DIR}/.env
Environment="APP_ENV=production"
Environment="BACKEND_HOST=${BIND_HOST}"
Environment="BACKEND_PORT=${BACKEND_PORT}"
Environment="BACKEND_RELOAD=false"
Environment="FRONTEND_HOST=${BIND_HOST}"
Environment="FRONTEND_PORT=${FRONTEND_PORT}"
Environment="NEXT_PUBLIC_API_BASE_URL=${PUBLIC_API_URL}"
Environment="CORS_ORIGINS=${FRONTEND_ORIGIN}"
ExecStart=${ROOT_DIR}/.venv/bin/uvicorn app.main:app --host ${BIND_HOST} --port ${BACKEND_PORT}
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

  cat > "$frontend_unit" <<EOF
[Unit]
Description=${SERVICE_PREFIX} Next.js frontend
After=network-online.target ${SERVICE_PREFIX}-backend.service
Wants=network-online.target

[Service]
Type=simple
User=${DEPLOY_USER}
WorkingDirectory=${ROOT_DIR}/frontend
EnvironmentFile=${ROOT_DIR}/.env
Environment="NODE_ENV=production"
Environment="FRONTEND_HOST=${BIND_HOST}"
Environment="FRONTEND_PORT=${FRONTEND_PORT}"
Environment="NEXT_PUBLIC_API_BASE_URL=${PUBLIC_API_URL}"
Environment="PATH=${node_dir}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=${npm_path} run start -- --hostname ${BIND_HOST} --port ${FRONTEND_PORT}
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

  run_root install -m 0644 "$backend_unit" "/etc/systemd/system/${SERVICE_PREFIX}-backend.service"
  run_root install -m 0644 "$frontend_unit" "/etc/systemd/system/${SERVICE_PREFIX}-frontend.service"
  rm -rf "$temp_dir"
  run_root systemctl daemon-reload
  run_root systemctl enable "${SERVICE_PREFIX}-backend.service" "${SERVICE_PREFIX}-frontend.service"
}

restart_services() {
  log "Starting application services"
  run_root systemctl restart "${SERVICE_PREFIX}-backend.service" "${SERVICE_PREFIX}-frontend.service"
  run_root systemctl --no-pager --full status "${SERVICE_PREFIX}-backend.service" "${SERVICE_PREFIX}-frontend.service"
}

print_deployment_summary() {
  echo
  echo "Deployment complete."
  echo "Frontend: ${FRONTEND_ORIGIN}"
  echo "Backend:  ${PUBLIC_API_URL}"
  echo
  echo "Service status: sudo systemctl status ${SERVICE_PREFIX}-backend ${SERVICE_PREFIX}-frontend"
  echo "Follow logs:    sudo journalctl -u ${SERVICE_PREFIX}-backend -u ${SERVICE_PREFIX}-frontend -f"
}
