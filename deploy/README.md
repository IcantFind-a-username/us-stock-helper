# Singapore deployment runbook

From a blank Ubuntu 24.04 LTS host to three services the iPhone can reach over
the internet, with no Mac involved at any point after the install.

```text
iPhone ──HTTPS 443──▶ Caddy ──127.0.0.1:8770──▶ analysis_api
                                                    │
                                          127.0.0.1:8765
                                                    ▼
                                             market_gateway
                                                    │
                                         127.0.0.1:11111
                                                    ▼
                                            Linux OpenD ──▶ moomoo
```

Only the first hop is public. The market gateway and OpenD listen on loopback,
are never proxied, and are never opened in the firewall.

## Read this before you start

**This host will hold a logged-in moomoo session.** A machine that stays logged
in to your broker is a machine whose compromise reaches your brokerage account,
and no amount of hardening below changes that fact. Running it is
a security decision that is yours to make knowingly, not an install detail:

- Nothing in this repository can place an order, and the two Python services
  are denied every non-loopback address at the kernel level. That bounds what
  *this* software can do. It does not bound what someone with a root shell on
  this host could do with OpenD directly.
- Anyone who can read `/proc` as the OpenD account, or who can restore a backup
  of this disk, inherits that session.
- Keep this host single-purpose. No other services, no other human accounts, no
  other tenants.

If that trade is not one you want to make, stop here and keep the Mac-local
setup in `docs/runbooks/local-real-market.md` instead.

**You log in to moomoo yourself.** No automation enters your account, password,
password hash, trade-unlock code or two-factor response — not this runbook, not
these scripts, not any agent working on this repository. Login material is
never committed to this repository, never pasted into an issue or a chat, and
never placed in a systemd unit, an environment file or a command line.

## What ships here

| File | Purpose |
| --- | --- |
| `systemd/opend.service` | Runs Linux OpenD as `usstock-opend`. |
| `systemd/market-gateway.service` | Runs the read-only market gateway as `usstock-gateway`. |
| `systemd/analysis-api.service` | Runs the decision-chain HTTP boundary as `usstock-api`. |
| `env/opend.env.example` | Template for OpenD's environment file. |
| `env/market-gateway.env.example` | Template for the gateway's environment file. |
| `env/analysis-api.env.example` | Template for the API's environment file, including the bearer token. |
| `Caddyfile` | The single public entry point on 443. |
| `issue-device-token.sh` | Generates the phone's bearer token and writes it into the environment file. |
| `bootstrap.sh` | Runs the mechanical steps of this runbook, stopping before section 6. |
| `preflight.sh` | Pre-deployment self-check; refuses to report PASS for anything it could not inspect. |
| `.gitignore` | Keeps real environment files and the OpenD config out of git. |
| `tests/` | The invariants the above must not lose. |

## Shortcut

`bootstrap.sh` performs the mechanical parts of sections 1, 2, 7, 8, 10, 11 and
12. It stops before section 6 and refuses to continue until OpenD answers on
loopback, because a stack started against a logged-out OpenD looks healthy and
returns nothing:

```bash
sudo ./deploy/bootstrap.sh prepare
# sections 3, 4, 5 and 6 by hand — the login is yours
sudo ./deploy/bootstrap.sh finish --domain your.domain
```

It is a convenience over the steps below, not a replacement for reading them.

## 1. The server

A 2 vCPU / 4 GB Ubuntu 24.04 LTS instance in Singapore is enough. Singapore is
the right region because it matches the account region of the moomoo login;
US-market data still arrives fine over the SDK's own connection.

Log in as a sudo-capable user, then:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv git ufw curl
python3 --version   # must be 3.11 or newer; 24.04 ships 3.12
```

Use SSH keys only. Confirm `PasswordAuthentication no` and
`PermitRootLogin no` in `/etc/ssh/sshd_config` (or a drop-in under
`/etc/ssh/sshd_config.d/`) before going further, and reload with
`sudo systemctl reload ssh`.

## 2. Service accounts

Three accounts, one per service, none of them root and none of them able to log
in. Separate accounts are the reason a fault in the closed-source OpenD binary
cannot read the phone's bearer token.

```bash
for account in usstock-opend usstock-gateway usstock-api; do
  sudo useradd --system --home-dir /nonexistent --no-create-home \
    --shell /usr/sbin/nologin "$account"
