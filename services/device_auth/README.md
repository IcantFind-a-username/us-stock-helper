# device_auth

Device pairing and revocable device tokens. This is the authentication layer
for reaching the read-only analysis API from the open internet, where the
static bearer token that was adequate on a home LAN is not: it cannot be
revoked for one phone, it never expires, and it has to be typed or pasted
somewhere it can be read.

It is a library plus an operator command line. It contains no HTTP surface of
its own, so the audit surface facing the internet stays exactly one service
wide, and nothing here can reach a broker, an account or an order.

## The shape of the flow

Issuing is asymmetric to redeeming, on purpose.

1. The operator, already on the host, runs `pair` over SSH. A single-use code
   is printed to that terminal and to nowhere else.
2. The operator reads the code off the screen and types it into the phone.
3. The phone redeems it once, over TLS, and receives a device token it keeps in
   the Keychain. The token is never printed, logged, or shown to the operator.
4. Every later request carries that token. Revoking the device refuses it from
   the next request onwards.

## Safety invariants

- **Nothing recoverable is stored.** The pairing code is kept as scrypt with a
  per-code salt; the device token as HMAC-SHA256 with a per-device salt. A test
  reads the raw database bytes, sidecars included, and fails if any plaintext
  appears in them.
- **Every failure path fails closed.** An unreadable database, an unknown KDF,
  an unknown token algorithm, a schema version with no migration — all raise
  rather than returning an empty result that a caller could read as "allowed".
- **All comparisons are on bytes.** `hmac.compare_digest` raises `TypeError` on
  non-ASCII `str`, and a raise on the authentication path is a crashed request
  thread rather than a refusal, so non-ASCII input is rejected at the parser
  before any digest exists.
- **One refusal message.** "Already used", "expired" and "never existed" are
  one public answer; separating them would tell an attacker which guesses were
  once real codes. The operator gets the distinction from the audit rows.
- **The operator names the device.** The label is chosen when the code is
  issued, so no string supplied by a caller ever reaches an operator listing,
  and no terminal control character reaches an operator terminal.
- **Read-only.** A verified device id is the entire output. No type here has a
  field that could carry an order, a position or a credential.

## Why a pairing code can be short

A code is 8 characters from a 31-character alphabet — about 40 bits — because a
person has to read it off one screen and type it into another. That is only
safe because three things hold at once: the code lives for ten minutes, it works
once, and redemption is capped at five attempts per client per minute. Even a
thousand cooperating addresses get roughly three million guesses inside the
window, against 10^12 codes. The alphabet omits `0/O` and `1/I/L` so a
mistyped character is a wrong code rather than a wrong reading.

`scrypt` at n=2^14 is what protects the codes if the database itself is stolen,
where the rate limit no longer applies. The cost parameters are stored next to
each hash, so raising them later does not invalidate a code an operator is in
the middle of reading out.

## Storage

One SQLite file, mode 0600, in a directory the service refuses to use if anyone
else can write it — a writable directory means the database can be moved aside
and replaced with one that pairs an attacker's phone. The schema is versioned in
`PRAGMA user_version`; a version this build does not know is refused rather than
guessed at, and there is no migration path yet to guess with.

Every operation opens its own connection, so one `DeviceStore` is safe to share
across the threads of a `ThreadingHTTPServer`. Timestamps are stored as
fixed-width UTC text so that SQLite's ordering of the text is the ordering of
the instants; the clock is injectable so expiry is tested without sleeping.

| Table | What it is for |
| --- | --- |
| `pairing_codes` | Live and recently dead codes, hashed, with their KDF parameters. |
| `devices` | One row per paired phone: salt, keyed hash, label, last seen, revocation. |
| `pairing_attempts` | The rate-limit window and the operator's audit trail. |

## Operator commands

```bash
PYTHONPATH=services/device_auth/src \
  python3 -m us_stock_helper_device_auth pair --label franz-iphone

PYTHONPATH=services/device_auth/src \
  python3 -m us_stock_helper_device_auth devices

PYTHONPATH=services/device_auth/src \
  python3 -m us_stock_helper_device_auth revoke <device-id> --reason "phone lost"

PYTHONPATH=services/device_auth/src \
  python3 -m us_stock_helper_device_auth attempts --client 203.0.113.9
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `DEVICE_AUTH_DATABASE` | `~/.us-stock-helper/device-auth.sqlite3` | Credential file; `--database` overrides it. |

`pair` also takes `--ttl-minutes` (default 10, one hour maximum). At most five
codes may be live at once; the rest of the cap clears by expiry, not by restart.

## Calling it from an HTTP boundary

```python
service = DeviceAuthService(store=DeviceStore(path))

verified = service.verify_token(bearer_token)
if not verified.authorized:
    return 401, {"error": {"code": "AUTH_REQUIRED", "message": verified.reason}}

outcome = service.redeem_pairing_code(submitted, client_id=peer_address)
if outcome.token is None:
    status = 429 if outcome.retry_after_seconds is not None else 401
```

`DeviceAuthError` must become a 5xx, never a 401 that a caller could mistake for
a bad credential: it means the credential store could not be consulted at all.

## Not implemented, deliberately

- **No token expiry.** Tokens end by revocation only. A device that is lost is
  revoked; a device that is idle is not guessed about.
- **No HTTP endpoint.** Wiring redemption and verification into `analysis_api`
  is a separate change, so that this package can be reviewed on its own.
- **No global rate limit.** A cap shared across all callers would let anyone on
  the internet lock the operator out of pairing their own phone. The per-client
  cap plus the code's own entropy is what holds.

## Run tests

```bash
cd services/device_auth && PYTHONPATH="src:tests" python3 -m pytest -q
```
