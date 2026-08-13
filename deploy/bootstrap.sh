#!/usr/bin/env bash
#
# Compresses the runbook's mechanical steps into two commands, with a hard
# stop at the one step no script may perform.
#
# The stop is structural, not a reminder: `prepare` finishes before OpenD is
# ever started, and `finish` refuses to run until a logged-in OpenD is already
# answering. Nothing here reads, prompts for, stores or transmits a moomoo
# account, password, trade-unlock code or two-factor response, and adding such
# a prompt would be a defect, not a feature.
#
#   sudo ./deploy/bootstrap.sh prepare
#   ... you log in to moomoo yourself, per section 6 of README.md ...
#   sudo ./deploy/bootstrap.sh finish --domain stock.example.com
#
# Every step is the same command the runbook spells out; read it there if you
# want to know what this is doing before you let it do it.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
OPEND_PORT=11111
GATEWAY_PORT=8765
ANALYSIS_PORT=8770

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die() { printf '\n\033[31mstopped: %s\033[0m\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "run with sudo"
}

require_ubuntu() {
  command -v apt-get >/dev/null 2>&1 || die "this expects Ubuntu; follow README.md by hand elsewhere"
}

cmd_prepare() {
  require_root
  require_ubuntu

  log "System packages"
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip ufw curl ca-certificates

  log "Service accounts"
  for account in usstock-opend usstock-gateway usstock-analysis; do
    if id "${account}" >/dev/null 2>&1; then
      note "${account} exists"
    else
      useradd --system --create-home --shell /usr/sbin/nologin "${account}"
      note "created ${account}"
    fi
  done

  log "Environment files"
  install -d -m 0750 /etc/usstock
  for example in "${DEPLOY_DIR}"/env/*.env.example; do
    target="/etc/usstock/$(basename "${example}" .example)"
    if [ -f "${target}" ]; then
      note "$(basename "${target}") exists, left alone"
    else
      install -m 0600 "${example}" "${target}"
      note "created $(basename "${target}") — edit it before finishing"
    fi
  done

  log "Firewall"
  ufw --force reset >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow OpenSSH >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  note "inbound: SSH and 443 only"

  log "Prepared"
  cat <<'NEXT'
    Next, and only you can do it:

      1. Install Linux OpenD           — README.md section 5
      2. Log in to moomoo yourself     — README.md section 6

    No script in this repository will do step 2, and none should. When OpenD
    is running and logged in, come back and run:

      sudo ./deploy/bootstrap.sh finish --domain your.domain.example
NEXT
}

cmd_finish() {
  require_root
  require_ubuntu

  local domain=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --domain) domain="${2:-}"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "${domain}" ] || die "pass --domain your.domain.example"

  log "Checking OpenD"
  # Refusing here is the point: everything below assumes a logged-in session,
  # and starting the stack without one produces a service that looks healthy
  # and answers with nothing.
  if ! (exec 3<>"/dev/tcp/127.0.0.1/${OPEND_PORT}") 2>/dev/null; then
    die "nothing is listening on 127.0.0.1:${OPEND_PORT}; finish README.md sections 5 and 6 first"
  fi
  note "OpenD is answering on loopback"

  log "Installing units"
  install -m 0644 "${DEPLOY_DIR}"/systemd/*.service /etc/systemd/system/
  systemctl daemon-reload
  for unit in market-gateway analysis-api; do
    systemctl enable --now "${unit}.service"
    note "${unit} enabled"
  done

  log "Caddy"
  if ! command -v caddy >/dev/null 2>&1; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
    curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -qq
    apt-get install -y -qq caddy
  fi
  sed "s/{\$SITE_ADDRESS}/${domain}/g" "${DEPLOY_DIR}/Caddyfile" > /etc/caddy/Caddyfile
  chmod 0644 /etc/caddy/Caddyfile
  systemctl restart caddy
  note "serving ${domain}"

  log "Preflight"
  bash "${DEPLOY_DIR}/preflight.sh"

  log "Done"
  cat <<NEXT
    Issue the phone's pairing code:

      sudo -u usstock-analysis python3 -m us_stock_helper_device_auth pair --label "iPhone"

    Then enter that code in the app once. It is single-use and short-lived.
NEXT
}

case "${1:-}" in
  prepare) shift; cmd_prepare "$@" ;;
  finish) shift; cmd_finish "$@" ;;
  *)
    cat <<'USAGE'
usage: bootstrap.sh prepare
       bootstrap.sh finish --domain your.domain.example

prepare  packages, service accounts, environment files, firewall
finish   units, Caddy with TLS, preflight — refuses until OpenD is logged in

Between the two you install OpenD and log in to moomoo yourself. Nothing here
will do that for you.
USAGE
    exit 1 ;;
esac
