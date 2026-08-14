#!/usr/bin/env bash
# Keep the read-only local market and analysis services alive as one job.
# Secrets stay in the operator-owned env file and are never copied here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ENV="${US_STOCK_HELPER_ENV_FILE:-${HOME}/.us-stock-helper/lan.env}"
PYTHON_BIN="${REPO_ROOT}/services/market_gateway/.venv/bin/python"

if [[ ! -r "${RUNTIME_ENV}" ]]; then
  echo "Missing local runtime environment: ${RUNTIME_ENV}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090 -- the path is operator-configured and checked above.
source "${RUNTIME_ENV}"
set +a

CA_BUNDLE="$(${PYTHON_BIN} -c 'import certifi; print(certifi.where())')"
if [[ ! -r "${CA_BUNDLE}" ]]; then
  echo "The market-gateway Python environment has no readable CA bundle" >&2
  exit 1
fi
export SSL_CERT_FILE="${CA_BUNDLE}"
export REQUESTS_CA_BUNDLE="${CA_BUNDLE}"

children=()
stop_children() {
  if ((${#children[@]})); then
    kill "${children[@]}" 2>/dev/null || true
    wait "${children[@]}" 2>/dev/null || true
  fi
}
trap stop_children EXIT INT TERM

env -u MOOMOO_GATEWAY_ALLOW_LAN -u MOOMOO_GATEWAY_TOKEN \
  -u MOOMOO_GATEWAY_ALLOWED_CLIENTS \
  MOOMOO_GATEWAY_HOST=127.0.0.1 \
  MOOMOO_GATEWAY_PORT=8765 \
  PYTHONPATH="${REPO_ROOT}/services/market_gateway/src:${REPO_ROOT}/services/analysis_core" \
  "${PYTHON_BIN}" -m us_stock_helper_market_gateway \
  >>/tmp/us-stock-helper-gateway-loopback.log 2>&1 &
children+=("$!")

MOOMOO_GATEWAY_ALLOW_LAN=1 \
  MOOMOO_GATEWAY_HOST=0.0.0.0 \
  MOOMOO_GATEWAY_PORT=8766 \
  PYTHONPATH="${REPO_ROOT}/services/market_gateway/src:${REPO_ROOT}/services/analysis_core" \
  "${PYTHON_BIN}" -m us_stock_helper_market_gateway \
  >>/tmp/us-stock-helper-gateway-lan.log 2>&1 &
children+=("$!")

ANALYSIS_API_ALLOW_LAN=1 \
  ANALYSIS_API_HOST=0.0.0.0 \
  ANALYSIS_API_PORT=8770 \
  DEVICE_AUTH_DATABASE="${HOME}/.us-stock-helper/state/devices.sqlite3" \
  ANALYSIS_API_GATEWAY_URL=http://127.0.0.1:8765 \
  PYTHONPATH="${REPO_ROOT}/services/analysis_api/src:${REPO_ROOT}/services/analysis_core:${REPO_ROOT}/services/information_layer:${REPO_ROOT}/services/adviser_layer:${REPO_ROOT}/services/decision_engine:${REPO_ROOT}/services/device_auth/src:${REPO_ROOT}/services/adviser_llm/src" \
  "${PYTHON_BIN}" -m us_stock_helper_analysis_api \
  >>/tmp/us-stock-helper-analysis-api.log 2>&1 &
children+=("$!")

echo "Local read-only stack started: ${children[*]}"

# Bash 3.2 has no `wait -n`, so poll each exact child. If any service exits,
# the supervisor exits too and the trap cleans up the remaining half-stack.
while true; do
  for child in "${children[@]}"; do
    if ! kill -0 "${child}" 2>/dev/null; then
      wait "${child}"
      exit $?
    fi
  done
  sleep 2
done
