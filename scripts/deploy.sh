#!/usr/bin/env bash
set -euo pipefail

# This file is intentionally self-contained until the repository has been cloned.
# It can be downloaded to a fresh Linux server and run from any directory.

APP_USER="fintracker"
APP_HOME="/srv/fintracker"
DEFAULT_REPO_URL="https://github.com/bryan-p/personal_finance.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bootstrap_die() {
  echo "Error: $*" >&2
  exit 1
}

bootstrap_log() {
  echo
  echo "==> $*"
}

bootstrap_validate_port() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || bootstrap_die "$name must be a number"
  (( value >= 1 && value <= 65535 )) || bootstrap_die "$name must be between 1 and 65535"
}

detect_local_ipv4() {
  local address=""
  if command -v ip >/dev/null 2>&1; then
    address="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit } }')"
  fi
  if [[ -z "$address" ]] && command -v hostname >/dev/null 2>&1; then
    address="$(hostname -I 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && $i !~ /^127\./) { print $i; exit } }')"
  fi
  if [[ -z "$address" ]] && command -v getent >/dev/null 2>&1; then
    address="$(getent ahostsv4 "$(hostname)" 2>/dev/null | awk '$1 !~ /^127\./ { print $1; exit }')"
  fi
  printf '%s' "$address"
}

as_root() {
  if (( EUID == 0 )); then
    "$@"
  else
    sudo "$@"
  fi
}

as_app_user() {
  if [[ "$(id -un)" == "$APP_USER" ]]; then
    "$@"
  elif (( EUID == 0 )); then
    runuser -u "$APP_USER" -- env HOME="$APP_HOME" "$@"
  else
    sudo -u "$APP_USER" -H "$@"
  fi
}

usage() {
  cat <<'EOF'
Usage: sudo ./deploy.sh [options]

Bootstrap a fresh Linux server: install system packages, create the dedicated
fintracker user, clone the GitHub repository into /srv/fintracker, install app
dependencies, build, migrate, install systemd units, and start both services.

Configuration can come from --env-file, database command-line options, or
--interactive. Interactive mode prompts for every generated setting and creates
/srv/fintracker/.env. HTTPS with a self-signed certificate is enabled by default.

Options:
  --interactive           Prompt for repository, network, database, and app settings
  --repo-url URL          Git repository (default: public GitHub repository URL)
  --env-file FILE         Source .env to install with mode 0600
  --frontend-port PORT    Frontend port (default: .env value or 5000)
  --backend-port PORT     Backend port (default: .env value or 9999)
  --http-port PORT        nginx HTTP/redirect port (default: 80)
  --https-port PORT       nginx HTTPS port (default: 443)
  --bind-host HOST        Internal service bind address (default: 127.0.0.1)
  --public-host HOST      Browser-visible hostname or IP (default: local IPv4)
  --scheme SCHEME         Public scheme, http or https (default: https)
  --frontend-origin URL   Full browser-visible frontend origin
  --api-url URL           Full browser-visible backend base URL
  --database-host HOST    PostgreSQL host
  --database-port PORT    PostgreSQL port (default: 5432)
  --database-name NAME    PostgreSQL database name
  --database-user USER    PostgreSQL user
  --database-password PW  PostgreSQL password (prefer interactive or --env-file)
  --database-ssl-mode M   PostgreSQL SSL mode (default: disable)
  --secret-key SECRET     Application signing secret (generated when omitted)
  --max-upload-mb MB      Maximum CSV upload size (default: 25)
  --service-name NAME     systemd service prefix (default: fintracker)
  --skip-system-packages  Do not install OS packages; validate prerequisites only
  --yes                   Accept the printed deployment plan without prompting
  --help                  Show this help

Examples:
  sudo ./deploy.sh --interactive
  sudo ./deploy.sh --env-file ./fintracker.env --public-host finance.example.com
  sudo ./deploy.sh --env-file ./fintracker.env --public-host 192.168.1.20 \
    --frontend-port 5100 --backend-port 10099
EOF
}

for argument in "$@"; do
  if [[ "$argument" == "--help" || "$argument" == "-h" ]]; then
    usage
    exit 0
  fi
done

GIT_REPO_URL="$DEFAULT_REPO_URL"
ENV_SOURCE=""
INTERACTIVE=false
FRONTEND_PORT_OVERRIDE=""
BACKEND_PORT_OVERRIDE=""
HTTP_PORT_OVERRIDE=""
HTTPS_PORT_OVERRIDE=""
BIND_HOST_OVERRIDE=""
PUBLIC_HOST_OVERRIDE=""
PUBLIC_SCHEME_OVERRIDE=""
FRONTEND_ORIGIN_OVERRIDE=""
PUBLIC_API_URL_OVERRIDE=""
SERVICE_PREFIX_OVERRIDE=""
DATABASE_HOST_VALUE="${DATABASE_HOST:-localhost}"
DATABASE_PORT_VALUE="${DATABASE_PORT:-5432}"
DATABASE_NAME_VALUE="${DATABASE_NAME:-personal_finance_sol}"
DATABASE_USER_VALUE="${DATABASE_USER:-postgres}"
DATABASE_PASSWORD_VALUE="${DATABASE_PASSWORD:-}"
DATABASE_SSL_MODE_VALUE="${DATABASE_SSL_MODE:-disable}"
SECRET_KEY_VALUE="${SECRET_KEY:-}"
MAX_UPLOAD_MB_VALUE="${MAX_UPLOAD_MB:-25}"
CONFIG_OPTIONS_PROVIDED=false
INSTALL_SYSTEM_PACKAGES=true
ASSUME_YES=false
SECRET_WAS_GENERATED=false