done
```

## 3. The code

```bash
sudo git clone <your-fork-url> /opt/us-stock-helper
sudo chown -R root:root /opt/us-stock-helper
sudo chmod -R go-w /opt/us-stock-helper
```

The tree stays owned by root and is read-only to every service account:
`python -m` puts the working directory on `sys.path`, so a tree the service
could write to would be an import-time backdoor.

## 4. The moomoo SDK

Only the gateway needs the SDK, and it gets its own virtual environment so the
system Python stays untouched:

```bash
sudo python3 -m venv /opt/us-stock-helper/services/market_gateway/.venv
sudo /opt/us-stock-helper/services/market_gateway/.venv/bin/pip install moomoo-api
sudo chown -R root:root /opt/us-stock-helper/services/market_gateway/.venv
```

The analysis API needs nothing installed: it and the four packages behind it
are standard library only.

## 5. Linux OpenD

Download OpenD **only** from the official moomoo OpenAPI download page, on this
host, and verify the checksum moomoo publishes next to it. Do not fetch it from
a mirror, and do not copy a binary from another machine without checking it.

```bash
sudo mkdir -p /opt/opend
# unpack the official archive into /opt/opend
sudo chown -R root:root /opt/opend
sudo chmod -R go-w /opt/opend
sudo chown root:usstock-opend /opt/opend
```

Confirm the flags your build accepts before installing the unit — releases have
differed:

```bash
/opt/opend/OpenD --help
```

`env/opend.env.example` passes `-cfg_file=/etc/us-stock-helper/opend.conf`. If
your build spells that differently, change `OPEND_ARGS` in the deployed
environment file, not the unit.

OpenD must keep listening on `127.0.0.1:11111`. Set the listen address in
`opend.conf`, and point OpenD's own log path at
`/var/lib/us-stock-helper-opend`, which systemd creates at mode 0700 — OpenD's
logs name the account, and 0700 keeps them away from every other local user.

## 6. Log in to moomoo yourself

This is the step no automation performs for you.

Create `/etc/us-stock-helper/opend.conf` by hand, with your own editor, on this
host:

```bash
sudo install -d -m 0755 -o root -g root /etc/us-stock-helper
sudo touch /etc/us-stock-helper/opend.conf
sudo chown root:usstock-opend /etc/us-stock-helper/opend.conf
sudo chmod 0640 /etc/us-stock-helper/opend.conf
sudo nano /etc/us-stock-helper/opend.conf   # you type the login material here
```

Two honest options, and the difference matters:

1. **Interactive login.** Run `/opt/opend/OpenD` in the foreground once and log
   in at its prompt. Nothing is persisted, and the session ends when the
   process does — which means an unattended restart leaves you logged out until
   you come back. The gateway will report `LOGIN_REQUIRED` and the app will
   show "unavailable" rather than anything invented. That is the intended
   behaviour, not a fault.
2. **Persisted login in `opend.conf`.** OpenD restarts unattended, and your
   login material sits on this disk at rest. Choose this only if you accept the
   first section of this document.

Either way: you type it, nobody and nothing types it for you, and
`opend.conf` never enters git — `deploy/.gitignore` covers the filename, but
the rule is yours to keep, not the tool's.

Complete any US market-data agreement inside moomoo. The gateway cannot bypass
a quote entitlement and will report `PERMISSION_DENIED` instead of guessing.

## 7. Environment files

```bash
sudo install -d -m 0755 -o root -g root /etc/us-stock-helper
for name in opend market-gateway analysis-api; do
  sudo install -m 0600 -o root -g root \
    /opt/us-stock-helper/deploy/env/$name.env.example \
    /etc/us-stock-helper/$name.env
