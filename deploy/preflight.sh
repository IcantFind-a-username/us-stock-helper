#!/usr/bin/env bash
#
# Pre-deployment self-check for the Singapore host.
#
# The rule this script is built around: it never prints PASS for something it
# could not actually look at. A check whose tool is missing, or whose output
# needs privileges this shell does not have, reports UNKNOWN and the run exits
# non-zero. An operator who reads a green run must be able to believe it.
#
#   exit 0  every check ran and passed
#   exit 1  at least one check failed
#   exit 2  nothing failed, but at least one check could not be performed
#
# The paths are overridable so the deploy tests can point the real script at a
# fixture tree instead of at /etc.

set -euo pipefail

ENV_DIR="${PREFLIGHT_ENV_DIR:-/etc/us-stock-helper}"
UNIT_DIR="${PREFLIGHT_UNIT_DIR:-/etc/systemd/system}"
CADDYFILE="${PREFLIGHT_CADDYFILE:-/etc/caddy/Caddyfile}"
EXPECTED_OWNER="${PREFLIGHT_EXPECTED_OWNER:-root}"
PROC_DIR="${PREFLIGHT_PROC_DIR:-/proc}"

ENV_FILES="opend.env market-gateway.env analysis-api.env"
UNIT_FILES="opend.service market-gateway.service analysis-api.service"
# OpenD's control port, the market gateway and the analysis API. None of the
# three may answer on anything but loopback.
INTERNAL_PORTS="11111 8765 8770"
PUBLIC_RULES="443/tcp 443 OpenSSH 22/tcp 22 ssh"

failures=0
unknowns=0

pass() { printf 'PASS %s %s\n' "$1" "$2"; }
fail() { printf 'FAIL %s %s\n' "$1" "$2"; failures=$((failures + 1)); }
unknown() { printf 'UNKNOWN %s %s\n' "$1" "$2"; unknowns=$((unknowns + 1)); }

# GNU and BSD stat disagree on their flags, and this script is written on one
# platform and run on the other.
file_mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null || true; }
file_owner() { stat -c '%U' "$1" 2>/dev/null || stat -f '%Su' "$1" 2>/dev/null || true; }

# The last assignment wins, matching both systemd and the environment file
# format: a key repeated later in a file overrides the earlier one, so reading
# the first would check a line the service does not use.
read_setting() { sed -n "s/^[[:space:]]*$2=//p" "$1" 2>/dev/null | tail -n 1; }

check_environment_files() {
	local name path mode owner
	for name in $ENV_FILES; do
		path="$ENV_DIR/$name"
		if [ ! -f "$path" ]; then
			fail environment-file-mode "$path is missing"
			continue
		fi
		mode="$(file_mode "$path")"
		owner="$(file_owner "$path")"
		if [ -z "$mode" ] || [ -z "$owner" ]; then
			unknown environment-file-mode "$path could not be inspected"
		elif [ "$mode" != "600" ]; then
			fail environment-file-mode "$path is mode $mode, expected 600"
		elif [ "$owner" != "$EXPECTED_OWNER" ]; then
			fail environment-file-mode "$path is owned by $owner, expected $EXPECTED_OWNER"
		else
			pass environment-file-mode "$path"
		fi
	done
}

# The credential the phone uses is minted by the pairing exchange and lives in
# this database, so what an operator can get wrong before the first start is
# where the database is — not what it contains.
check_credential_database() {
	local path value
	path="$ENV_DIR/analysis-api.env"
	if grep -Eq '^ANALYSIS_API_TOKEN=' "$path" 2>/dev/null; then
		# The service refuses to start on this rather than ignoring it, but
		# saying so here turns a crash loop into a sentence.
		fail environment-file-credential "$path still sets ANALYSIS_API_TOKEN, which nothing reads any more"
		return
	fi
	value="$(read_setting "$path" DEVICE_AUTH_DATABASE)"
	if [ -z "$value" ]; then
		fail environment-file-credential "no DEVICE_AUTH_DATABASE is set, so the analysis API will refuse to start"
	elif [ "${value#/}" = "$value" ]; then
		fail environment-file-credential "DEVICE_AUTH_DATABASE is not an absolute path"
	else
		pass environment-file-credential "a credential database is configured"
	fi
}

