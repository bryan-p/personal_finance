#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/deploy_common.sh
source "$ROOT_DIR/scripts/lib/deploy_common.sh"

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [options]

Install dependencies, build the app, migrate PostgreSQL, install systemd units,
and start the production services.

Options:
  --frontend-port PORT    Frontend port (default: FRONTEND_PORT from .env or 5000)
  --backend-port PORT     Backend port (default: BACKEND_PORT from .env or 9999)
  --bind-host HOST        Service bind address (default: 0.0.0.0)
  --public-host HOST      Browser-visible hostname or IP (default: hostname -f)
  --scheme SCHEME         Public scheme, http or https (default: http)
  --frontend-origin URL   Full browser-visible frontend origin
  --api-url URL           Full browser-visible backend base URL
  --service-name NAME     systemd service prefix (default: personal-finance-manager)
  --user USER             Linux service user (default: current user or SUDO_USER)
  --help                  Show this help

Examples:
  ./scripts/deploy.sh --public-host finance.example.com
  ./scripts/deploy.sh --public-host 192.168.1.20 --frontend-port 5100 --backend-port 10099
EOF
}

for argument in "$@"; do
  if [[ "$argument" == "--help" || "$argument" == "-h" ]]; then
    usage
    exit 0
  fi
done

load_app_env
validate_app_env

DEPLOY_USER="${SUDO_USER:-$(id -un)}"
SERVICE_PREFIX="${SERVICE_PREFIX:-personal-finance-manager}"
BIND_HOST="${DEPLOY_BIND_HOST:-0.0.0.0}"
PUBLIC_HOST="${DEPLOY_PUBLIC_HOST:-$(hostname -f 2>/dev/null || hostname)}"
PUBLIC_SCHEME="${DEPLOY_PUBLIC_SCHEME:-http}"
FRONTEND_PORT="${FRONTEND_PORT:-5000}"
BACKEND_PORT="${BACKEND_PORT:-9999}"
FRONTEND_ORIGIN_OVERRIDE=""
PUBLIC_API_URL_OVERRIDE=""

while (( $# )); do
  case "$1" in
    --frontend-port) [[ $# -ge 2 ]] || die "--frontend-port needs a value"; FRONTEND_PORT="$2"; shift 2 ;;
    --backend-port) [[ $# -ge 2 ]] || die "--backend-port needs a value"; BACKEND_PORT="$2"; shift 2 ;;
    --bind-host) [[ $# -ge 2 ]] || die "--bind-host needs a value"; BIND_HOST="$2"; shift 2 ;;
    --public-host) [[ $# -ge 2 ]] || die "--public-host needs a value"; PUBLIC_HOST="$2"; shift 2 ;;
    --scheme) [[ $# -ge 2 ]] || die "--scheme needs a value"; PUBLIC_SCHEME="$2"; shift 2 ;;
    --frontend-origin) [[ $# -ge 2 ]] || die "--frontend-origin needs a value"; FRONTEND_ORIGIN_OVERRIDE="$2"; shift 2 ;;
    --api-url) [[ $# -ge 2 ]] || die "--api-url needs a value"; PUBLIC_API_URL_OVERRIDE="$2"; shift 2 ;;
    --service-name) [[ $# -ge 2 ]] || die "--service-name needs a value"; SERVICE_PREFIX="$2"; shift 2 ;;
    --user) [[ $# -ge 2 ]] || die "--user needs a value"; DEPLOY_USER="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_command python3
require_command node
require_command npm
require_command systemctl
if (( EUID != 0 )); then require_command sudo; fi
if (( EUID == 0 )) && [[ "$(id -un)" != "$DEPLOY_USER" ]]; then require_command runuser; fi
id "$DEPLOY_USER" >/dev/null 2>&1 || die "Linux user does not exist: $DEPLOY_USER"
[[ "$DEPLOY_USER" != "root" ]] || die "Refusing to run the app services as root. Run as the app user or pass --user USER."
run_as_deploy_user test -r "$ROOT_DIR/.env" || die "$DEPLOY_USER cannot read $ROOT_DIR/.env"
run_as_deploy_user test -w "$ROOT_DIR" || die "$DEPLOY_USER cannot write to the application directory: $ROOT_DIR"
[[ "$ROOT_DIR" != *[[:space:]]* ]] || die "The deployment path cannot contain whitespace: $ROOT_DIR"
[[ "$PUBLIC_SCHEME" == "http" || "$PUBLIC_SCHEME" == "https" ]] || die "--scheme must be http or https"
validate_port FRONTEND_PORT "$FRONTEND_PORT"
validate_port BACKEND_PORT "$BACKEND_PORT"
[[ "$FRONTEND_PORT" != "$BACKEND_PORT" ]] || die "Frontend and backend ports must be different"
validate_service_prefix "$SERVICE_PREFIX"

FRONTEND_ORIGIN="${FRONTEND_ORIGIN_OVERRIDE:-${PUBLIC_SCHEME}://${PUBLIC_HOST}:${FRONTEND_PORT}}"
PUBLIC_API_URL="${PUBLIC_API_URL_OVERRIDE:-${PUBLIC_SCHEME}://${PUBLIC_HOST}:${BACKEND_PORT}}"
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
restart_services
print_deployment_summary
