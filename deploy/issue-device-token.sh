#!/usr/bin/env bash
#
# Issue the pairing secret for one iPhone.
#
# The token is written into the analysis API's environment file and shown once
# on the terminal. It is printed to /dev/tty rather than to stdout so that
# redirecting or piping this script cannot quietly put the secret into a file,
# a pager history or a CI log.
#
# This is not a single-use pairing code and it does not expire; the service
# checks one static bearer token. Revoking a phone therefore means running this
# script again and restarting the service, which invalidates every device at
# once. deploy/README.md states that limit where the operator will read it.

set -euo pipefail

ENV_FILE="${DEVICE_TOKEN_ENV_FILE:-/etc/us-stock-helper/analysis-api.env}"

if [ ! -f "$ENV_FILE" ]; then
	printf 'error: %s does not exist; install the environment file first.\n' "$ENV_FILE" >&2
	exit 1
fi
if [ ! -w "$ENV_FILE" ]; then
	printf 'error: %s is not writable; run this as root.\n' "$ENV_FILE" >&2
	exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
	printf 'error: openssl is required to generate a token.\n' >&2
	exit 1
fi
# The terminal is claimed before anything is written, and the descriptor is
# held open for the rest of the run. Testing the device with -w is not enough:
# the node is world-writable even when the process has no controlling terminal
# to open, and discovering that after the environment file has been rewritten
# would leave the service demanding a token nobody ever saw.
if ! (exec 3>/dev/tty) 2>/dev/null; then
	printf 'error: no terminal is attached, so the token cannot be shown safely.\n' >&2
	exit 1
fi
exec 3>/dev/tty

# Thirty-two random bytes as hex clears the service's 32-character minimum with
# a wide margin and is short enough to be typed into a phone once.
token="$(openssl rand -hex 32)"

umask 077
scratch="$(mktemp "${ENV_FILE}.XXXXXX")"
trap 'rm -f "$scratch"' EXIT

{ grep -v '^ANALYSIS_API_TOKEN=' "$ENV_FILE" || true; } >"$scratch"
if [ ! -s "$scratch" ]; then
	printf 'error: %s lost its contents while being rewritten; nothing was changed.\n' "$ENV_FILE" >&2
	exit 1
fi
printf 'ANALYSIS_API_TOKEN=%s\n' "$token" >>"$scratch"
chmod 600 "$scratch"
# The rename is atomic within the directory, so a failure here leaves the old
# working token in place rather than a half-written file the service cannot
# parse.
mv "$scratch" "$ENV_FILE"
trap - EXIT

{
	printf '\nPairing secret for one iPhone. It is shown once and is not stored anywhere else.\n\n'
	printf '  Bearer token : %s\n\n' "$token"
	printf 'Type it into the app, which keeps it in the iOS Keychain. Never paste it\n'
	printf 'into a note, a chat, a screenshot or this repository.\n\n'
	printf 'Apply it with:  systemctl restart analysis-api\n\n'
} >&3
exec 3>&-
