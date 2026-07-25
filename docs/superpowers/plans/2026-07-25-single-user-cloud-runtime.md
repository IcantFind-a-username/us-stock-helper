# Single User Cloud Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the verified real-market slice continuously on one Singapore server, bind one iPhone through a revocable pairing token, and synchronize editable trade journals plus compact personal-risk memory without exposing OpenD or allowing any broker transaction.

**Architecture:** Add a versioned `cloud_api` in front of the loopback-only market gateway and PostgreSQL. The public process accepts HTTPS traffic only through Caddy, authenticates one paired device, proxies the allowlisted read-only market endpoints, and owns journal CRUD. Pairing codes are short-lived and single-use; device secrets live in iOS Keychain and only keyed hashes live in PostgreSQL. Objective market data and personal journal memory use separate types, tables, services, and tests so personal preferences can affect only personal-fit warnings.

**Tech Stack:** Ubuntu LTS on AWS Lightsail Singapore (`ap-southeast-1`), Python 3.12, FastAPI, Uvicorn, Pydantic v2, psycopg 3, PostgreSQL 16, Alembic, Argon2id, Caddy, systemd, Terraform, pytest; Expo SDK 57, `expo-secure-store`, AsyncStorage offline queue, Jest Expo, React Native Testing Library, Xcode Release/TestFlight.

## Global Constraints

- Written authority: `docs/superpowers/specs/2026-07-25-real-market-backend-v1-design.md`.
- Execute this plan after `2026-07-25-real-market-mobile-vertical-slice.md` passes on a physical iPhone.
- Deploy in AWS Singapore. OpenD, PostgreSQL, and the market gateway bind to loopback or a private Unix socket only.
- Public ingress is TCP 443 through Caddy. Do not expose OpenD `11111`, PostgreSQL `5432`, the gateway `8765`, Uvicorn, SSH password authentication, or a development Metro server.
- Use only moomoo quote context. Cloud configuration contains no trade password and no trading route.
- The app has no traditional user/password login. One short-lived pairing code binds a device and returns a revocable device token.
- Device tokens are generated from at least 32 random bytes, never logged, never stored in plaintext server-side, and stored only in iOS Keychain client-side.
- Pairing attempts are rate-limited and codes are single-use. Revocation immediately blocks the device.
- Journal records are user-entered facts, not broker orders. Journal endpoints never call OpenD.
- Objective market memory and personal journal memory are structurally separated. The same market evidence must produce the same objective score regardless of journal contents.
- Personal memory may change only personal-fit explanations and risk warnings; it cannot alter facts, citations, market direction, base score, confidence, or counter-evidence.
- Logs contain request IDs and result classes, never full journal text, pairing codes, device tokens, OpenD credentials, moomoo account identifiers, or authorization headers.
- All timestamps are UTC in storage and APIs. The UI may additionally show US Eastern time.
- Backups are encrypted, retained for 14 days, and restore-tested. The user can export and delete journal/memory data.
- Release builds contain an HTTPS API origin but no development bearer token, OpenD credential, AWS secret, database URL, or journal data.
- Terraform plans and any resource that incurs cost require the user's explicit approval immediately before `terraform apply`.

---

### Task 1: Scaffold the authenticated cloud API boundary

**Files:**
- Create: `services/cloud_api/pyproject.toml`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/__init__.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/config.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/errors.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/app.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/market_client.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/py.typed`
- Create: `services/cloud_api/tests/conftest.py`
- Create: `services/cloud_api/tests/test_app_boundary.py`
- Create: `services/cloud_api/tests/test_market_client.py`

**Interfaces:**
- `GET /v1/health`
- Authenticated `GET /v1/watchlist`
- Authenticated `GET /v1/stocks/{symbol}/snapshot?interval=5m&count=200`
- Authenticated `GET /v1/stocks/{symbol}/institutional-holdings`
- `MarketGatewayClient` talks only to `http://127.0.0.1:8765`

- [ ] **Step 1: Declare a pinned service package**

Use Python 3.12 and bounded dependencies:

