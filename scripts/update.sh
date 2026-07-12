#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL_ARGS=("$@")
# shellcheck source=scripts/lib/deploy_common.sh
source "$ROOT_DIR/scripts/lib/deploy_common.sh"

usage() {
  cat <<'EOF'
Usage: ./scripts/update.sh [options]

Update a server previously configured by deploy.sh. By default this performs a
fast-forward-only git pull, reinstalls locked dependencies, rebuilds, migrates,
refreshes the systemd units, and restarts both services.

Options:
  --no-pull               Use the currently checked-out source without git pull
  --frontend-port PORT    Change the deployed frontend port
  --backend-port PORT     Change the deployed backend port
  --bind-host HOST        Change the service bind address
  --frontend-origin URL   Change the public frontend origin
  --api-url URL           Change the browser-visible backend URL
  --help                  Show this help
EOF
}

for argument in "$@"; do
  if [[ "$argument" == "--help" || "$argument" == "-h" ]]; then
    usage
    exit 0
  fi
done

[[ -f "$ROOT_DIR/.deploy/config" ]] || die "No deployment config found. Run ./scripts/deploy.sh first."
# shellcheck disable=SC1091
source "$ROOT_DIR/.deploy/config"
load_app_env
validate_app_env
PULL_SOURCE=true
FRONTEND_PORT_CHANGED=false
BACKEND_PORT_CHANGED=false
FRONTEND_ORIGIN_CHANGED=false
PUBLIC_API_URL_CHANGED=false

while (( $# )); do
  case "$1" in
    --no-pull) PULL_SOURCE=false; shift ;;
    --frontend-port) [[ $# -ge 2 ]] || die "--frontend-port needs a value"; FRONTEND_PORT="$2"; FRONTEND_PORT_CHANGED=true; shift 2 ;;
    --backend-port) [[ $# -ge 2 ]] || die "--backend-port needs a value"; BACKEND_PORT="$2"; BACKEND_PORT_CHANGED=true; shift 2 ;;
    --bind-host) [[ $# -ge 2 ]] || die "--bind-host needs a value"; BIND_HOST="$2"; shift 2 ;;
    --frontend-origin) [[ $# -ge 2 ]] || die "--frontend-origin needs a value"; FRONTEND_ORIGIN="${2%/}"; FRONTEND_ORIGIN_CHANGED=true; shift 2 ;;
    --api-url) [[ $# -ge 2 ]] || die "--api-url needs a value"; PUBLIC_API_URL="${2%/}"; PUBLIC_API_URL_CHANGED=true; shift 2 ;;
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
[[ "$DEPLOY_USER" != "root" ]] || die "Refusing to run the app services as root"
run_as_deploy_user test -r "$ROOT_DIR/.env" || die "$DEPLOY_USER cannot read $ROOT_DIR/.env"
run_as_deploy_user test -w "$ROOT_DIR" || die "$DEPLOY_USER cannot write to the application directory: $ROOT_DIR"
validate_port FRONTEND_PORT "$FRONTEND_PORT"
validate_port BACKEND_PORT "$BACKEND_PORT"
[[ "$FRONTEND_PORT" != "$BACKEND_PORT" ]] || die "Frontend and backend ports must be different"
if [[ "$FRONTEND_PORT_CHANGED" == true && "$FRONTEND_ORIGIN_CHANGED" == false ]]; then
  FRONTEND_ORIGIN="${PUBLIC_SCHEME}://${PUBLIC_HOST}:${FRONTEND_PORT}"
fi
if [[ "$BACKEND_PORT_CHANGED" == true && "$PUBLIC_API_URL_CHANGED" == false ]]; then
  PUBLIC_API_URL="${PUBLIC_SCHEME}://${PUBLIC_HOST}:${BACKEND_PORT}"
fi
validate_systemd_value BIND_HOST "$BIND_HOST"
validate_systemd_value FRONTEND_ORIGIN "$FRONTEND_ORIGIN"
validate_systemd_value PUBLIC_API_URL "$PUBLIC_API_URL"

if [[ "$PULL_SOURCE" == true ]]; then
  require_command git
  [[ -d "$ROOT_DIR/.git" ]] || die "Cannot pull updates because $ROOT_DIR is not a Git checkout"
  [[ -z "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=no)" ]] || die "Tracked files have local changes. Commit, stash, or use --no-pull."
  log "Pulling the latest source"
  run_as_deploy_user git -C "$ROOT_DIR" pull --ff-only
  exec "$ROOT_DIR/scripts/update.sh" --no-pull "${ORIGINAL_ARGS[@]}"
fi

install_app_dependencies
build_frontend
prepare_storage
verify_database_and_migrate
write_deploy_config
install_systemd_services
restart_services
print_deployment_summary
