#!/usr/bin/env python3
"""Compute the macro and fundamentals factors against the live public sources.

This exists because a green unit suite proves the arithmetic, not the wiring.
Every adapter here is exercised through the same ``UrllibHttpsTransport`` a
deployment uses, against the real endpoints, with no fixtures and no fakes: if
SEC renames a tag, Treasury moves the CSV, or the host allowlist is wrong, this
script fails and the unit tests do not.

    US_STOCK_HELPER_CONTACT_EMAIL=you@example.com \\
        python3 services/information_layer/scripts/smoke_real_factors.py AAPL

Exit status is 0 only if every factor either produced a number or produced a
reason this script recognises as legitimate. A silent 0.0 anywhere is a
failure by definition.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "services/information_layer"))

from information_layer.cik_registry import CikTickerRegistry  # noqa: E402
from information_layer.factors import (  # noqa: E402
    FactorReading,
    PublicFactorProvider,
    SecXbrlFundamentalsFactor,
    TreasuryYieldCurveMacroFactor,
)
from information_layer.feeds import (  # noqa: E402
    HttpRequest,
    UrllibHttpsTransport,
    contact_email_from_environment,
    user_agent_for,
)


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_cik_registry(transport: UrllibHttpsTransport, user_agent: str) -> CikTickerRegistry:
    response = transport.request(
        HttpRequest(
            url=COMPANY_TICKERS_URL,
            allowed_hosts=("www.sec.gov",),
            headers=(("User-Agent", user_agent), ("Accept", "application/json")),
            timeout_seconds=30.0,
            max_response_bytes=8_000_000,
        )
    )
    if response.status_code != 200:
        raise SystemExit(
            f"SEC company ticker registry answered {response.status_code}"
        )
    return CikTickerRegistry.from_sec_payload(response.body)


def describe(reading: FactorReading) -> dict[str, object]:
    return {
        "factor": reading.factor,
        "methodVersion": reading.method_version,
        "value": reading.value,
        "unavailableReason": (
            reading.unavailable_reason.value
            if reading.unavailable_reason is not None
            else None
        ),
        "availableAt": (
            reading.available_at.isoformat() if reading.available_at else None
        ),
        "lagSeconds": reading.lag_seconds,
        "detail": reading.detail,
        "inputs": [
            {
                "name": item.name,
                "value": item.value,
                "observedAt": item.observed_at.isoformat(),
                "availableAt": item.available_at.isoformat(),
            }
            for item in reading.inputs
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?", default="AAPL")
    arguments = parser.parse_args()

    contact = contact_email_from_environment()
    user_agent = user_agent_for(contact)
    transport = UrllibHttpsTransport()
    as_of = datetime.now(timezone.utc)

    provider = PublicFactorProvider(
        fundamentals=SecXbrlFundamentalsFactor(
            transport=transport, user_agent=user_agent
        ),
        macro=TreasuryYieldCurveMacroFactor(
            transport=transport, user_agent=user_agent
        ),
        cik_registry=fetch_cik_registry(transport, user_agent),
    )
    snapshot = provider.snapshot(symbol=arguments.symbol, as_of=as_of)

    report = {
        "symbol": snapshot.symbol,
        "asOf": snapshot.as_of.isoformat(),
        "readings": [describe(item) for item in snapshot.readings()],
    }
    print(json.dumps(report, indent=2))

    failures: list[str] = []
    for reading in snapshot.readings():
        if reading.value is not None:
            # The whole point of the exercise: a number that came off the wire.
            continue
        reason = reading.unavailable_reason
        assert reason is not None
        if reason.value in {"source_unreachable", "source_malformed"}:
            failures.append(f"{reading.factor}: {reason.value} — {reading.detail}")
    if snapshot.macro.value is None and snapshot.fundamentals.value is None:
        failures.append(
            "neither factor this script exists to prove produced a number"
        )
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