# ProtectSystem=strict leaves the whole filesystem read-only to the service
# except the directory systemd creates for it. A database configured anywhere
# else is a service that starts and then fails every pairing, which reads as a
# permission bug rather than as the missing line it is.
check_state_directory() {
	local unit env_path state database
	unit="$UNIT_DIR/analysis-api.service"
	env_path="$ENV_DIR/analysis-api.env"
	if [ ! -f "$unit" ]; then
		fail state-directory "$unit is missing"
		return
	fi
	state="$(read_setting "$unit" StateDirectory)"
	database="$(read_setting "$env_path" DEVICE_AUTH_DATABASE)"
	if [ -z "$state" ]; then
		fail state-directory "$unit grants no StateDirectory, so the credential database cannot be written"
	elif [ -z "$database" ]; then
		fail state-directory "no DEVICE_AUTH_DATABASE is set, so nothing can be checked against the granted directory"
	elif [ "${database#/var/lib/$state/}" = "$database" ]; then
		fail state-directory "DEVICE_AUTH_DATABASE is outside /var/lib/$state, the only path this service may write"
	else
		pass state-directory "the credential database is inside the directory systemd creates"
	fi
}

check_unit_secrets() {
	local name path
	for name in $UNIT_FILES; do
		path="$UNIT_DIR/$name"
		if [ ! -f "$path" ]; then
			fail unit-plaintext-secret "$path is missing"
		elif grep -Eq '^[[:space:]]*Environment=' "$path"; then
			# Environment= is disclosed by `systemctl show` to any local
			# account, which is exactly what EnvironmentFile= avoids.
			fail unit-plaintext-secret "$path sets Environment= inline"
		elif grep -Eq '[0-9a-fA-F]{32,}' "$path"; then
			fail unit-plaintext-secret "$path contains something shaped like a secret"
		else
			pass unit-plaintext-secret "$path"
		fi
	done
}

check_unit_syntax() {
	local name path
	if ! command -v systemd-analyze >/dev/null 2>&1; then
		unknown unit-syntax "systemd-analyze is unavailable, so no unit was parsed"
		return
	fi
	for name in $UNIT_FILES; do
		path="$UNIT_DIR/$name"
		if systemd-analyze verify "$path" >/dev/null 2>&1; then
			pass unit-syntax "$path"
		else
			fail unit-syntax "$path does not verify"
		fi
	done
}

check_caddyfile_ports() {
	if [ ! -f "$CADDYFILE" ]; then
		fail caddyfile-internal-port "$CADDYFILE is missing"
	elif grep -Eq '\b(8765|11111)\b' "$CADDYFILE"; then
		fail caddyfile-internal-port "$CADDYFILE addresses the gateway or OpenD"
	else
		pass caddyfile-internal-port "only the analysis API is reachable from the edge"
	fi
}

check_caddyfile_placeholder() {
	if [ ! -f "$CADDYFILE" ]; then
		fail caddyfile-placeholder "$CADDYFILE is missing"
	elif grep -q 'example\.com' "$CADDYFILE"; then
		fail caddyfile-placeholder "$CADDYFILE still carries the placeholder domain or email"
	else
		pass caddyfile-placeholder "the site address has been set"
	fi
}

check_caddyfile_syntax() {
	if ! command -v caddy >/dev/null 2>&1; then
		unknown caddyfile-syntax "caddy is unavailable, so the config was not parsed"
	elif caddy validate --adapter caddyfile --config "$CADDYFILE" >/dev/null 2>&1; then
		pass caddyfile-syntax "$CADDYFILE"
	else
		fail caddyfile-syntax "$CADDYFILE does not validate"
	fi
}

is_loopback_address() {
	case "$1" in
	127.*) return 0 ;;
	::1 | '[::1]') return 0 ;;
	*) return 1 ;;
	esac
}