while (( $# )); do
  case "$1" in
    --interactive) INTERACTIVE=true; shift ;;
    --repo-url) [[ $# -ge 2 ]] || bootstrap_die "--repo-url needs a value"; GIT_REPO_URL="$2"; shift 2 ;;
    --env-file) [[ $# -ge 2 ]] || bootstrap_die "--env-file needs a value"; ENV_SOURCE="$2"; shift 2 ;;
    --frontend-port) [[ $# -ge 2 ]] || bootstrap_die "--frontend-port needs a value"; FRONTEND_PORT_OVERRIDE="$2"; shift 2 ;;
    --backend-port) [[ $# -ge 2 ]] || bootstrap_die "--backend-port needs a value"; BACKEND_PORT_OVERRIDE="$2"; shift 2 ;;
    --http-port) [[ $# -ge 2 ]] || bootstrap_die "--http-port needs a value"; HTTP_PORT_OVERRIDE="$2"; shift 2 ;;
    --https-port) [[ $# -ge 2 ]] || bootstrap_die "--https-port needs a value"; HTTPS_PORT_OVERRIDE="$2"; shift 2 ;;
    --bind-host) [[ $# -ge 2 ]] || bootstrap_die "--bind-host needs a value"; BIND_HOST_OVERRIDE="$2"; shift 2 ;;
    --public-host) [[ $# -ge 2 ]] || bootstrap_die "--public-host needs a value"; PUBLIC_HOST_OVERRIDE="$2"; shift 2 ;;
    --scheme) [[ $# -ge 2 ]] || bootstrap_die "--scheme needs a value"; PUBLIC_SCHEME_OVERRIDE="$2"; shift 2 ;;
    --frontend-origin) [[ $# -ge 2 ]] || bootstrap_die "--frontend-origin needs a value"; FRONTEND_ORIGIN_OVERRIDE="$2"; shift 2 ;;
    --api-url) [[ $# -ge 2 ]] || bootstrap_die "--api-url needs a value"; PUBLIC_API_URL_OVERRIDE="$2"; shift 2 ;;
    --database-host) [[ $# -ge 2 ]] || bootstrap_die "--database-host needs a value"; DATABASE_HOST_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --database-port) [[ $# -ge 2 ]] || bootstrap_die "--database-port needs a value"; DATABASE_PORT_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --database-name) [[ $# -ge 2 ]] || bootstrap_die "--database-name needs a value"; DATABASE_NAME_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --database-user) [[ $# -ge 2 ]] || bootstrap_die "--database-user needs a value"; DATABASE_USER_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --database-password) [[ $# -ge 2 ]] || bootstrap_die "--database-password needs a value"; DATABASE_PASSWORD_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --database-ssl-mode) [[ $# -ge 2 ]] || bootstrap_die "--database-ssl-mode needs a value"; DATABASE_SSL_MODE_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --secret-key) [[ $# -ge 2 ]] || bootstrap_die "--secret-key needs a value"; SECRET_KEY_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --max-upload-mb) [[ $# -ge 2 ]] || bootstrap_die "--max-upload-mb needs a value"; MAX_UPLOAD_MB_VALUE="$2"; CONFIG_OPTIONS_PROVIDED=true; shift 2 ;;
    --service-name) [[ $# -ge 2 ]] || bootstrap_die "--service-name needs a value"; SERVICE_PREFIX_OVERRIDE="$2"; shift 2 ;;
    --skip-system-packages) INSTALL_SYSTEM_PACKAGES=false; shift ;;
    --yes) ASSUME_YES=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) bootstrap_die "Unknown option: $1" ;;
  esac
done

prompt_value() {
  local variable_name="$1"
  local label="$2"
  local default_value="$3"
  local answer
  read -r -p "${label} [${default_value}]: " answer
  printf -v "$variable_name" '%s' "${answer:-$default_value}"
}

prompt_secret() {
  local variable_name="$1"
  local label="$2"
  local current_value="$3"
  local answer
  if [[ -n "$current_value" ]]; then
    read -r -s -p "${label} [press Enter to keep supplied value]: " answer
  else
    read -r -s -p "${label}: " answer
  fi
  echo
  printf -v "$variable_name" '%s' "${answer:-$current_value}"
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

if [[ "$INTERACTIVE" == true ]]; then
  [[ -z "$ENV_SOURCE" ]] || bootstrap_die "Use either --interactive or --env-file, not both"
  bootstrap_log "Interactive deployment configuration"
  prompt_value GIT_REPO_URL "Git repository URL" "$GIT_REPO_URL"
  prompt_value PUBLIC_HOST_OVERRIDE "Public hostname or IP" "${PUBLIC_HOST_OVERRIDE:-$(detect_local_ipv4)}"
  prompt_value PUBLIC_SCHEME_OVERRIDE "Public scheme (https or http)" "${PUBLIC_SCHEME_OVERRIDE:-https}"
  prompt_value HTTP_PORT_OVERRIDE "nginx HTTP/redirect port" "${HTTP_PORT_OVERRIDE:-80}"
  prompt_value HTTPS_PORT_OVERRIDE "nginx HTTPS port" "${HTTPS_PORT_OVERRIDE:-443}"
  prompt_value BIND_HOST_OVERRIDE "Internal bind address" "${BIND_HOST_OVERRIDE:-127.0.0.1}"
  prompt_value FRONTEND_PORT_OVERRIDE "Internal frontend port" "${FRONTEND_PORT_OVERRIDE:-5000}"
  prompt_value BACKEND_PORT_OVERRIDE "Internal backend port" "${BACKEND_PORT_OVERRIDE:-9999}"
  local_origin="$(public_origin "$PUBLIC_SCHEME_OVERRIDE" "$PUBLIC_HOST_OVERRIDE" "$([[ "$PUBLIC_SCHEME_OVERRIDE" == "https" ]] && printf '%s' "$HTTPS_PORT_OVERRIDE" || printf '%s' "$HTTP_PORT_OVERRIDE")" "$([[ "$PUBLIC_SCHEME_OVERRIDE" == "https" ]] && printf '443' || printf '80')")"
  prompt_value FRONTEND_ORIGIN_OVERRIDE "Public frontend origin" "${FRONTEND_ORIGIN_OVERRIDE:-$local_origin}"
  prompt_value PUBLIC_API_URL_OVERRIDE "Public API base URL" "${PUBLIC_API_URL_OVERRIDE:-${FRONTEND_ORIGIN_OVERRIDE%/}/api}"
  prompt_value DATABASE_HOST_VALUE "PostgreSQL host" "$DATABASE_HOST_VALUE"
  prompt_value DATABASE_PORT_VALUE "PostgreSQL port" "$DATABASE_PORT_VALUE"
  prompt_value DATABASE_NAME_VALUE "PostgreSQL database name" "$DATABASE_NAME_VALUE"
  prompt_value DATABASE_USER_VALUE "PostgreSQL user" "$DATABASE_USER_VALUE"
  prompt_secret DATABASE_PASSWORD_VALUE "PostgreSQL password" "$DATABASE_PASSWORD_VALUE"
  prompt_value DATABASE_SSL_MODE_VALUE "PostgreSQL SSL mode" "$DATABASE_SSL_MODE_VALUE"
  prompt_secret SECRET_KEY_VALUE "Application secret (blank generates one)" "$SECRET_KEY_VALUE"
  prompt_value MAX_UPLOAD_MB_VALUE "Maximum CSV upload size in MB" "$MAX_UPLOAD_MB_VALUE"
  prompt_value SERVICE_PREFIX_OVERRIDE "systemd service prefix" "${SERVICE_PREFIX_OVERRIDE:-fintracker}"
fi

if [[ -n "$FRONTEND_PORT_OVERRIDE" ]]; then bootstrap_validate_port FRONTEND_PORT "$FRONTEND_PORT_OVERRIDE"; fi
if [[ -n "$BACKEND_PORT_OVERRIDE" ]]; then bootstrap_validate_port BACKEND_PORT "$BACKEND_PORT_OVERRIDE"; fi
if [[ -n "$HTTP_PORT_OVERRIDE" ]]; then bootstrap_validate_port HTTP_PORT "$HTTP_PORT_OVERRIDE"; fi
if [[ -n "$HTTPS_PORT_OVERRIDE" ]]; then bootstrap_validate_port HTTPS_PORT "$HTTPS_PORT_OVERRIDE"; fi
bootstrap_validate_port DATABASE_PORT "$DATABASE_PORT_VALUE"
case "$DATABASE_SSL_MODE_VALUE" in
  disable|allow|prefer|require|verify-ca|verify-full) ;;
  *) bootstrap_die "Unsupported PostgreSQL SSL mode: $DATABASE_SSL_MODE_VALUE" ;;
esac
if [[ -n "$FRONTEND_PORT_OVERRIDE" && -n "$BACKEND_PORT_OVERRIDE" && "$FRONTEND_PORT_OVERRIDE" == "$BACKEND_PORT_OVERRIDE" ]]; then
  bootstrap_die "Frontend and backend ports must be different"
fi
if [[ -n "$PUBLIC_SCHEME_OVERRIDE" && "$PUBLIC_SCHEME_OVERRIDE" != "http" && "$PUBLIC_SCHEME_OVERRIDE" != "https" ]]; then
  bootstrap_die "--scheme must be http or https"
fi
if [[ -n "$PUBLIC_HOST_OVERRIDE" && ! "$PUBLIC_HOST_OVERRIDE" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  bootstrap_die "Public hostname contains unsupported characters"
fi
if [[ -n "$SERVICE_PREFIX_OVERRIDE" && ! "$SERVICE_PREFIX_OVERRIDE" =~ ^[A-Za-z0-9_.@-]+$ ]]; then
  bootstrap_die "Service name contains unsupported characters"
fi
[[ "$GIT_REPO_URL" != *$'\n'* && "$GIT_REPO_URL" != *$'\r'* ]] || bootstrap_die "Repository URL contains unsupported characters"
[[ "$MAX_UPLOAD_MB_VALUE" =~ ^[0-9]+$ ]] && (( MAX_UPLOAD_MB_VALUE >= 1 )) || bootstrap_die "MAX_UPLOAD_MB must be a positive number"

GENERATE_ENV=false
if [[ -n "$ENV_SOURCE" && "$CONFIG_OPTIONS_PROVIDED" == true ]]; then
  bootstrap_die "Use either --env-file or database/application configuration options, not both"
fi
if [[ "$INTERACTIVE" == true ]]; then
  GENERATE_ENV=true
elif [[ "$CONFIG_OPTIONS_PROVIDED" == true ]]; then
  GENERATE_ENV=true
elif [[ -z "$ENV_SOURCE" ]]; then
  if [[ -f "$APP_HOME/.env" ]]; then
    ENV_SOURCE="$APP_HOME/.env"
  elif [[ -f "$PWD/.env" ]]; then
    ENV_SOURCE="$PWD/.env"
  elif [[ -f "$SCRIPT_DIR/.env" ]]; then
    ENV_SOURCE="$SCRIPT_DIR/.env"
  elif [[ -f "$SCRIPT_DIR/../.env" ]]; then
    ENV_SOURCE="$SCRIPT_DIR/../.env"
  elif [[ -n "$DATABASE_PASSWORD_VALUE" ]]; then
    GENERATE_ENV=true
  else
    bootstrap_die "No configuration found. Use --interactive, --env-file FILE, or database command-line options."
  fi
fi

GENERATED_ENV_FILE=""
TEMP_CLONE_DIR=""
cleanup_bootstrap() {
  if [[ -n "$TEMP_CLONE_DIR" && -d "$TEMP_CLONE_DIR" ]]; then rm -rf "$TEMP_CLONE_DIR"; fi
  if [[ -n "$GENERATED_ENV_FILE" && -f "$GENERATED_ENV_FILE" ]]; then rm -f "$GENERATED_ENV_FILE"; fi
}
trap cleanup_bootstrap EXIT

if [[ "$GENERATE_ENV" == true ]]; then
  [[ -n "$DATABASE_HOST_VALUE" && -n "$DATABASE_NAME_VALUE" && -n "$DATABASE_USER_VALUE" && -n "$DATABASE_PASSWORD_VALUE" ]] || bootstrap_die "Database host, name, user, and password are required"
  if [[ -z "$SECRET_KEY_VALUE" ]]; then
    SECRET_KEY_VALUE="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    SECRET_WAS_GENERATED=true
  fi
  [[ ${#SECRET_KEY_VALUE} -ge 12 ]] || bootstrap_die "SECRET_KEY must contain at least 12 characters"
  for env_value in "$DATABASE_HOST_VALUE" "$DATABASE_NAME_VALUE" "$DATABASE_USER_VALUE" "$DATABASE_PASSWORD_VALUE" "$DATABASE_SSL_MODE_VALUE" "$SECRET_KEY_VALUE"; do
    [[ "$env_value" != *$'\n'* && "$env_value" != *$'\r'* && "$env_value" != *"'"* ]] || bootstrap_die "Generated .env values cannot contain newlines or single quotes"
  done

  generated_scheme="${PUBLIC_SCHEME_OVERRIDE:-https}"
  generated_host="${PUBLIC_HOST_OVERRIDE:-$(detect_local_ipv4)}"
  [[ -n "$generated_host" ]] || bootstrap_die "Unable to detect a local IPv4 address; pass --public-host ADDRESS"
  generated_http_port="${HTTP_PORT_OVERRIDE:-80}"
  generated_https_port="${HTTPS_PORT_OVERRIDE:-443}"
  generated_frontend_port="${FRONTEND_PORT_OVERRIDE:-5000}"
  generated_backend_port="${BACKEND_PORT_OVERRIDE:-9999}"
  generated_public_port="$generated_http_port"
  generated_default_port="80"
  if [[ "$generated_scheme" == "https" ]]; then generated_public_port="$generated_https_port"; generated_default_port="443"; fi
  generated_origin="${FRONTEND_ORIGIN_OVERRIDE:-$(public_origin "$generated_scheme" "$generated_host" "$generated_public_port" "$generated_default_port")}"
  generated_api_url="${PUBLIC_API_URL_OVERRIDE:-${generated_origin%/}/api}"
  for env_value in "$generated_host" "$generated_origin" "$generated_api_url" "${BIND_HOST_OVERRIDE:-127.0.0.1}" "${SERVICE_PREFIX_OVERRIDE:-fintracker}"; do
    [[ "$env_value" != *$'\n'* && "$env_value" != *$'\r'* && "$env_value" != *"'"* ]] || bootstrap_die "Generated .env values cannot contain newlines or single quotes"
  done
  GENERATED_ENV_FILE="$(mktemp)"
  {
    printf "APP_ENV='production'\n"
    printf "APP_NAME='personal-finance-manager'\n"
    printf "DEPLOY_PUBLIC_HOST='%s'\n" "$generated_host"
    printf "DEPLOY_PUBLIC_SCHEME='%s'\n" "$generated_scheme"
    printf "DEPLOY_BIND_HOST='%s'\n" "${BIND_HOST_OVERRIDE:-127.0.0.1}"
    printf "HTTP_PORT='%s'\n" "$generated_http_port"
    printf "HTTPS_PORT='%s'\n" "$generated_https_port"
    printf "SERVICE_PREFIX='%s'\n" "${SERVICE_PREFIX_OVERRIDE:-fintracker}"
    printf "FRONTEND_HOST='%s'\n" "${BIND_HOST_OVERRIDE:-127.0.0.1}"
    printf "FRONTEND_PORT='%s'\n" "$generated_frontend_port"
    printf "NEXT_PUBLIC_API_BASE_URL='%s'\n" "$generated_api_url"
    printf "CORS_ORIGINS='%s'\n" "$generated_origin"
    printf "BACKEND_HOST='%s'\n" "${BIND_HOST_OVERRIDE:-127.0.0.1}"
    printf "BACKEND_PORT='%s'\n" "$generated_backend_port"
    printf "BACKEND_RELOAD='false'\n"
    printf "API_ROOT_PATH='/api'\n"
    printf "COOKIE_SECURE='%s'\n" "$([[ "$generated_scheme" == "https" ]] && printf 'true' || printf 'false')"
    printf "SECRET_KEY='%s'\n" "$SECRET_KEY_VALUE"
    printf "DATABASE_HOST='%s'\n" "$DATABASE_HOST_VALUE"
    printf "DATABASE_PORT='%s'\n" "$DATABASE_PORT_VALUE"
    printf "DATABASE_NAME='%s'\n" "$DATABASE_NAME_VALUE"
    printf "DATABASE_USER='%s'\n" "$DATABASE_USER_VALUE"
    printf "DATABASE_PASSWORD='%s'\n" "$DATABASE_PASSWORD_VALUE"
    printf "DATABASE_SSL_MODE='%s'\n" "$DATABASE_SSL_MODE_VALUE"
    printf "MAX_UPLOAD_MB='%s'\n" "$MAX_UPLOAD_MB_VALUE"
    printf "UPLOAD_STORAGE_DIR='%s'\n" "$APP_HOME/backend/storage/imports"
  } > "$GENERATED_ENV_FILE"
  chmod 0600 "$GENERATED_ENV_FILE"
  ENV_SOURCE="$GENERATED_ENV_FILE"
else
  [[ -f "$ENV_SOURCE" ]] || bootstrap_die "Environment file not found: $ENV_SOURCE"
  ENV_SOURCE="$(cd "$(dirname "$ENV_SOURCE")" && pwd)/$(basename "$ENV_SOURCE")"
fi

# Resolve and validate the complete plan before making any system changes.
set -a
# shellcheck disable=SC1090
source "$ENV_SOURCE"
set +a
DATABASE_HOST_VALUE="${DATABASE_HOST:-$DATABASE_HOST_VALUE}"
DATABASE_PORT_VALUE="${DATABASE_PORT:-$DATABASE_PORT_VALUE}"
DATABASE_NAME_VALUE="${DATABASE_NAME:-$DATABASE_NAME_VALUE}"
DATABASE_USER_VALUE="${DATABASE_USER:-$DATABASE_USER_VALUE}"
DATABASE_PASSWORD_VALUE="${DATABASE_PASSWORD:-$DATABASE_PASSWORD_VALUE}"
DATABASE_SSL_MODE_VALUE="${DATABASE_SSL_MODE:-$DATABASE_SSL_MODE_VALUE}"
SECRET_KEY_VALUE="${SECRET_KEY:-$SECRET_KEY_VALUE}"
MAX_UPLOAD_MB_VALUE="${MAX_UPLOAD_MB:-$MAX_UPLOAD_MB_VALUE}"

PLAN_SERVICE_PREFIX="${SERVICE_PREFIX_OVERRIDE:-${SERVICE_PREFIX:-fintracker}}"
PLAN_BIND_HOST="${BIND_HOST_OVERRIDE:-${DEPLOY_BIND_HOST:-127.0.0.1}}"
PLAN_PUBLIC_HOST="${PUBLIC_HOST_OVERRIDE:-${DEPLOY_PUBLIC_HOST:-$(detect_local_ipv4)}}"
PLAN_PUBLIC_SCHEME="${PUBLIC_SCHEME_OVERRIDE:-${DEPLOY_PUBLIC_SCHEME:-https}}"
PLAN_FRONTEND_PORT="${FRONTEND_PORT_OVERRIDE:-${FRONTEND_PORT:-5000}}"
PLAN_BACKEND_PORT="${BACKEND_PORT_OVERRIDE:-${BACKEND_PORT:-9999}}"
PLAN_HTTP_PORT="${HTTP_PORT_OVERRIDE:-${HTTP_PORT:-80}}"
PLAN_HTTPS_PORT="${HTTPS_PORT_OVERRIDE:-${HTTPS_PORT:-443}}"
PLAN_PUBLIC_PORT="$PLAN_HTTP_PORT"
PLAN_DEFAULT_PORT="80"
if [[ "$PLAN_PUBLIC_SCHEME" == "https" ]]; then PLAN_PUBLIC_PORT="$PLAN_HTTPS_PORT"; PLAN_DEFAULT_PORT="443"; fi
PLAN_FRONTEND_ORIGIN="${FRONTEND_ORIGIN_OVERRIDE:-$(public_origin "$PLAN_PUBLIC_SCHEME" "$PLAN_PUBLIC_HOST" "$PLAN_PUBLIC_PORT" "$PLAN_DEFAULT_PORT")}"
PLAN_PUBLIC_API_URL="${PUBLIC_API_URL_OVERRIDE:-${PLAN_FRONTEND_ORIGIN%/}/api}"

validate_plan_port() { bootstrap_validate_port "$1" "$2"; }
validate_plan_port FRONTEND_PORT "$PLAN_FRONTEND_PORT"
validate_plan_port BACKEND_PORT "$PLAN_BACKEND_PORT"
validate_plan_port HTTP_PORT "$PLAN_HTTP_PORT"
validate_plan_port HTTPS_PORT "$PLAN_HTTPS_PORT"
validate_plan_port DATABASE_PORT "$DATABASE_PORT_VALUE"
[[ "$PLAN_FRONTEND_PORT" != "$PLAN_BACKEND_PORT" ]] || bootstrap_die "Frontend and backend ports must be different"
if [[ "$PLAN_PUBLIC_SCHEME" == "https" && "$PLAN_HTTP_PORT" == "$PLAN_HTTPS_PORT" ]]; then bootstrap_die "HTTP and HTTPS ports must be different"; fi
for internal_port in "$PLAN_FRONTEND_PORT" "$PLAN_BACKEND_PORT"; do
  [[ "$internal_port" != "$PLAN_HTTP_PORT" && "$internal_port" != "$PLAN_HTTPS_PORT" ]] || bootstrap_die "Internal application ports must differ from nginx ports"
done
[[ "$PLAN_PUBLIC_SCHEME" == "http" || "$PLAN_PUBLIC_SCHEME" == "https" ]] || bootstrap_die "Public scheme must be http or https"
[[ -n "$PLAN_PUBLIC_HOST" ]] || bootstrap_die "Unable to detect a local IPv4 address; pass --public-host ADDRESS"
[[ "$PLAN_PUBLIC_HOST" =~ ^[A-Za-z0-9._:-]+$ ]] || bootstrap_die "Public hostname contains unsupported characters"
[[ "$PLAN_SERVICE_PREFIX" =~ ^[A-Za-z0-9_.@-]+$ ]] || bootstrap_die "Service name contains unsupported characters"
[[ -n "$DATABASE_HOST_VALUE" && -n "$DATABASE_NAME_VALUE" && -n "$DATABASE_USER_VALUE" && -n "$DATABASE_PASSWORD_VALUE" ]] || bootstrap_die "Database host, name, user, and password are required"
case "$DATABASE_SSL_MODE_VALUE" in
  disable|allow|prefer|require|verify-ca|verify-full) ;;
  *) bootstrap_die "Unsupported PostgreSQL SSL mode: $DATABASE_SSL_MODE_VALUE" ;;
esac
[[ ${#SECRET_KEY_VALUE} -ge 12 ]] || bootstrap_die "SECRET_KEY must contain at least 12 characters"
[[ "$MAX_UPLOAD_MB_VALUE" =~ ^[0-9]+$ ]] && (( MAX_UPLOAD_MB_VALUE >= 1 )) || bootstrap_die "MAX_UPLOAD_MB must be a positive number"

print_deployment_plan() {
  echo
  echo "================ Fintracker deployment plan ================"
  printf '%-28s %s\n' "Repository:" "$GIT_REPO_URL"
  printf '%-28s %s\n' "Application user:" "$APP_USER"
  printf '%-28s %s\n' "Application/home path:" "$APP_HOME"
  printf '%-28s %s\n' "Environment source:" "$([[ "$GENERATE_ENV" == true ]] && printf 'generated from supplied answers/options' || printf '%s' "$ENV_SOURCE")"
  printf '%-28s %s\n' "Install system packages:" "$INSTALL_SYSTEM_PACKAGES"
  printf '%-28s %s\n' "systemd services:" "${PLAN_SERVICE_PREFIX}-backend, ${PLAN_SERVICE_PREFIX}-frontend"
  printf '%-28s %s\n' "Internal bind address:" "$PLAN_BIND_HOST"
  printf '%-28s %s\n' "Internal frontend:" "${PLAN_BIND_HOST}:${PLAN_FRONTEND_PORT}"
  printf '%-28s %s\n' "Internal backend:" "${PLAN_BIND_HOST}:${PLAN_BACKEND_PORT}"
  printf '%-28s %s\n' "Public scheme:" "$PLAN_PUBLIC_SCHEME"
  printf '%-28s %s\n' "nginx HTTP port:" "$PLAN_HTTP_PORT"
  if [[ "$PLAN_PUBLIC_SCHEME" == "https" ]]; then
    printf '%-28s %s\n' "nginx HTTPS port:" "$PLAN_HTTPS_PORT"
    printf '%-28s %s\n' "TLS certificate:" "self-signed (generated if absent)"
  fi
  printf '%-28s %s\n' "Frontend URL:" "$PLAN_FRONTEND_ORIGIN"
  printf '%-28s %s\n' "API URL:" "$PLAN_PUBLIC_API_URL"
  printf '%-28s %s\n' "API documentation:" "${PLAN_PUBLIC_API_URL%/}/docs"
  printf '%-28s %s\n' "PostgreSQL host:" "${DATABASE_HOST_VALUE}:${DATABASE_PORT_VALUE}"
  printf '%-28s %s\n' "PostgreSQL database:" "$DATABASE_NAME_VALUE"
  printf '%-28s %s\n' "PostgreSQL user:" "$DATABASE_USER_VALUE"
  printf '%-28s %s\n' "PostgreSQL password:" "[configured, redacted]"
  printf '%-28s %s\n' "PostgreSQL SSL mode:" "$DATABASE_SSL_MODE_VALUE"
  printf '%-28s %s\n' "Application secret:" "$([[ "$SECRET_WAS_GENERATED" == true ]] && printf '[generated, redacted]' || printf '[configured, redacted]')"
  printf '%-28s %s MB\n' "Maximum CSV upload:" "$MAX_UPLOAD_MB_VALUE"
  printf '%-28s %s\n' "Python virtualenv:" "$APP_HOME/.venv"
  echo "=============================================================="
}

print_deployment_plan
if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Proceed with this deployment? [y/N]: " CONFIRM_DEPLOYMENT || bootstrap_die "Deployment cancelled"
  [[ "$CONFIRM_DEPLOYMENT" =~ ^[Yy]$ ]] || bootstrap_die "Deployment cancelled"
fi

if (( EUID != 0 )); then
  command -v sudo >/dev/null 2>&1 || bootstrap_die "Run as root or install sudo"
  sudo -v
fi

install_system_packages() {
  [[ -r /etc/os-release ]] || bootstrap_die "Cannot detect this Linux distribution"
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}" in
    ubuntu|debian)
      bootstrap_log "Installing Linux prerequisites with apt"
      as_root apt-get update
      as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl git rsync nginx openssl python3 python3-venv python3-pip python3-dev build-essential nodejs npm
      ;;
    fedora|rhel|centos|rocky|almalinux)
      bootstrap_log "Installing Linux prerequisites with dnf"
      as_root dnf install -y curl git rsync nginx openssl python3 python3-pip python3-devel gcc gcc-c++ make nodejs npm
      ;;
    *)
      bootstrap_die "Unsupported distribution '${ID:-unknown}'. Install git, rsync, Python 3.11+, venv, Node.js 20+, npm, and systemd; then rerun with --skip-system-packages."
      ;;
  esac
}

if [[ "$INSTALL_SYSTEM_PACKAGES" == true ]]; then
  install_system_packages
fi

for command_name in git rsync nginx openssl python3 node npm systemctl; do
  command -v "$command_name" >/dev/null 2>&1 || bootstrap_die "Required command not found: $command_name"
done
if (( EUID == 0 )); then
  command -v runuser >/dev/null 2>&1 || bootstrap_die "Required command not found: runuser"
fi
NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
if { [[ ! "$NODE_MAJOR" =~ ^[0-9]+$ ]] || (( NODE_MAJOR < 20 )); } && [[ "$INSTALL_SYSTEM_PACKAGES" == true ]]; then
  bootstrap_log "Upgrading Node.js to the current 22.x LTS line"
  as_root npm install --global n
  as_root n 22
  hash -r
  NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
fi
[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] && (( NODE_MAJOR >= 20 )) || bootstrap_die "Node.js 20 or newer is required; found $(node --version)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || bootstrap_die "Python 3.11 or newer is required"

bootstrap_log "Creating the dedicated ${APP_USER} user and ${APP_HOME} home"
if id "$APP_USER" >/dev/null 2>&1; then
  EXISTING_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
  [[ "$EXISTING_HOME" == "$APP_HOME" ]] || bootstrap_die "User $APP_USER already exists with home $EXISTING_HOME; expected $APP_HOME"
else
  as_root useradd --system --user-group --create-home --home-dir "$APP_HOME" --shell /bin/bash "$APP_USER"
fi
APP_GROUP="$(id -gn "$APP_USER")"
as_root install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$APP_HOME"

bootstrap_log "Cloning ${GIT_REPO_URL} into ${APP_HOME}"
if [[ -d "$APP_HOME/.git" ]]; then
  [[ -z "$(as_app_user git -C "$APP_HOME" status --porcelain --untracked-files=no)" ]] || bootstrap_die "Tracked files in $APP_HOME have local changes"
  as_app_user git -C "$APP_HOME" pull --ff-only
else
  TEMP_CLONE_DIR="$(mktemp -d)"
  as_root chown "$APP_USER:$APP_GROUP" "$TEMP_CLONE_DIR"
  as_app_user git clone "$GIT_REPO_URL" "$TEMP_CLONE_DIR/repository"
  as_root rsync -a --delete \
    --exclude=.env \
    --exclude=.deploy/ \
    --exclude=.ssh/ \
    --exclude=backend/storage/imports/ \
    "$TEMP_CLONE_DIR/repository/" "$APP_HOME/"
  as_root chown -R "$APP_USER:$APP_GROUP" "$APP_HOME"
  rm -rf "$TEMP_CLONE_DIR"
  TEMP_CLONE_DIR=""
fi

TARGET_ENV="$APP_HOME/.env"
if [[ "$ENV_SOURCE" != "$TARGET_ENV" ]]; then
  as_root install -o "$APP_USER" -g "$APP_GROUP" -m 0600 "$ENV_SOURCE" "$TARGET_ENV"
else
  as_root chown "$APP_USER:$APP_GROUP" "$TARGET_ENV"
  as_root chmod 0600 "$TARGET_ENV"
fi

ROOT_DIR="$APP_HOME"
[[ -f "$ROOT_DIR/scripts/lib/deploy_common.sh" ]] || bootstrap_die "The cloned repository does not contain scripts/lib/deploy_common.sh"
# shellcheck source=scripts/lib/deploy_common.sh
source "$ROOT_DIR/scripts/lib/deploy_common.sh"

load_app_env
validate_app_env
DEPLOY_USER="$APP_USER"
SERVICE_PREFIX="${SERVICE_PREFIX_OVERRIDE:-${SERVICE_PREFIX:-fintracker}}"
BIND_HOST="${BIND_HOST_OVERRIDE:-${DEPLOY_BIND_HOST:-127.0.0.1}}"
PUBLIC_HOST="${PUBLIC_HOST_OVERRIDE:-${DEPLOY_PUBLIC_HOST:-$(detect_local_ipv4)}}"
PUBLIC_SCHEME="${PUBLIC_SCHEME_OVERRIDE:-${DEPLOY_PUBLIC_SCHEME:-https}}"
FRONTEND_PORT="${FRONTEND_PORT_OVERRIDE:-${FRONTEND_PORT:-5000}}"
BACKEND_PORT="${BACKEND_PORT_OVERRIDE:-${BACKEND_PORT:-9999}}"
HTTP_PORT="${HTTP_PORT_OVERRIDE:-${HTTP_PORT:-80}}"
HTTPS_PORT="${HTTPS_PORT_OVERRIDE:-${HTTPS_PORT:-443}}"

[[ "$PUBLIC_SCHEME" == "http" || "$PUBLIC_SCHEME" == "https" ]] || die "--scheme must be http or https"
validate_port FRONTEND_PORT "$FRONTEND_PORT"
validate_port BACKEND_PORT "$BACKEND_PORT"
validate_port HTTP_PORT "$HTTP_PORT"
validate_port HTTPS_PORT "$HTTPS_PORT"
[[ "$FRONTEND_PORT" != "$BACKEND_PORT" ]] || die "Frontend and backend ports must be different"
if [[ "$PUBLIC_SCHEME" == "https" && "$HTTP_PORT" == "$HTTPS_PORT" ]]; then die "HTTP and HTTPS ports must be different"; fi
[[ "$PUBLIC_HOST" =~ ^[A-Za-z0-9._:-]+$ ]] || die "Public hostname contains unsupported characters"
validate_service_prefix "$SERVICE_PREFIX"
PUBLIC_PORT="$HTTP_PORT"
PUBLIC_DEFAULT_PORT="80"
if [[ "$PUBLIC_SCHEME" == "https" ]]; then PUBLIC_PORT="$HTTPS_PORT"; PUBLIC_DEFAULT_PORT="443"; fi
FRONTEND_ORIGIN="${FRONTEND_ORIGIN_OVERRIDE:-$(public_origin "$PUBLIC_SCHEME" "$PUBLIC_HOST" "$PUBLIC_PORT" "$PUBLIC_DEFAULT_PORT")}"
PUBLIC_API_URL="${PUBLIC_API_URL_OVERRIDE:-${FRONTEND_ORIGIN%/}/api}"
COOKIE_SECURE=false
if [[ "$PUBLIC_SCHEME" == "https" ]]; then COOKIE_SECURE=true; fi
FRONTEND_ORIGIN="${FRONTEND_ORIGIN%/}"
PUBLIC_API_URL="${PUBLIC_API_URL%/}"
validate_systemd_value BIND_HOST "$BIND_HOST"
validate_systemd_value FRONTEND_ORIGIN "$FRONTEND_ORIGIN"
validate_systemd_value PUBLIC_API_URL "$PUBLIC_API_URL"

install_app_dependencies
build_frontend
prepare_storage
verify_database_and_migrate
write_deploy_config
install_systemd_services
install_reverse_proxy
restart_services
print_deployment_summary
