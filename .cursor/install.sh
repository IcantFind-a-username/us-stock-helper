#!/usr/bin/env bash
# Cloud Agent bootstrap for us-stock-helper.
#
# Idempotent: safe to re-run against a cached or partially prepared checkout.
# It installs the Python backend and the Expo/React Native mobile app so the
# repository's canonical verification commands (per-service pytest, mobile
# typecheck + jest) run without further setup.
set -euo pipefail

cd "$(dirname "$0")/.."

# --- System prerequisites -------------------------------------------------
# The default base image ships python3 and node, but pip is not guaranteed.
# Provision it once if missing so the committed config works on any base.
if ! python3 -m pip --version >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-pip
fi

# --- Python backend -------------------------------------------------------
# The eight service packages are installed editable into the user site so the
# default `python3` resolves every dependency. This matches CI (a single
# interpreter with everything installed) and the subprocess the analysis_api
# documentation test spawns with a bare `python3`.
#
# httpx is a test dependency: older `anthropic` releases pulled it in
# transitively, but current `anthropic` ships `httpx2` instead, so the
# adviser_llm / analysis_api tests that build `httpx.Request/Response` need it
# installed explicitly.
PIP_FLAGS=(--user --break-system-packages --disable-pip-version-check -q)
python3 -m pip install "${PIP_FLAGS[@]}" --upgrade pip setuptools wheel
python3 -m pip install "${PIP_FLAGS[@]}" pytest httpx
for d in services/*/; do
  echo "installing ${d%/}"
  python3 -m pip install "${PIP_FLAGS[@]}" -e "$d"
done

# --- Mobile app -----------------------------------------------------------
# `npm ci` is idempotent and reproduces the locked dependency tree.
( cd apps/mobile && npm ci )

echo "us-stock-helper environment ready."
