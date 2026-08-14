# Durable Local Runtime P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` and keep one implementation task active at a time.

**Goal:** Keep the two market gateways, analysis API, and Expo dev-client Metro alive under the user's macOS login session after the launching terminal or Codex task exits.

**Architecture:** Four independent user LaunchAgents invoke one standard-library Python launcher. The launcher parses the existing private `~/.us-stock-helper/lan.env` as inert `KEY=VALUE` data, builds a component-specific environment, and `execve`s exactly one service. A small lifecycle CLI renders and validates plists, refuses unknown target listeners, and manages only the four exact labels it owns.

**P0 boundary:** This slice does not invent a worker. Durable scheduled scans, alert threads, and session-flow history require a real SQLite lease/job implementation and remain a separate product slice. It also does not change the household-LAN Debug credential model or claim Release/TestFlight readiness.

## Fixed runtime contract

- `com.franz.us-stock-helper.market-loopback`: `127.0.0.1:8765`
- `com.franz.us-stock-helper.market-lan`: `0.0.0.0:8766`
- `com.franz.us-stock-helper.analysis-api`: `0.0.0.0:8770`
- `com.franz.us-stock-helper.metro`: `0.0.0.0:8088`, Node 22
- OpenD stays external on `127.0.0.1:11111`; an offline OpenD must not terminate a gateway.
- Unknown listeners on `8765`, `8766`, `8770`, or `8088` block installation and receive no signal.
- Existing listeners on legacy `8081`/`8083` are reported and left untouched.
- All interpreter, launcher, repository, working-directory, plist, and log paths are absolute.
- Plists use `RunAtLoad`, `KeepAlive`, `ThrottleInterval`, integer `Umask = 63`, independent stdout/stderr logs, and no credential-bearing `EnvironmentVariables`.
- Runtime/log directories are `0700`; environment, ownership, plist staging, and logs are `0600`.
- No command evaluates or `source`s the environment file. No secret value, raw response body, raw exception, pairing code, or Authorization value enters status, health, logs, or tests.
- Gateways and Metro never receive `ANTHROPIC_API_KEY`; analysis never receives `MOOMOO_GATEWAY_TOKEN`.
- Metro uses the tracked project and local `.env` behavior, with `EXPO_PUBLIC_INITIAL_DEMO_MODE=false`; Debug public tokens remain a household-LAN limitation and continue to be forbidden in Release.
- No `config.yaml` is introduced. The operator-owned private env file remains the single local secret source.

## Task 1: Strict environment parser and component isolation

**Files**

- Create: `scripts/local_runtime_support.py`
- Create: `scripts/tests/test_local_runtime_environment.py`

**RED tests**

- Refuse a non-regular env file, mode other than `0600`, non-private runtime parent, duplicate/unknown/invalid keys, missing `=`, NUL/control characters, shell syntax, quotes-as-syntax, `$()`, backticks, and substitutions.
- Accept blank lines, comments, and the exact current key set without exposing values.
- Build fixed minimal environments and prove secret separation for all four components.
- Atomically create/chmod runtime and log files without printing values.

**GREEN implementation**

- Add immutable component specs and injectable filesystem/process runners.
- Parse bytes as UTF-8 inert assignments; never mutate `os.environ`.
- Use fixed `PATH`, explicit `HOME`/`TMPDIR` only where required, the venv CA bundle, and exact per-component variables.

**Verify and commit**

```bash
PYTHONPATH=. python3 -m unittest scripts.tests.test_local_runtime_environment -v
git diff --check
git add scripts/local_runtime_support.py scripts/tests/test_local_runtime_environment.py
git commit -m "feat: isolate local runtime environments"
git push origin feature/iphone-demo
```

## Task 2: Absolute launchers and four LaunchAgent templates

**Files**

- Create: `scripts/local_runtime_launch.py`
- Create: `runtime/launchagents/com.franz.us-stock-helper.market-loopback.plist.in`
- Create: `runtime/launchagents/com.franz.us-stock-helper.market-lan.plist.in`
- Create: `runtime/launchagents/com.franz.us-stock-helper.analysis-api.plist.in`
- Create: `runtime/launchagents/com.franz.us-stock-helper.metro.plist.in`
- Create: `scripts/tests/test_local_runtime_plists.py`

**RED tests**

- Exactly four labels/templates; every rendered plist passes `plistlib` and `plutil -lint`.
- Program arguments and working directories are absolute; Metro is exactly `8088` with the tested Node 22 binary.
- Every plist has independent private logs, `KeepAlive`, restart throttling, and `Umask == 63`.
- No plist contains a token/key value, shell command, or broad inherited environment.
- Unknown components, missing binaries, wrong repository identity, or unsafe file modes fail closed.

**GREEN implementation**

- The launcher validates inputs, changes to the exact worktree, builds the isolated child environment, and calls `os.execve` so launchd owns the real service PID.
- Metro command is the absolute Node 22 binary plus the absolute Expo CLI: `start --dev-client --lan --port 8088`.

**Verify and commit**

```bash
PYTHONPATH=. python3 -m unittest scripts.tests.test_local_runtime_plists -v
git diff --check
git add scripts/local_runtime_launch.py runtime/launchagents scripts/tests/test_local_runtime_plists.py
git commit -m "feat: define isolated macOS launch agents"
git push origin feature/iphone-demo
```

