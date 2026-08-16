#!/usr/bin/env python3
"""Measure the real evidence_confidence distribution across the watchlist.

Task 5 Step 1 of docs/superpowers/plans/2026-08-17-authoritative-source-adapters.md:
before anyone touches the 0.35 INSUFFICIENT_EVIDENCE gate, measure what the
production pipeline actually computes per symbol, with the widened source
registry live. This script changes no threshold and writes no production
state — it is a measuring instrument.

How it measures: it builds the exact provider stack `analysis_api.__main__`
builds (gateway + evidence + factors + institutional flow), then wraps
`decision_engine.engine.extract_horizon_features` with a recorder so the
FeatureSet the scorer really sees — including `evidence_confidence`, which
the served payload does not expose — is captured per decision. No pipeline
step is reimplemented, so the numbers cannot drift from production.

State honesty: `ANALYSIS_API_COORDINATOR_STATE` is deliberately NOT set, so
this process starts with a fresh in-memory coordinator (it sees the full
lookback window, like a long-running server in steady state) and never
touches the production snapshot at ~/.us-stock-helper/state/coordinator.json.

Usage (from the worktree root; the running stack must be up for candles):

    python3 .superpowers/sdd/2026-08-17-authoritative-source-adapters/measure_evidence_gate.py
    python3 .../measure_evidence_gate.py --horizon short --out /tmp/gate_measurement.md
    python3 .../measure_evidence_gate.py --self-test   # no network, checks the math

Run it during a US trading session (weekday ~21:30–04:00 北京时间): a weekend
measurement reads empty feed windows and is exactly the starved input the
plan warns against tuning on. The script warns when run outside that window
but does not refuse — half-days exist.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


GATE = 0.35  # measured against, never changed here (scoring.py:450)

_WORKTREE = Path(__file__).resolve().parents[3]
_SERVICE_PATHS = (
    "services/analysis_api/src",
    "services/analysis_core",
    "services/information_layer",
    "services/adviser_layer",
    "services/decision_engine",
    "services/market_gateway/src",
    "services/adviser_llm/src",
    "services/device_auth/src",
)


def summarize(readings: list[dict]) -> dict:
    """Distribution statistics over per-symbol gate measurements.

    A reading is {"symbol", "evidence_confidence" (float|None), "blocked",
    "citations", "error" (str|None)}. None confidence means the decision
    never reached scoring (no candles, gateway error …) and is counted as
    unmeasured, never as zero — zero is a measured value.
    """

    values = [
        row["evidence_confidence"]
        for row in readings
        if row["evidence_confidence"] is not None
    ]
    return {
        "total": len(readings),
        "measured": len(values),
        "unmeasured": len(readings) - len(values),
        # The gate at scoring.py:450 fires strictly below GATE.
        "clears_gate": sum(1 for value in values if value >= GATE),
        "fires_gate": sum(1 for value in values if value < GATE),
        "zero_evidence": sum(1 for value in values if value == 0.0),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "median": statistics.median(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
    }


def _self_test() -> int:
    readings = [
        {"symbol": "AAA", "evidence_confidence": 0.99, "blocked": False,
         "citations": 3, "error": None},
        {"symbol": "BBB", "evidence_confidence": 0.35, "blocked": False,
         "citations": 1, "error": None},
        {"symbol": "CCC", "evidence_confidence": 0.30, "blocked": True,
         "citations": 1, "error": None},
        {"symbol": "DDD", "evidence_confidence": 0.0, "blocked": True,
         "citations": 0, "error": None},
        {"symbol": "EEE", "evidence_confidence": None, "blocked": False,
         "citations": 0, "error": "no candles"},
    ]

    stats = summarize(readings)

    assert stats["total"] == 5, stats
    assert stats["measured"] == 4, stats
    assert stats["unmeasured"] == 1, stats
    # The gate fires strictly below 0.35: 0.35 itself clears.
    assert stats["clears_gate"] == 2, stats
    assert stats["fires_gate"] == 2, stats
    assert stats["zero_evidence"] == 1, stats
    assert stats["minimum"] == 0.0, stats
    assert stats["maximum"] == 0.99, stats
    assert abs(stats["median"] - 0.325) < 1e-9, stats
    assert abs(stats["mean"] - (0.99 + 0.35 + 0.30 + 0.0) / 4) < 1e-9, stats
    # An empty measurement must say so, not divide by zero.
    empty = summarize([])
    assert empty["total"] == 0 and empty["measured"] == 0, empty
    assert empty["median"] is None and empty["mean"] is None, empty
    print("self-test passed")
    return 0


def _load_runtime_environment() -> None:
    """Read lan.env the way the launchd stack does, minus coordinator state."""

    lan_env = Path.home() / ".us-stock-helper" / "lan.env"
    if not lan_env.exists():
        raise SystemExit(f"missing {lan_env}: the runtime environment file")
    for line in lan_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    # Same gateway origin the analysis-api component uses.
    os.environ.setdefault("ANALYSIS_API_GATEWAY_URL", "http://127.0.0.1:8765")
    # Deliberately absent: ANALYSIS_API_COORDINATOR_STATE (see module docstring).
    os.environ.pop("ANALYSIS_API_COORDINATOR_STATE", None)


def _warn_if_outside_market_hours(now: datetime) -> None:
    # US cash session 13:30–20:00 UTC (EDT); weekday check in UTC is close
    # enough for a warning.
    weekday = now.weekday() < 5
    in_hours = 13 <= now.hour < 21
    if not (weekday and in_hours):
        print(
            "⚠️  当前不在美股常规交易时段：feed 回看窗口可能为空，"
            "此时的分布是饥饿输入，不适合作为调阈值依据。"
        )


def _measure(horizon: str, limit: int | None) -> list[dict]:
    for relative in _SERVICE_PATHS:
        sys.path.insert(0, str(_WORKTREE / relative))

    import decision_engine.engine as engine_module
    from us_stock_helper_analysis_api.evidence_provider import (
        CompositeAnalysisProvider,
        evidence_provider_from_environment,
    )
    from us_stock_helper_analysis_api.factor_provider import (
        factor_provider_from_environment,
    )
    from us_stock_helper_analysis_api.gateway_provider import (
        provider_from_environment,
    )
    from us_stock_helper_analysis_api.institutional_flow_provider import (
        GatewayInstitutionalFlowProvider,
    )
    from us_stock_helper_analysis_api.service import AnalysisService

    captured: list = []
    real_extract = engine_module.extract_horizon_features

    def recording_extract(*args, **kwargs):
        features = real_extract(*args, **kwargs)
        captured.append(features)
        return features

    engine_module.extract_horizon_features = recording_extract

    gateway = provider_from_environment()
    provider = CompositeAnalysisProvider(
        bars=gateway,
        evidence=evidence_provider_from_environment(),
        factors=factor_provider_from_environment(),
        institutional_flow=GatewayInstitutionalFlowProvider(gateway=gateway),
    )
    service = AnalysisService(provider)

    symbols = list(provider.watchlist_symbols())
    if limit is not None:
        symbols = symbols[:limit]
    print(f"watchlist: {len(symbols)} symbols, horizon={horizon}")

    readings: list[dict] = []
    for index, symbol in enumerate(symbols, start=1):
        captured.clear()
        error: str | None = None
        blocked = False
        citations = 0
        confidence: float | None = None
        try:
            payload = service.decision(symbol, horizon)
            blocked = "insufficient_evidence" in (
                payload.get("score", {}).get("blockedBy", [])
            )
            citations = len(payload.get("citations", []))
            if captured:
                confidence = captured[-1].evidence_confidence
            elif payload.get("status") == "unavailable":
                error = str(
                    payload.get("reason") or "decision unavailable"
                )
        except Exception as failure:  # a measuring instrument records, it does not crash
            error = f"{type(failure).__name__}: {failure}"
        readings.append(
            {
                "symbol": symbol,
                "evidence_confidence": confidence,
                "blocked": blocked,
                "citations": citations,
                "error": error,
            }
        )
        marker = (
            "unmeasured" if confidence is None else f"{confidence:.3f}"
        )
        print(f"[{index}/{len(symbols)}] {symbol}: {marker}"
              + (f" ({error})" if error else ""))
    return readings


def _render(readings: list[dict], stats: dict, horizon: str) -> str:
    now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"# evidence_confidence measurement — {now} (horizon={horizon})",
        "",
        f"- symbols: {stats['total']}, measured: {stats['measured']},"
        f" unmeasured: {stats['unmeasured']}",
        f"- gate {GATE}: clears {stats['clears_gate']},"
        f" fires {stats['fires_gate']}, zero-evidence {stats['zero_evidence']}",
        f"- min {stats['minimum']}, median {stats['median']},"
        f" mean {stats['mean']}, max {stats['maximum']}",
        "",
        "| symbol | evidence_confidence | citations | insufficient_evidence | note |",
        "| --- | --- | --- | --- | --- |",
    ]
    def sort_key(row: dict):
        value = row["evidence_confidence"]
        return (value is None, -(value or 0.0), row["symbol"])
    for row in sorted(readings, key=sort_key):
        value = row["evidence_confidence"]
        lines.append(
            f"| {row['symbol']} |"
            f" {'—' if value is None else f'{value:.4f}'} |"
            f" {row['citations']} |"
            f" {'yes' if row['blocked'] else 'no'} |"
            f" {row['error'] or ''} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", default="short",
                        choices=("short", "swing", "long"))
    parser.add_argument("--limit", type=int, default=None,
                        help="measure only the first N symbols (smoke run)")
    parser.add_argument("--out", default=None,
                        help="also write the markdown report to this path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    _warn_if_outside_market_hours(datetime.now(tz=timezone.utc))
    _load_runtime_environment()
    readings = _measure(args.horizon, args.limit)
    stats = summarize(readings)
    report = _render(readings, stats, args.horizon)
    print()
    print(report)
    print("json:", json.dumps(stats))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