```toml
dependencies = [
  "fastapi>=0.116,<1",
  "uvicorn[standard]>=0.35,<1",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.10,<3",
  "httpx>=0.28,<1",
  "psycopg[binary]>=3.2,<4",
  "alembic>=1.16,<2",
  "argon2-cffi>=25.1,<26"
]
```

Test dependencies are `pytest`, `pytest-asyncio`, and `mypy`.

- [ ] **Step 2: Write failing configuration and route-boundary tests**

Assert startup rejects:

- a non-loopback gateway URL;
- a missing database URL;
- a device-token pepper shorter than 32 bytes;
- `http://` public origin outside test/development;
- any setting name containing trade password/unlock data.

Assert only the listed routes exist, unhandled exceptions return a sanitized request ID, and OpenAPI contains no order/trade/account route.

- [ ] **Step 3: Run focused tests and observe RED**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_app_boundary.py services/cloud_api/tests/test_market_client.py
```

Expected: collection fails because `cloud_api` is absent.

- [ ] **Step 4: Implement strict settings and sanitized errors**

`CloudSettings` reads secrets from environment or systemd credentials. `MARKET_GATEWAY_URL` must parse to loopback. Error bodies contain:

```json
{"error":{"code":"MARKET_UNAVAILABLE","message":"Market data is temporarily unavailable","retriable":true},"requestId":"..."}
```

Never copy provider exception strings directly to the client.

- [ ] **Step 5: Implement the internal read-only client**

Allow exactly `/health`, `/watchlist`, `/stock-snapshot`, and `/institutional-holdings`. Enforce a 5-second timeout, response size cap, schema version, source, and cutoff checks. Forward no public `Authorization` header to the gateway.

- [ ] **Step 6: Add temporary test authentication dependency**

Define `require_device()` as a dependency backed by a `DeviceAuthenticator` protocol. Tests inject an allow/deny fake. The real token implementation arrives in Task 2.

- [ ] **Step 7: Run checks and commit**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests
PYTHONPATH=services/cloud_api/src mypy services/cloud_api/src
rg -n "OpenSecTradeContext|unlock_trade|place_order|modify_order|cancel_order" services/cloud_api
```

Expected: tests and mypy pass; `rg` has no matches.

```bash
git add services/cloud_api
git commit -m "feat: add hardened cloud api boundary"
```

---

### Task 2: Implement one-time device pairing and revocation

**Files:**
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/db.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/auth.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/pairing_cli.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/migrations/env.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/migrations/versions/0001_device_auth.py`
- Create: `services/cloud_api/alembic.ini`
- Create: `services/cloud_api/tests/compose.postgres.yml`
- Modify: `services/cloud_api/src/us_stock_helper_cloud_api/app.py`
- Modify: `services/cloud_api/pyproject.toml`
- Create: `services/cloud_api/tests/test_device_auth.py`
- Create: `services/cloud_api/tests/test_pairing_api.py`

**Interfaces:**
- Local admin command: `us-stock-helper-pairing issue --ttl-minutes 10`
- Public rate-limited `POST /v1/device-pairings`
- Authenticated `POST /v1/device-token/rotate`
- Local admin command: `us-stock-helper-pairing revoke --device-id <uuid>`

- [ ] **Step 1: Write failing token-security tests**

Assert:

- pairing code expires after 10 minutes;
- code works once and replay fails;
- five wrong attempts from one IP trigger a 15-minute lockout;
- issued device token has at least 256 bits;
- database rows contain only code/token hashes;
- constant-time token verification succeeds;
- revoked and expired devices receive 401;
- rotation invalidates the old token after a 24-hour overlap;
- auth logs contain neither code nor token.

- [ ] **Step 2: Run focused tests and observe RED**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_device_auth.py services/cloud_api/tests/test_pairing_api.py
```

- [ ] **Step 3: Add the database schema**

Create:

```text
pairing_codes(id, code_hash, created_at, expires_at, consumed_at, failed_attempts)
devices(id, display_name, token_hash, previous_token_hash, previous_valid_until,
        created_at, last_seen_at, expires_at, revoked_at)
auth_attempts(id, ip_hash, occurred_at, succeeded)
```

Use Argon2id for low-entropy pairing-code hashes. Use HMAC-SHA256 with the server pepper for random device-token lookup. Do not persist IP addresses; store a rotating keyed hash for rate limiting.

