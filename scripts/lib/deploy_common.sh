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

public_origin() {
  local scheme="$1"
  local host="$2"
  local port="$3"
  local default_port="$4"
  if [[ "$port" == "$default_port" ]]; then
    printf '%s://%s' "$scheme" "$host"
  else
    printf '%s://%s:%s' "$scheme" "$host" "$port"
  fi
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
    local deploy_home
    deploy_home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
    runuser -u "$DEPLOY_USER" -- env HOME="$deploy_home" "$@"
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
  run_as_deploy_user "$ROOT_DIR/.venv/bin/python" -c \
    'import pathlib, sys; expected = pathlib.Path(sys.argv[1]).resolve(); actual = pathlib.Path(sys.prefix).resolve(); raise SystemExit(0 if sys.prefix != sys.base_prefix and actual == expected else f"Expected virtual environment {expected}, got {actual}")' \
    "$ROOT_DIR/.venv"
  run_as_deploy_user "$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
  run_as_deploy_user "$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"

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
    printf 'HTTP_PORT=%q\n' "$HTTP_PORT"
    printf 'HTTPS_PORT=%q\n' "$HTTPS_PORT"
    printf 'FRONTEND_ORIGIN=%q\n' "$FRONTEND_ORIGIN"
    printf 'PUBLIC_API_URL=%q\n' "$PUBLIC_API_URL"
    printf 'COOKIE_SECURE=%q\n' "$COOKIE_SECURE"
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
Environment="API_ROOT_PATH=/api"
Environment="COOKIE_SECURE=${COOKIE_SECURE}"
Environment="FRONTEND_HOST=${BIND_HOST}"
Environment="FRONTEND_PORT=${FRONTEND_PORT}"
Environment="NEXT_PUBLIC_API_BASE_URL=${PUBLIC_API_URL}"
Environment="CORS_ORIGINS=${FRONTEND_ORIGIN}"
Environment="VIRTUAL_ENV=${ROOT_DIR}/.venv"
Environment="PATH=${ROOT_DIR}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=${ROOT_DIR}/.venv/bin/uvicorn app.main:app --host ${BIND_HOST} --port ${BACKEND_PORT} --root-path /api
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

install_reverse_proxy() {
  log "Configuring nginx reverse proxy"
  local temp_file config_file cert_dir cert_file key_file https_suffix san_value
  temp_file="$(mktemp)"
  config_file="/etc/nginx/conf.d/${SERVICE_PREFIX}.conf"
  cert_dir="/etc/${SERVICE_PREFIX}/tls"
  cert_file="$cert_dir/${PUBLIC_HOST}.crt"
  key_file="$cert_dir/${PUBLIC_HOST}.key"
  https_suffix=""
  if [[ "$HTTPS_PORT" != "443" ]]; then https_suffix=":${HTTPS_PORT}"; fi
  if [[ "$PUBLIC_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    san_value="IP:${PUBLIC_HOST}"
  else
    san_value="DNS:${PUBLIC_HOST}"
  fi

  if [[ "$PUBLIC_SCHEME" == "https" ]]; then
    run_root install -d -m 0755 "$cert_dir"
    if ! run_root test -s "$cert_file" || ! run_root test -s "$key_file"; then
      log "Generating a self-signed TLS certificate for ${PUBLIC_HOST}"
      run_root openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
        -keyout "$key_file" -out "$cert_file" \
        -subj "/CN=${PUBLIC_HOST}" -addext "subjectAltName=${san_value}"
      run_root chmod 0600 "$key_file"
      run_root chmod 0644 "$cert_file"
    fi
    cat > "$temp_file" <<EOF
server {
    listen ${HTTP_PORT};
    server_name ${PUBLIC_HOST};
    return 301 https://\$host${https_suffix}\$request_uri;
}

server {
    listen ${HTTPS_PORT} ssl;
    server_name ${PUBLIC_HOST};

    ssl_certificate ${cert_file};
    ssl_certificate_key ${key_file};
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size ${MAX_UPLOAD_MB:-25}m;

    location = /api { return 308 /api/; }
    location /api/ {
        proxy_pass http://${BIND_HOST}:${BACKEND_PORT}/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
    }

    location / {
        proxy_pass http://${BIND_HOST}:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
EOF
  else
    cat > "$temp_file" <<EOF
server {
    listen ${HTTP_PORT};
    server_name ${PUBLIC_HOST};
    client_max_body_size ${MAX_UPLOAD_MB:-25}m;

    location = /api { return 308 /api/; }
    location /api/ {
        proxy_pass http://${BIND_HOST}:${BACKEND_PORT}/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
    }

    location / {
        proxy_pass http://${BIND_HOST}:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
EOF
  fi

  run_root install -m 0644 "$temp_file" "$config_file"
  rm -f "$temp_file"
  run_root nginx -t
  run_root systemctl enable --now nginx
  run_root systemctl reload nginx

  if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    run_root firewall-cmd --permanent --add-port="${HTTP_PORT}/tcp"
    if [[ "$PUBLIC_SCHEME" == "https" ]]; then run_root firewall-cmd --permanent --add-port="${HTTPS_PORT}/tcp"; fi
    run_root firewall-cmd --reload
  elif command -v ufw >/dev/null 2>&1 && run_root ufw status | grep -q '^Status: active'; then
    run_root ufw allow "${HTTP_PORT}/tcp"
    if [[ "$PUBLIC_SCHEME" == "https" ]]; then run_root ufw allow "${HTTPS_PORT}/tcp"; fi
  fi
}

restart_services() {
  log "Starting application services"
  run_root systemctl restart "${SERVICE_PREFIX}-backend.service" "${SERVICE_PREFIX}-frontend.service"
  run_root systemctl --no-pager --full status "${SERVICE_PREFIX}-backend.service" "${SERVICE_PREFIX}-frontend.service"
}

print_deployment_summary() {
  local storage_dir="${UPLOAD_STORAGE_DIR:-backend/storage/imports}"
  local repository_url revision
  if [[ "$storage_dir" != /* ]]; then storage_dir="$ROOT_DIR/$storage_dir"; fi
  repository_url="$(git -C "$ROOT_DIR" config --get remote.origin.url 2>/dev/null || printf 'unknown')"
  revision="$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
  echo
  echo "================ Deployment complete ========================"
  printf '%-28s %s\n' "Repository:" "$repository_url"
  printf '%-28s %s\n' "Deployed revision:" "$revision"
  printf '%-28s %s\n' "Application user:" "$DEPLOY_USER"
  printf '%-28s %s\n' "Application directory:" "$ROOT_DIR"
  printf '%-28s %s\n' "Environment file:" "$ROOT_DIR/.env (mode 0600)"
  printf '%-28s %s\n' "Deployment config:" "$ROOT_DIR/.deploy/config"
  printf '%-28s %s\n' "nginx configuration:" "/etc/nginx/conf.d/${SERVICE_PREFIX}.conf"
  printf '%-28s %s\n' "Python virtualenv:" "$ROOT_DIR/.venv"
  printf '%-28s %s\n' "Upload storage:" "$storage_dir"
  printf '%-28s %s\n' "Frontend URL:" "$FRONTEND_ORIGIN"
  printf '%-28s %s\n' "API URL:" "$PUBLIC_API_URL"
  printf '%-28s %s\n' "API documentation:" "${PUBLIC_API_URL%/}/docs"
  printf '%-28s %s\n' "Internal frontend:" "${BIND_HOST}:${FRONTEND_PORT}"
  printf '%-28s %s\n' "Internal backend:" "${BIND_HOST}:${BACKEND_PORT}"
  printf '%-28s %s\n' "nginx HTTP port:" "$HTTP_PORT"
  if [[ "$PUBLIC_SCHEME" == "https" ]]; then
    printf '%-28s %s\n' "nginx HTTPS port:" "$HTTPS_PORT"
    printf '%-28s %s\n' "TLS certificate:" "/etc/${SERVICE_PREFIX}/tls/${PUBLIC_HOST}.crt"
    printf '%-28s %s\n' "TLS private key:" "/etc/${SERVICE_PREFIX}/tls/${PUBLIC_HOST}.key"
    printf '%-28s %s\n' "Certificate trust:" "self-signed; browser trust warning expected"
  fi
  printf '%-28s %s\n' "PostgreSQL target:" "${DATABASE_HOST}:${DATABASE_PORT}/${DATABASE_NAME}"
  printf '%-28s %s\n' "PostgreSQL user:" "$DATABASE_USER"
  printf '%-28s %s\n' "PostgreSQL SSL mode:" "${DATABASE_SSL_MODE:-disable}"
  printf '%-28s %s\n' "Database password:" "[stored in .env, not displayed]"
  printf '%-28s %s\n' "Application secret:" "[stored in .env, not displayed]"
  printf '%-28s %s\n' "Backend service:" "${SERVICE_PREFIX}-backend.service"
  printf '%-28s %s\n' "Frontend service:" "${SERVICE_PREFIX}-frontend.service"
  echo "--------------------------------------------------------------"
  echo "Status:  sudo systemctl status ${SERVICE_PREFIX}-backend ${SERVICE_PREFIX}-frontend"
  echo "Logs:    sudo journalctl -u ${SERVICE_PREFIX}-backend -u ${SERVICE_PREFIX}-frontend -f"
  echo "Update:  sudo ${ROOT_DIR}/scripts/update.sh"
  echo "Restart: sudo systemctl restart ${SERVICE_PREFIX}-backend ${SERVICE_PREFIX}-frontend"
  echo "=============================================================="
}