done
```

Mode 0600 owned by root is correct even though the services run as other
accounts: systemd reads `EnvironmentFile=` as the manager, before it drops
privileges, so no service account ever needs to read the file. That is also why
the token is not in an `Environment=` line — those are readable by any local
account through `systemctl show`.

## 8. Install the units

```bash
sudo install -m 0644 /opt/us-stock-helper/deploy/systemd/*.service \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/opend.service \
  /etc/systemd/system/market-gateway.service \
  /etc/systemd/system/analysis-api.service
sudo systemctl enable --now opend.service market-gateway.service
```

Leave `analysis-api.service` stopped until a token exists; without one it
refuses to start, which is the intended fail-closed behaviour.

Check what the hardening actually bought:

```bash
systemd-analyze security market-gateway.service
```

`market-gateway.service` deliberately omits `MemoryDenyWriteExecution`: the SDK
pulls in numpy, pandas and pycryptodome, and none of them has been verified
under it on this host. To add it, set it in a drop-in, restart, and confirm the
service still answers `/health` — do not assume.

## 9. Issue the phone's token

```bash
sudo /opt/us-stock-helper/deploy/issue-device-token.sh
sudo systemctl enable --now analysis-api.service
```

The token is printed once, to the terminal only. Type it into the app, which
keeps it in the iOS Keychain; it is never compiled into the bundle.

**What this token is not.** It is one static bearer token. It is
not a single-use pairing code, it has no expiry, and there is no server-side
device registry behind it, so there is no way to revoke one phone while leaving
another working. To revoke, run `issue-device-token.sh` again and restart the
service: that invalidates every device at once and requires re-entering the new
token on each one. Rotate it if a phone is lost, if the
token is ever displayed somewhere it might have been captured, and on a
schedule you set.

`services/device_auth` in this repository already implements single-use codes
and revocable per-device tokens, but no HTTP boundary reaches it yet: the
analysis API imports nothing from it and serves no pairing route, so it cannot
be deployed by this runbook. When it is wired in, three things here change
together — the paragraph above stops being true, `analysis-api.service` needs a
`StateDirectory` for the credential database (`ProtectSystem=strict` and
`ProtectHome=yes` mean the package's default `~/.us-stock-helper/` path will not
work, so `DEVICE_AUTH_DATABASE` must point into that state directory), and the
deploy tests that pin the current shape must be updated in the same change. A
test fails on the day the import appears, so this cannot drift silently.

## 10. Caddy and TLS

Point an A record for your domain at the host and let it propagate first;
certificate issuance will fail otherwise.

Install Caddy from the official repository as documented at
`https://caddyserver.com/docs/install`, then:

```bash
sudo install -m 0644 /opt/us-stock-helper/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's/stock\.example\.com/your.domain/; s/ops@example\.com/you@your.domain/' \
  /etc/caddy/Caddyfile
sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
```

The packaged unit starts Caddy with `--environ`, which prints the whole process
environment into the journal. Drop it so no future environment variable of
Caddy's leaks there:

```bash
sudo systemctl edit caddy
```

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
```

```bash
sudo systemctl restart caddy
```

Certificates are issued over TLS-ALPN on 443 because port 80 is never opened;
the config disables the HTTP-01 challenge so Caddy does not wait on a port the
firewall drops.

## 11. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Nothing else is opened. In particular the gateway and OpenD ports stay closed;
they are reachable only from this host, and only over loopback.

## 12. Preflight

```bash
sudo /opt/us-stock-helper/deploy/preflight.sh
```

Exit 0 means every check ran and passed. Exit 1 means something failed. **Exit
2 means nothing failed but something could not be checked** — a missing tool,
or a check that needed root. Treat exit 2 as unverified, not as success; the
script will not print PASS for evidence it does not have.

## 13. Verification

Work down this list. Stop at the first line that does not hold.

```bash
# The internal ports answer on loopback and nowhere else.
sudo ss -ltnp | grep -E '11111|8765|8770'

# The gateway sees a healthy, logged-in OpenD.
curl --fail --silent http://127.0.0.1:8765/health

# The API is up on loopback.
curl --fail --silent http://127.0.0.1:8770/health

# From another machine: the internal ports are not reachable at all.
nc -vz your.domain 8765   # must fail
nc -vz your.domain 11111  # must fail

# The public edge refuses an unauthenticated caller.
curl -i https://your.domain/health                      # 401
curl -i -H 'Authorization: Bearer wrong' https://your.domain/health   # 401
curl -i -H "Authorization: Bearer $TOKEN" https://your.domain/health  # 200

# The public edge refuses writes and unlisted paths.
curl -i -X POST -H "Authorization: Bearer $TOKEN" https://your.domain/decision  # 405
curl -i -H "Authorization: Bearer $TOKEN" https://your.domain/watchlist         # 404

# A real decision, with its refusals intact.
curl --fail --silent -H "Authorization: Bearer $TOKEN" \
  'https://your.domain/decision?symbol=NVDA&horizon=short' | head -c 400
```

Then confirm no secret reached a log:

```bash
sudo journalctl -u analysis-api -u market-gateway -u opend --since today \
  | grep -iE 'authorization|bearer|token|password' || echo 'clean'
sudo grep -iE 'authorization|bearer' /var/log/caddy/access.log || echo 'clean'
```

Both must print `clean`. Neither Python service logs requests, and the Caddy
access log deletes the `Authorization` header before writing.

Finally, on the phone: put it on cellular data, with Wi-Fi off, and load a
symbol. The Mac must be off or asleep while you do it — that is the whole point
of this deployment.

## Operations

| Task | Command |
| --- | --- |
| Follow logs | `journalctl -u analysis-api -f` |
| Restart the chain | `sudo systemctl restart opend market-gateway analysis-api` |
| Rotate the phone token | `sudo ./issue-device-token.sh && sudo systemctl restart analysis-api` |
| Update the code | `sudo git -C /opt/us-stock-helper pull && sudo systemctl restart market-gateway analysis-api` |
| Re-check the host | `sudo /opt/us-stock-helper/deploy/preflight.sh` |

Back up `/etc/us-stock-helper/` only if the backup is encrypted and stored
somewhere you control: it contains the bearer token, and `opend.conf` may
contain your login material. A backup of this host is a copy of your broker
session.

## What this deployment still does not do

Stated plainly so nobody discovers it during an incident:

- No single-use pairing, no per-device revocation, no token expiry (section 9).
- No rate limiting at the edge. A leaked token can be used as fast as the
  attacker likes until it is rotated.
- The market gateway has no authentication of its own. It does not need one
  while it is loopback-only, but any local account on this host can read it.
  Keep the host single-purpose.
- No automatic security updates are configured here. Enable
  `unattended-upgrades` yourself if you want them.
- No alerting. If OpenD logs out, the app says "unavailable" and nothing tells
  you why until you look.

## Tests

```bash
PYTHONPATH=services/analysis_api/src:services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine:services/market_gateway/src \
  python3 -m unittest discover -s deploy/tests -v
```

They run anywhere, including a Mac: the checks that need a Linux host report
UNKNOWN rather than passing.
