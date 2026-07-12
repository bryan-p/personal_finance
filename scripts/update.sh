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
  --http-port PORT        Change the nginx HTTP/redirect port
  --https-port PORT       Change the nginx HTTPS port
  --bind-host HOST        Change the service bind address
  --public-host HOST      Change the public hostname or IP
  --scheme http|https     Change the public scheme
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
[[ "$DEPLOY_USER" == "fintracker" ]] || die "Deployment config must use the dedicated fintracker user"
[[ "$ROOT_DIR" == "/srv/fintracker" ]] || die "Updates must run from /srv/fintracker"
load_app_env
validate_app_env
PULL_SOURCE=true
FRONTEND_PORT_CHANGED=false
BACKEND_PORT_CHANGED=false
HTTP_PORT_CHANGED=false
HTTPS_PORT_CHANGED=false
PUBLIC_HOST_CHANGED=false
PUBLIC_SCHEME_CHANGED=false
FRONTEND_ORIGIN_CHANGED=false
PUBLIC_API_URL_CHANGED=false

while (( $# )); do
  case "$1" in
    --no-pull) PULL_SOURCE=false; shift ;;
    --frontend-port) [[ $# -ge 2 ]] || die "--frontend-port needs a value"; FRONTEND_PORT="$2"; FRONTEND_PORT_CHANGED=true; shift 2 ;;
    --backend-port) [[ $# -ge 2 ]] || die "--backend-port needs a value"; BACKEND_PORT="$2"; BACKEND_PORT_CHANGED=true; shift 2 ;;
    --http-port) [[ $# -ge 2 ]] || die "--http-port needs a value"; HTTP_PORT="$2"; HTTP_PORT_CHANGED=true; shift 2 ;;
    --https-port) [[ $# -ge 2 ]] || die "--https-port needs a value"; HTTPS_PORT="$2"; HTTPS_PORT_CHANGED=true; shift 2 ;;
    --bind-host) [[ $# -ge 2 ]] || die "--bind-host needs a value"; BIND_HOST="$2"; shift 2 ;;
    --public-host) [[ $# -ge 2 ]] || die "--public-host needs a value"; PUBLIC_HOST="$2"; PUBLIC_HOST_CHANGED=true; shift 2 ;;
    --scheme) [[ $# -ge 2 ]] || die "--scheme needs a value"; PUBLIC_SCHEME="$2"; PUBLIC_SCHEME_CHANGED=true; shift 2 ;;
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
require_command nginx
if [[ "$PUBLIC_SCHEME" == "https" ]]; then require_command openssl; fi
if (( EUID != 0 )); then require_command sudo; fi
if (( EUID == 0 )) && [[ "$(id -un)" != "$DEPLOY_USER" ]]; then require_command runuser; fi
[[ "$DEPLOY_USER" != "root" ]] || die "Refusing to run the app services as root"
run_as_deploy_user test -r "$ROOT_DIR/.env" || die "$DEPLOY_USER cannot read $ROOT_DIR/.env"
run_as_deploy_user test -w "$ROOT_DIR" || die "$DEPLOY_USER cannot write to the application directory: $ROOT_DIR"
validate_port FRONTEND_PORT "$FRONTEND_PORT"
validate_port BACKEND_PORT "$BACKEND_PORT"
validate_port HTTP_PORT "$HTTP_PORT"
validate_port HTTPS_PORT "$HTTPS_PORT"
[[ "$FRONTEND_PORT" != "$BACKEND_PORT" ]] || die "Frontend and backend ports must be different"
[[ "$PUBLIC_SCHEME" == "http" || "$PUBLIC_SCHEME" == "https" ]] || die "--scheme must be http or https"
[[ "$PUBLIC_HOST" =~ ^[A-Za-z0-9._:-]+$ ]] || die "Public hostname contains unsupported characters"
if [[ "$PUBLIC_SCHEME" == "https" && "$HTTP_PORT" == "$HTTPS_PORT" ]]; then die "HTTP and HTTPS ports must be different"; fi
if { [[ "$HTTP_PORT_CHANGED" == true ]] || [[ "$HTTPS_PORT_CHANGED" == true ]] || [[ "$PUBLIC_HOST_CHANGED" == true ]] || [[ "$PUBLIC_SCHEME_CHANGED" == true ]]; } && [[ "$FRONTEND_ORIGIN_CHANGED" == false ]]; then
  public_port="$HTTP_PORT"
  default_port="80"
  if [[ "$PUBLIC_SCHEME" == "https" ]]; then public_port="$HTTPS_PORT"; default_port="443"; fi
  FRONTEND_ORIGIN="$(public_origin "$PUBLIC_SCHEME" "$PUBLIC_HOST" "$public_port" "$default_port")"
fi
if { [[ "$FRONTEND_ORIGIN_CHANGED" == true ]] || [[ "$HTTP_PORT_CHANGED" == true ]] || [[ "$HTTPS_PORT_CHANGED" == true ]] || [[ "$PUBLIC_HOST_CHANGED" == true ]] || [[ "$PUBLIC_SCHEME_CHANGED" == true ]]; } && [[ "$PUBLIC_API_URL_CHANGED" == false ]]; then
  PUBLIC_API_URL="${FRONTEND_ORIGIN%/}/api"
fi
validate_systemd_value BIND_HOST "$BIND_HOST"
validate_systemd_value FRONTEND_ORIGIN "$FRONTEND_ORIGIN"
validate_systemd_value PUBLIC_API_URL "$PUBLIC_API_URL"
COOKIE_SECURE=false
if [[ "$PUBLIC_SCHEME" == "https" ]]; then COOKIE_SECURE=true; fi

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
install_reverse_proxy
restart_services
print_deployment_summary
