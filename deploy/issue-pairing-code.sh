#!/usr/bin/env bash
#
# Print a single-use pairing code for one iPhone.
#
# The code is shown once, on the terminal only. It is printed to /dev/tty
# rather than to stdout so that redirecting or piping this script cannot
# quietly put it into a file, a pager history or a CI log — it is short lived
# and single use, but for those minutes it is the whole credential.
#
# The device token the phone receives in exchange is never printed here and
# never leaves the phone: it is minted inside the pairing response and stored
# hashed. Revoking one phone is a separate command that leaves the others
# working; deploy/README.md section 9 has both.
#
# This runs the pairing command as the service account rather than as root, so
# that the database it creates is owned by the account that has to write it
# afterwards. A root-owned database is a service that starts and then fails
# every request.

set -euo pipefail

ENV_FILE="${PAIRING_ENV_FILE:-/etc/us-stock-helper/analysis-api.env}"
SERVICE_USER="${PAIRING_SERVICE_USER:-usstock-api}"
TTL_MINUTES="${PAIRING_TTL_MINUTES:-10}"
LABEL="${1:-}"

if [ -z "$LABEL" ]; then
	printf 'usage: %s "how this phone should be listed"\n' "$0" >&2
	exit 1
fi
if [ ! -r "$ENV_FILE" ]; then
	printf 'error: %s is not readable; install the environment file first.\n' "$ENV_FILE" >&2
	exit 1
fi

# Read the two settings from the file the service itself reads, rather than
# repeating them here. A copy would drift, and a drifted database path means
# codes issued into a file nothing serves.
read_setting() {
	sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

database="$(read_setting DEVICE_AUTH_DATABASE)"
pythonpath="$(read_setting PYTHONPATH)"
if [ -z "$database" ]; then
	printf 'error: %s names no DEVICE_AUTH_DATABASE, so there is nowhere to record a code.\n' "$ENV_FILE" >&2
	exit 1
fi
if [ -z "$pythonpath" ]; then
	printf 'error: %s names no PYTHONPATH, so the pairing command cannot be imported.\n' "$ENV_FILE" >&2
	exit 1
fi
# The terminal is claimed before anything is issued and the descriptor is held
# open for the rest of the run. Testing the device with -w is not enough: the
# node is world-writable even when the process has no controlling terminal to
# open, and discovering that after a code had been recorded would leave a live
# code that nobody ever saw. Nothing below this line may run without it.
if ! (exec 3>/dev/tty) 2>/dev/null; then
	printf 'error: no terminal is attached, so the pairing code cannot be shown safely.\n' >&2
	exit 1
fi
exec 3>/dev/tty

if ! command -v runuser >/dev/null 2>&1; then
	printf 'error: runuser is required to issue a code as %s.\n' "$SERVICE_USER" >&2
	exit 1
fi

{
	printf '\nSingle-use pairing code for one iPhone. It is shown once and stored only as a hash.\n\n'
} >&3

runuser -u "$SERVICE_USER" -- env \
	PYTHONPATH="$pythonpath" \
	DEVICE_AUTH_DATABASE="$database" \
	python3 -m us_stock_helper_device_auth pair \
	--label "$LABEL" \
	--ttl-minutes "$TTL_MINUTES" >&3

{
	printf '\nType it into the app before it expires. The app receives a device token in\n'
	printf 'exchange and keeps it in the iOS Keychain; that token is never displayed,\n'
	printf 'never written to this terminal, and can be revoked on its own.\n\n'
} >&3
exec 3>&-
