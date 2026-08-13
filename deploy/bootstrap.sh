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
#   sudo ./deploy/bootstrap.sh finish --domain stock.example.com --email you@stock.example.com
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
  for account in usstock-opend usstock-gateway usstock-api; do
    if id "${account}" >/dev/null 2>&1; then
      note "${account} exists"
    else
      useradd --system --home-dir /nonexistent --no-create-home \
        --shell /usr/sbin/nologin "${account}"
      note "created ${account}"
    fi
  done

  log "Environment files"
  install -d -m 0755 -o root -g root /etc/us-stock-helper
  for example in "${DEPLOY_DIR}"/env/*.env.example; do
    target="/etc/us-stock-helper/$(basename "${example}" .example)"
    if [ -f "${target}" ]; then
      note "$(basename "${target}") exists, left alone"
    else
      install -m 0600 -o root -g root "${example}" "${target}"
      note "created $(basename "${target}") — edit it before finishing"
    fi
  done

  log "Firewall"
  # Never reset: that would drop rules the operator added, and the OpenSSH
  # profile only covers port 22. A host whose sshd was moved elsewhere would
  # become unreachable the moment the policy took effect.
  local ssh_port
  ssh_port="$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}')"
  ssh_port="${ssh_port:-22}"
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow "${ssh_port}/tcp" >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  note "inbound: ${ssh_port}/tcp (ssh) and 443 only; existing rules left in place"

  log "Prepared"
  cat <<'NEXT'
    Next, and only you can do it:

      1. Install Linux OpenD           — README.md section 5
      2. Log in to moomoo yourself     — README.md section 6

    No script in this repository will do step 2, and none should. When OpenD
    is running and logged in, come back and run:

      sudo ./deploy/bootstrap.sh finish --domain your.domain --email you@your.domain
NEXT
}

cmd_finish() {
  require_root
  require_ubuntu

  local domain="" email=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --domain) domain="${2:-}"; shift 2 ;;
      --email) email="${2:-}"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "${domain}" ] || die "pass --domain your.domain.example"
  # Let's Encrypt sends expiry and revocation notices to this address. Leaving
  # the template's placeholder would register the ACME account to someone else
  # and send them the notices for your certificate.
  [ -n "${email}" ] || die "pass --email you@your.domain (the ACME contact address)"

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
  systemd-analyze verify /etc/systemd/system/opend.service \
    /etc/systemd/system/market-gateway.service \
    /etc/systemd/system/analysis-api.service
  systemctl enable --now market-gateway.service
  note "market-gateway enabled"
  # analysis-api stays stopped until a token exists: without one it refuses to
  # start, which is the intended fail-closed behaviour.

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
  install -m 0644 "${DEPLOY_DIR}/Caddyfile" /etc/caddy/Caddyfile
  sed -i "s/stock\.example\.com/${domain}/g; s/ops@example\.com/${email}/g" /etc/caddy/Caddyfile
  if grep -q 'example\.com' /etc/caddy/Caddyfile; then
    die "a placeholder survived in /etc/caddy/Caddyfile; not starting Caddy"
  fi
  caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
  systemctl restart caddy
  note "serving ${domain}, ACME contact ${email}"

  log "Preflight"
  # The token is issued after this point, so preflight is expected to report
  # the missing one; everything else must already hold.
  bash "${DEPLOY_DIR}/preflight.sh" || note "preflight reported findings above — read them before issuing the token"

  log "Done"
  cat <<NEXT
    Issue the phone's bearer token and start the API:

      sudo ${DEPLOY_DIR}/issue-device-token.sh
      sudo systemctl enable --now analysis-api.service

    The token prints once, to this terminal only. Type it into the app.

    Read section 9 of README.md before you rely on it: this is one static
    token with no expiry and no per-device revocation. services/device_auth
    implements single-use codes and revocable per-device tokens, but nothing
    serves them over HTTP yet, so this runbook cannot deploy that.
NEXT
}

case "${1:-}" in
  prepare) shift; cmd_prepare "$@" ;;
  finish) shift; cmd_finish "$@" ;;
  *)
    cat <<'USAGE'
usage: bootstrap.sh prepare
       bootstrap.sh finish --domain your.domain --email you@your.domain

prepare  packages, service accounts, environment files, firewall
finish   units, Caddy with TLS, preflight — refuses until OpenD is logged in

Between the two you install OpenD and log in to moomoo yourself. Nothing here
will do that for you.
USAGE
    exit 1 ;;
esac