check_port_exposure() {
	local listeners line local_address address port exposed=""
	if ! command -v ss >/dev/null 2>&1; then
		unknown port-exposure "ss is unavailable, so nothing is known about who can reach these ports"
		return
	fi
	# Swallowing ss's exit status would turn "could not look" into "looked
	# and found nothing", which is the one substitution this script exists to
	# prevent.
	if ! listeners="$(ss -H -ltn 2>/dev/null)"; then
		unknown port-exposure "ss could not enumerate listeners, so exposure is unmeasured"
		return
	fi
	while IFS= read -r line; do
		[ -n "$line" ] || continue
		local_address="$(printf '%s\n' "$line" | awk '{print $4}')"
		[ -n "$local_address" ] || continue
		port="${local_address##*:}"
		address="${local_address%:*}"
		case " $INTERNAL_PORTS " in
		*" $port "*) ;;
		*) continue ;;
		esac
		if ! is_loopback_address "$address"; then
			exposed="$exposed $address:$port"
		fi
	done <<EOF
$listeners
EOF
	if [ -n "$exposed" ]; then
		fail port-exposure "an internal service answers off loopback:$exposed"
	else
		pass port-exposure "no internal service answers off loopback"
	fi
}

check_firewall() {
	local status opened rule
	if ! command -v ufw >/dev/null 2>&1; then
		unknown firewall "ufw is not installed, so the firewall was not verified"
		return
	fi
	status="$(ufw status verbose 2>/dev/null || true)"
	if [ -z "$status" ]; then
		unknown firewall "ufw status could not be read, which usually means this check needs root"
		return
	fi
	case "$status" in
	*"Status: inactive"*)
		fail firewall "the firewall is inactive on a host with a public address"
		return
		;;
	*"Status: active"*) ;;
	*)
		unknown firewall "ufw reported a status this check does not recognise"
		return
		;;
	esac
	# An active firewall that defaults to allowing inbound traffic opens every
	# port that has no explicit rule, including OpenD's. Its rule list reads
	# identically to a correctly configured host, so the default is the only
	# place the difference is visible.
	case "$status" in
	*"Default: deny (incoming)"* | *"Default: reject (incoming)"*) ;;
	*"Default:"*)
		fail firewall "the firewall does not deny inbound traffic by default"
		return
		;;
	*)
		unknown firewall "ufw did not report its default policy, so inbound exposure is unmeasured"
		return
		;;
	esac
	opened="$(printf '%s\n' "$status" | awk '/ALLOW/ {print $1}' | sort -u)"
	for rule in $opened; do
		case " $PUBLIC_RULES " in
		*" $rule "*) ;;
		*)
			fail firewall "the firewall opens $rule, which belongs to no public service here"
			return
			;;
		esac
	done
	pass firewall "only HTTPS and SSH are open"
}

check_opend_command_line() {
	local entry cmdline found=0 leaked=""
	if [ ! -d "$PROC_DIR" ]; then
		unknown opend-cmdline "$PROC_DIR is unavailable, so no command line was read"
		return
	fi
	for entry in "$PROC_DIR"/[0-9]*; do
		[ -r "$entry/cmdline" ] || continue
		cmdline="$(tr '\0' ' ' <"$entry/cmdline" 2>/dev/null || true)"
		case "$cmdline" in
		*OpenD*) ;;
		*) continue ;;
		esac
		found=1
		# A command line is readable by every local process, so login material
		# here is already disclosed and rotating it is the only remedy.
		case "$cmdline" in
		*login_pwd* | *login_account* | *passwd* | *password* | *token*)
			leaked="$entry"
			;;
		esac
	done
	if [ -n "$leaked" ]; then
		fail opend-cmdline "an OpenD command line carries login material and is readable by every local process"
	elif [ "$found" -eq 1 ]; then
		pass opend-cmdline "the running OpenD exposes no login material in its arguments"
	else
		pass opend-cmdline "no OpenD process is running, so no argument is exposed"
	fi
}

check_environment_files
check_credential_database
check_state_directory
check_unit_secrets
check_unit_syntax
check_caddyfile_ports
check_caddyfile_placeholder
check_caddyfile_syntax
check_port_exposure
check_firewall
check_opend_command_line

if [ "$failures" -gt 0 ]; then
	printf '\n%d check(s) failed; %d could not be performed.\n' "$failures" "$unknowns"
	exit 1
fi
if [ "$unknowns" -gt 0 ]; then
	printf '\nNo check failed, but %d could not be performed. This host is not verified.\n' "$unknowns"
	exit 2
fi
printf '\nEvery check ran and passed.\n'
exit 0