- [ ] **Step 4: Implement issuance, validation, rotation, and revocation**

Pairing returns the plaintext token exactly once:

```json
{"deviceId":"uuid","deviceToken":"opaque-secret","expiresAt":"..."}
```

Every later response omits the token. The CLI prints the pairing code to the local TTY and never writes it to a file or application log.

- [ ] **Step 5: Wire authentication into every non-health market route**

`GET /v1/health` returns only public API health, not moomoo account details. `/v1/device-pairings` is unauthenticated but rate-limited. Every market, journal, preference, export, and delete endpoint requires an active device.

- [ ] **Step 6: Run migrations and tests against PostgreSQL**

Start an ephemeral local PostgreSQL 16 container bound to loopback:

```bash
docker compose -f services/cloud_api/tests/compose.postgres.yml up -d
PYTHONPATH=services/cloud_api/src alembic -c services/cloud_api/alembic.ini upgrade head
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_device_auth.py services/cloud_api/tests/test_pairing_api.py
docker compose -f services/cloud_api/tests/compose.postgres.yml down
```

Expected: migration and tests pass; the database contains no plaintext secrets.

- [ ] **Step 7: Commit**

```bash
git add services/cloud_api
git commit -m "feat: pair and revoke one mobile device"
```

---

### Task 3: Persist complete manual trade journals

**Files:**
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/journal_models.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/journal_repository.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/journal_routes.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/migrations/versions/0002_journal.py`
- Modify: `services/cloud_api/src/us_stock_helper_cloud_api/app.py`
- Create: `services/cloud_api/tests/test_journal_repository.py`
- Create: `services/cloud_api/tests/test_journal_api.py`
- Create: `services/cloud_api/tests/test_log_redaction.py`

**Interfaces:**
- `GET /v1/journal?cursor=<opaque>&limit=50`
- `POST /v1/journal`
- `PATCH /v1/journal/{id}` with optimistic `version`
- `DELETE /v1/journal/{id}`
- `GET /v1/journal/export`
- `DELETE /v1/personal-data`

- [ ] **Step 1: Write failing schema and ownership tests**

The request/response model includes:

```text
symbol, side, horizon,
openedAt, exitedAt,
entryPrice, exitPrice, stopPrice,
quantity, notional, leverage, fees,
thesis, invalidation,
strategyTags, evidenceIds,
pnl, mae, mfe, executionDeviation,
selfRating, lesson,
createdAt, updatedAt, version
```

Reject invalid symbols, non-finite/negative monetary fields where inappropriate, leverage below 0 or above the configured safety ceiling, exit before entry, mismatched notional, invalid evidence IDs, oversized text, and naive timestamps.

Assert device A can never read or mutate device B data even though V1 has one device.

- [ ] **Step 2: Run the focused tests and observe RED**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_journal_repository.py services/cloud_api/tests/test_journal_api.py
```

- [ ] **Step 3: Add normalized journal storage**

Create `journal_entries` with a UUID primary key, `device_id` foreign key, typed numeric columns, JSONB only for bounded string arrays, `version`, and timestamps. Create indexes on `(device_id, opened_at DESC)`, `(device_id, symbol, opened_at DESC)`, and `(device_id, strategy_tags)`.

- [ ] **Step 4: Implement optimistic CRUD**

POST accepts an idempotency key. PATCH requires the last seen version and returns 409 on conflict. DELETE is recoverable for 30 days through `deleted_at`; `/v1/personal-data` permanently deletes all journal and personal-memory rows after a second signed confirmation nonce.

- [ ] **Step 5: Implement streaming export**

Export newline-delimited JSON or CSV with a deterministic schema. It includes the user's journal and personal-memory summaries, not device-token hashes or server secrets.

- [ ] **Step 6: Prove log redaction**

Capture application logs while submitting unique marker strings in thesis, lesson, Authorization, and pairing fields. Assert no marker occurs. Record only route template, status, duration, device UUID suffix hash, and request ID.