## Task 3: Non-interactive lifecycle CLI and safe listener ownership

**Files**

- Create: `scripts/local_runtime.py`
- Modify: `scripts/local_runtime_support.py`
- Create: `scripts/tests/test_local_runtime_cli.py`
- Create: `scripts/tests/test_local_runtime_ownership.py`

**CLI**

```text
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status [--json]
python3 scripts/local_runtime.py health [--json]
python3 scripts/local_runtime.py reinstall
python3 scripts/local_runtime.py uninstall
```

**RED tests**

- Unknown target listeners abort before plist installation/bootstrap and receive no signal.
- Legacy `8081`/`8083` listeners are reported only.
- Installation validates every staged plist before the first `launchctl bootstrap gui/<uid>`.
- Partial bootstrap failure boots out only labels loaded by that attempt and preserves private data/logs.
- Reinstall/uninstall operate only on exact installed labels; ordinary uninstall preserves env, device DB, and logs.
- Status/health expose only fixed metadata and independently report stopped/unhealthy components.
- No output contains env values, credentials, response bodies, or raw exceptions.

**GREEN implementation**

- Resolve the repository from the script path and pin the current branch worktree intentionally.
- Precreate all private paths and logs, render/validate all plists, atomically install them, then bootstrap independently.
- Store only non-secret ownership metadata: label, PID/start time when available, executable, cwd, command fingerprint, and port.
- Use bounded HTTP health checks that retain numeric status and allowlisted error codes only.

**Verify and commit**

```bash
PYTHONPATH=. python3 -m unittest \
  scripts.tests.test_local_runtime_environment \
  scripts.tests.test_local_runtime_plists \
  scripts.tests.test_local_runtime_ownership \
  scripts.tests.test_local_runtime_cli -v
git diff --check
git add scripts/local_runtime.py scripts/local_runtime_support.py \
  scripts/tests/test_local_runtime_cli.py scripts/tests/test_local_runtime_ownership.py
git commit -m "feat: manage the durable local runtime"
git push origin feature/iphone-demo
```

## Task 4: Operator runbook and foreground-supervisor retirement

**Files**

- Modify: `scripts/run_local_dev_stack.sh`
- Modify: `docs/runbooks/local-real-market.md`
- Modify: `docs/runbooks/iphone-dev-client.md`
- Modify: `services/market_gateway/RUNBOOK.md`
- Modify: `services/analysis_api/README.md`
- Modify: `apps/mobile/README.md`
- Modify: `scripts/tests/test_local_runtime_cli.py`

**RED tests**

- Normal instructions use `local_runtime.py`; no runbook calls the foreground supervisor the durable path.
- `8088` is the only canonical Metro port; `8081`/`8083` appear only as legacy listeners that must not be killed by port alone.
- The old script cannot source env, launch Python/Node, kill processes, or write `/tmp` logs; it prints the migration command only.
- Docs distinguish household-LAN Debug from paired HTTPS Release and state what uninstall preserves.

**GREEN implementation**

- Replace the old foreground supervisor with a fixed deprecation message after the LaunchAgents have passed live acceptance.
- Document install/status/health/reinstall/uninstall, OpenD offline recovery, exact-label restart, token hygiene, and the dev-client deep-link/rebuild path.

**Verify and commit**

```bash
PYTHONPATH=. python3 -m unittest scripts.tests.test_local_runtime_cli -v
rg -n '8081|8083|8088|run_local_dev_stack.sh' \
  docs/runbooks apps/mobile/README.md services/analysis_api/README.md \
  services/market_gateway/RUNBOOK.md
git diff --check
git add scripts/run_local_dev_stack.sh docs/runbooks/local-real-market.md \
  docs/runbooks/iphone-dev-client.md services/market_gateway/RUNBOOK.md \
  services/analysis_api/README.md apps/mobile/README.md \
  scripts/tests/test_local_runtime_cli.py
git commit -m "docs: operate the local stack through launchd"
git push origin feature/iphone-demo
```

## Task 5: Live handoff and persistence acceptance

1. Run all runtime tests and the existing gateway/analysis/mobile suites.
2. Render and validate all four plists before touching the running stack.
3. Record the exact PID, start time, executable, cwd, command, parent, and listeners for the known foreground supervisor and its three children.
4. TERM only that revalidated exact supervisor; wait up to 15 seconds; never use KILL. Leave `8081` and legacy `8083` untouched.
5. Install/bootstrap the four LaunchAgents and verify `8765`, `8766`, `8770`, and `8088` independently.
6. Run the safe health command and a single SOFI v3/day snapshot plus deterministic decision check with adviser off.
7. Restart each exact label with `launchctl kickstart -k`; prove the other three PID/start-time identities do not change.
8. From a fresh non-parent shell, re-run status/health and prove all labels remain loaded. This is the terminal-session-independence gate.
9. Launch the simulator through `8088`; capture Real Dashboard, SOFI detail, and SOFI full-chart screenshots under `/tmp` only.
10. Confirm repository HEAD equals `origin/feature/iphone-demo`, tracked status is clean, and no env/token/DB/log/generated plist/report is tracked.

The P0 runtime is complete only when all four LaunchAgents survive their installer process, their exact-label restart isolation is green, and the Real simulator still reads live day data through them. Physical-iPhone and signed Release/TestFlight acceptance remain explicit external gates.