- [ ] **Step 7: Run tests and commit**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_journal_repository.py services/cloud_api/tests/test_journal_api.py services/cloud_api/tests/test_log_redaction.py
PYTHONPATH=services/cloud_api/src mypy services/cloud_api/src
```

```bash
git add services/cloud_api
git commit -m "feat: persist secure manual trade journals"
```

---

### Task 4: Build the objective/personal memory firewall

**Files:**
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/journal_memory.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/migrations/versions/0003_personal_memory.py`
- Create: `services/cloud_api/src/us_stock_helper_cloud_api/preference_routes.py`
- Modify: `services/cloud_api/src/us_stock_helper_cloud_api/app.py`
- Create: `services/cloud_api/tests/test_journal_memory.py`
- Create: `services/cloud_api/tests/test_memory_firewall.py`

**Interfaces:**
- `GET /v1/preferences`
- `PATCH /v1/preferences/{memory_id}` to correct or dismiss a learned item
- `JournalMemoryBuilder.rebuild(device_id, journal_rows) -> PersonalMemorySummary`
- `PersonalFitService.evaluate(objective_snapshot, personal_memory) -> PersonalFitOutput`

- [ ] **Step 1: Write failing compact-summary tests**

Given journal fixtures, assert deterministic aggregates for:

- horizon/side/strategy counts and realized win rate;
- average P&L, MAE, MFE, fees, leverage, and execution deviation;
- recent relevant records by symbol and strategy;
- repeated behavior flags such as chasing, oversized leverage, holding losers, and premature exits;
- stable user-stated preferences kept separate from inferred patterns.

The compact serialized summary must stay below 4 KB for 10,000 journal rows.

- [ ] **Step 2: Write the firewall property test**

For the same objective snapshot, generate many personal-memory variations and assert:

```python
assert result.objective_score == original.objective_score
assert result.direction == original.direction
assert result.confidence == original.confidence
assert result.facts == original.facts
assert result.citations == original.citations
assert result.counter_evidence == original.counter_evidence
```

Only `personal_fit`, `risk_warnings`, and `execution_cautions` may differ.

- [ ] **Step 3: Run tests and observe RED**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests/test_journal_memory.py services/cloud_api/tests/test_memory_firewall.py
```

- [ ] **Step 4: Implement deterministic precomputation**

Build personal summaries with SQL aggregates and pure Python rules. No LLM call is required to calculate facts. Store derived items with evidence journal IDs, method version, confidence, created time, and correction/dismissal state.

- [ ] **Step 5: Implement token-bounded retrieval**

For an adviser request, retrieve:

1. aggregate statistics;
2. up to five recent relevant trades;
3. up to five strongest repeated behavior flags;
4. explicit user preferences;
5. the objective evidence package separately.

Never send the full journal history or hidden deleted records.

- [ ] **Step 6: Add preference correction UI contract**

The API lets the user correct, dismiss, export, or delete learned personal items. A correction changes only personal memory, never objective market records.

- [ ] **Step 7: Run tests and commit**

```bash
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests
PYTHONPATH=services/cloud_api/src mypy services/cloud_api/src
```

```bash
git add services/cloud_api
git commit -m "feat: isolate compact personal risk memory"
```

---

### Task 5: Pair the iPhone and store credentials in Keychain

**Files:**
- Modify: `apps/mobile/package.json`
- Modify: `apps/mobile/package-lock.json`
- Modify: `apps/mobile/app.json`
- Modify: generated SecureStore-linked files under `apps/mobile/ios/`
- Create: `apps/mobile/src/security/deviceCredentialStore.ts`
- Create: `apps/mobile/src/security/__tests__/deviceCredentialStore.test.ts`
- Create: `apps/mobile/src/data/cloudClient.ts`
- Create: `apps/mobile/src/data/__tests__/cloudClient.test.ts`
- Create: `apps/mobile/src/state/DeviceSessionProvider.tsx`
- Create: `apps/mobile/src/state/__tests__/DeviceSessionProvider.test.tsx`
- Create: `apps/mobile/src/screens/PairDeviceScreen.tsx`
- Create: `apps/mobile/src/screens/__tests__/PairDeviceScreen.test.tsx`
- Create: `apps/mobile/src/app/pair-device.tsx`
- Modify: `apps/mobile/src/app/_layout.tsx`

**Interfaces:**
- `DeviceCredentialStore.get/set/clear`
- `CloudClient.pair(code, deviceName)`
- `CloudClient.rotateToken()`
- `useDeviceSession()` returns `unpaired | pairing | paired | revoked | offline`

- [ ] **Step 1: Install SecureStore with the Expo-compatible version**

```bash
cd apps/mobile
npx expo install expo-secure-store
```

Add the SecureStore config plugin. Do not store the token in AsyncStorage, app logs, React query cache, crash reports, or Expo public config.

- [ ] **Step 2: Write failing credential-store tests**

Mock SecureStore and assert token write/read/delete, accessibility after first device unlock, no token in thrown errors, and clearing on server revocation. Assert production runtime rejects `EXPO_PUBLIC_MARKET_GATEWAY_TOKEN`.

- [ ] **Step 3: Write failing cloud-client tests**

Assert HTTPS-only production origin, pairing payload, bearer authorization, 401 transition to revoked, sanitized error mapping, no authorization forwarding across redirects, timeout, and certificate failure.

- [ ] **Step 4: Run focused tests and observe RED**

```bash
cd apps/mobile
npm test -- src/security/__tests__/deviceCredentialStore.test.ts src/data/__tests__/cloudClient.test.ts src/state/__tests__/DeviceSessionProvider.test.tsx src/screens/__tests__/PairDeviceScreen.test.tsx
```

- [ ] **Step 5: Implement the pairing screen**

Show one code field, device name, expiry/rate-limit errors, and the analysis-only privacy boundary. On success, store the token in Keychain and navigate to the dashboard. Do not show a username/password UI.

- [ ] **Step 6: Route all production market calls through `CloudClient`**

Development may still target the local gateway. Release mode must use the paired HTTPS cloud origin. Rotate a token when less than 30 days remain, keeping the current session if rotation is temporarily offline.

- [ ] **Step 7: Rebuild the native development client and run checks**

SecureStore changes the native app and requires an Xcode rebuild:

```bash
cd apps/mobile
npx expo prebuild --platform ios
npx expo run:ios --device
npm test -- --runInBand
npm run typecheck
npm run lint
```

Expected: the physical iPhone pairs, restarts, and remains paired without exposing the token.

- [ ] **Step 8: Commit**

```bash
git add apps/mobile
git commit -m "feat: securely pair the iphone"
```

---

### Task 6: Synchronize journal CRUD and offline edits

**Files:**
- Modify: `apps/mobile/src/domain/models.ts`
- Modify: `apps/mobile/src/domain/journal.ts`
- Modify: `apps/mobile/src/components/journal/JournalEntryForm.tsx`
- Modify: `apps/mobile/src/screens/JournalScreen.tsx`
- Modify: `apps/mobile/src/state/AppStateProvider.tsx`
- Create: `apps/mobile/src/data/journalRepository.ts`
- Create: `apps/mobile/src/data/__tests__/journalRepository.test.ts`
- Create: `apps/mobile/src/state/__tests__/JournalSync.test.tsx`
- Modify: `apps/mobile/src/screens/__tests__/JournalScreen.test.tsx`

**Interfaces:**
- `JournalRepository.list/create/update/remove/export`
- Offline mutation record `{operationId, kind, journalId, baseVersion, payload, createdAt}`
- App state adds `updateJournalEntry`, `deleteJournalEntry`, `refreshJournal`, and `journalSyncStatus`

- [ ] **Step 1: Expand the mobile journal contract**

Add all fields from Task 3. Keep numerical validation in a pure domain helper. The form separates planned values, actual execution, risk, result, and lesson into progressive sections without changing the approved Calm Alpha styling.

- [ ] **Step 2: Write failing sync tests**

Assert:

- remote rows hydrate after pairing;
- create/update/delete round-trip;
- restart retains pending offline edits;
- idempotency prevents duplicate creates;
- mutations replay in order after reconnect;
- version conflict preserves both local draft and server row for user resolution;
- server deletion removes the local row;
- journal text never enters objective market state;
- export/delete-personal-data flows require confirmation.

- [ ] **Step 3: Run focused tests and observe RED**

```bash
cd apps/mobile
npm test -- src/data/__tests__/journalRepository.test.ts src/state/__tests__/JournalSync.test.tsx src/screens/__tests__/JournalScreen.test.tsx
```

- [ ] **Step 4: Implement a durable bounded offline queue**

Store journal payloads and mutation queue in AsyncStorage because they are user content, while the bearer token remains in Keychain. Cap automatic retries and surface conflicts. Do not silently overwrite a newer server version.

- [ ] **Step 5: Add edit/delete/export/personal-memory UI**

The Journal screen supports create, edit, delete, export, sync state, and learned preference review. It repeats the firewall: operations and P&L affect only personal fit and risk warnings.

- [ ] **Step 6: Run mobile checks**

```bash
cd apps/mobile
npm test -- --runInBand
npm run typecheck
npm run lint
```

- [ ] **Step 7: Commit**

```bash
git add apps/mobile
git commit -m "feat: sync trade journals and personal memory"
```

---

### Task 7: Codify the Singapore Lightsail deployment

**Files:**
- Create: `infra/lightsail/main.tf`
- Create: `infra/lightsail/variables.tf`
- Create: `infra/lightsail/outputs.tf`
- Create: `infra/lightsail/cloud-init.yaml.tftpl`
- Create: `infra/systemd/us-stock-helper-api.service`
- Create: `infra/systemd/us-stock-helper-gateway.service`
- Create: `infra/systemd/us-stock-helper-opend.service`
- Create: `infra/systemd/us-stock-helper-backup.service`
- Create: `infra/systemd/us-stock-helper-backup.timer`
- Create: `infra/caddy/Caddyfile`
- Create: `infra/postgres/pg_hba.conf`
- Create: `infra/scripts/backup.sh`
- Create: `infra/scripts/restore-check.sh`
- Create: `infra/scripts/health-check.sh`
- Create: `docs/runbooks/singapore-cloud-deployment.md`
- Create: `docs/runbooks/opend-relogin.md`

**Interfaces:**
- Terraform provisions one static-IP Lightsail instance in `ap-southeast-1`
- systemd starts PostgreSQL, OpenD, gateway, API, Caddy, backup timer, and health monitor
- Only Caddy is publicly reachable on 443

- [ ] **Step 1: Write deployment validation tests before provisioning**

Add a shell/static test that fails if:

- any service binds OpenD/gateway/PostgreSQL to `0.0.0.0`;
- the firewall opens 11111, 5432, 8000, 8765, or Metro ports;
- a secret-like literal is committed;
- systemd lacks restart/backoff/hardening;
- Caddy proxies a path outside `/v1`;
- backup scripts can upload unencrypted plaintext.

- [ ] **Step 2: Implement repeatable Terraform**

Variables require the AWS profile, SSH public-key path, HTTPS hostname, and snapshot time. Select the Singapore region, Ubuntu LTS blueprint, 2-vCPU/4-GB bundle, static IP, daily automatic snapshot, and firewall rules for 443 plus SSH restricted to the operator CIDR.

- [ ] **Step 3: Harden services**

Use dedicated Unix users, `ProtectSystem=strict`, `PrivateTmp=true`, `NoNewPrivileges=true`, explicit writable directories, memory limits, restart-on-failure, and systemd credentials for secrets. OpenD and the gateway listen on `127.0.0.1`; PostgreSQL accepts only local application credentials.

- [ ] **Step 4: Configure HTTPS and monitoring**

Caddy obtains/renews TLS for the configured hostname and adds HSTS, content-type, frame, and referrer headers. Health monitoring checks API, gateway, OpenD session, data freshness, disk, memory, and last backup, and sends a minimal notification when human moomoo re-login is required.

- [ ] **Step 5: Implement encrypted backup and restore check**

Back up PostgreSQL and configuration metadata without runtime secrets. Encrypt before upload, retain 14 daily copies, and run a weekly restore into a disposable local database followed by row-count and migration checks.

- [ ] **Step 6: Validate the Terraform plan**

```bash
terraform -chdir=infra/lightsail fmt -check
terraform -chdir=infra/lightsail init
terraform -chdir=infra/lightsail validate
terraform -chdir=infra/lightsail plan -out=/tmp/us-stock-helper.tfplan
```

Expected: one Singapore instance, one static IP, daily snapshot, and no public database/OpenD/gateway ports.

- [ ] **Step 7: Obtain explicit cost approval, then provision**

Show the Terraform plan and current AWS monthly estimate to the user. Only after approval:

```bash
terraform -chdir=infra/lightsail apply /tmp/us-stock-helper.tfplan
```

The user performs the one unavoidable interactive step: log the Singapore moomoo account into the official OpenD installation and confirm US quote permission. Do not bypass Gatekeeper/signatures or automate credentials.

- [ ] **Step 8: Run public exposure tests**

From outside the instance:

```bash
curl --fail --silent --show-error https://${API_HOSTNAME}/v1/health
nmap -Pn -p 443,11111,5432,8000,8765 ${STATIC_IP}
```

Expected: 443 open; 11111, 5432, 8000, and 8765 closed/filtered. Unpaired market requests return 401 without account details.

- [ ] **Step 9: Commit**

```bash
git add infra docs/runbooks
git commit -m "infra: codify singapore single-user runtime"
```

---

### Task 8: Ship and accept an independent iPhone Release build

**Files:**
- Create: `apps/mobile/eas.json`
- Modify: `apps/mobile/app.json`
- Modify: release signing/build settings under `apps/mobile/ios/`
- Create: `docs/runbooks/ios-release.md`
- Create: `scripts/verify_release_secrets.sh`

**Interfaces:**
- Release bundle identifier is distinct from the development client
- Release API origin is HTTPS
- App starts and operates without Metro

- [ ] **Step 1: Add release-secret scanning**

The script builds/export-inspects the iOS bundle and fails on:

- `MOOMOO_`, OpenD account IDs, AWS keys, database URLs;
- development bearer tokens;
- `localhost`, private LAN IPs, or Metro URLs;
- journal fixture text;
- trade-context or order-route strings.

- [ ] **Step 2: Configure signed release profiles**

Keep `com.franz.usstockhelper.dev` for development. Use `com.franz.usstockhelper` for Release, automatic signing with the user's Apple team, and an EAS/TestFlight profile that contains only the public HTTPS API origin.

- [ ] **Step 3: Build and install without Metro**

Archive in Xcode or build the TestFlight profile. Stop Metro before launch. Delete/reinstall once to verify the pairing flow, then restart the app and phone to verify Keychain persistence.

- [ ] **Step 4: Run the complete physical-device acceptance matrix**

Verify:

- Wi-Fi, cellular, and Singapore VPN;
- real moomoo watchlist and quote;
- real completed K-lines;
- aligned 100% participation bars with missing older coverage;
- MA5, RSI, MACD, Magic Nine under one cutoff;
- delayed institutional disclosure label;
- app behavior during VPN loss, API restart, OpenD restart, and moomoo re-login-required;
- pair, rotate, revoke, and re-pair;
- journal create/edit/delete/export across app restarts;
- offline journal replay and conflict handling;
- personal-memory correction/deletion;
- unchanged objective market output under different journal preferences;
- no order or auto-trade action anywhere.

- [ ] **Step 5: Run all automated verification**

```bash
PYTHONPATH=services/analysis_core python3 -m unittest discover -s services/analysis_core/tests -v
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m unittest discover -s services/market_gateway/tests -v
PYTHONPATH=services/cloud_api/src pytest -q services/cloud_api/tests
cd apps/mobile && npm test -- --runInBand && npm run typecheck && npm run lint
scripts/verify_release_secrets.sh
rg -n "OpenSecTradeContext|unlock_trade|place_order|modify_order|cancel_order" services apps/mobile
```

Expected: all pass; both security scans have no findings.

- [ ] **Step 6: Verify operations**

Reboot the Lightsail instance. Confirm systemd recovers API/gateway/OpenD, the iPhone reconnects, cached data stays correctly timestamped, backup succeeds, and the restore check passes. Simulate revoked OpenD login and verify the notification contains no account secret.

- [ ] **Step 7: Commit and push**

```bash
git add apps/mobile/eas.json apps/mobile/app.json docs/runbooks/ios-release.md scripts/verify_release_secrets.sh
git commit -m "release: prepare independent iphone app"
git push
```
