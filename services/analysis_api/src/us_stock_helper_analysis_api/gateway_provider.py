"""Read completed candles from the market gateway's candles contract.

This supplies candles only. Evidence comes from `evidence_provider`, because
the two systems fail in different ways and a single object answering for both
would have to pick one story to tell about a failure.

The gateway is the only candle source, and every failure to reach it has to
stay distinguishable from the market genuinely having produced nothing: an
empty series is a decision the app can trust, a silent one is not. So the
transport, the contract and the point-in-time fields all fail loudly here.

Read-only by construction: this speaks HTTP to our own gateway, holds no
credential, and has no path to a broker.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from us_stock_helper_core import OHLCVBar


CANDLES_PATH = "/candles"
_INTERVALS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "60m": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(days=7),
}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
# One response of a thousand candles is well under a megabyte; the ceiling
# exists so a peer that never stops writing cannot exhaust this process.
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class MarketGatewayUnavailable(RuntimeError):
    """The gateway did not supply candles that can be trusted at a cutoff."""


@dataclass(frozen=True, slots=True)
class MarketGatewayProvider:
    base_url: str
    fetch: Callable[[str], bytes]
    count: int = 200

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        duration = _INTERVALS.get(interval)
        if duration is None:
            raise MarketGatewayUnavailable(
                "the gateway does not serve this candle interval"
            )
        payload = self._candles(symbol, interval)
        if payload.get("symbol") != symbol or payload.get("interval") != interval:
            raise MarketGatewayUnavailable(
                "the gateway answered for a different symbol or interval"
            )
        cutoff = _timestamp(payload, "asOf")
        candles = payload.get("items")
        if not isinstance(candles, list):
            raise MarketGatewayUnavailable(
                "the gateway response carries no candle series"
            )
        bars = tuple(
            _bar(symbol, interval, duration, item, cutoff) for item in candles
        )
        # The chain reads the last bar as the current price, so a series that
        # arrives newest-first would price the decision off an old close —
        # plausible, wrong, and with nothing to notice.
        for index in range(1, len(bars)):
            if bars[index].closed_at <= bars[index - 1].closed_at:
                raise MarketGatewayUnavailable(
                    "the gateway candle series is out of order"
                )
        return bars

    def _candles(self, symbol: str, interval: str) -> dict[str, Any]:
        query = urlencode(
            {"symbol": symbol, "interval": interval, "count": self.count}
        )
        payload = self._read_json(f"{self.base_url}{CANDLES_PATH}?{query}")
        if payload.get("schemaVersion") != "1":
            raise MarketGatewayUnavailable(
                "the market gateway returned an unsupported candle contract"
            )
        if payload.get("source") != "moomoo":
            raise MarketGatewayUnavailable(
                "the market gateway returned an unknown candle source"
            )
        if payload.get("session") != "healthy":
            failure = payload.get("error")
            code = failure.get("code") if isinstance(failure, dict) else None
            raise MarketGatewayUnavailable(
                f"the market gateway reported {code or 'an error'}"
            )
        return payload

    def _read_json(self, url: str) -> dict[str, Any]:
        try:
            body = self.fetch(url)
        except OSError as error:
            raise MarketGatewayUnavailable(
                "the market gateway could not be reached"
            ) from error
        try:
            payload = json.loads(body)
        except ValueError as error:
            raise MarketGatewayUnavailable(
                "the market gateway returned a body that is not JSON"
            ) from error
        if not isinstance(payload, dict):
            raise MarketGatewayUnavailable(
                "the market gateway returned a body that is not an object"
            )
        return payload


def provider_from_environment(
    environment: Mapping[str, str] | None = None,
) -> MarketGatewayProvider:
    env = os.environ if environment is None else environment
    base_url = _loopback_origin(
        env.get("ANALYSIS_API_GATEWAY_URL", "http://127.0.0.1:8765")
    )
    try:
        count = int(env.get("ANALYSIS_API_CANDLE_COUNT", "200"))
    except ValueError as exc:
        raise ValueError("ANALYSIS_API_CANDLE_COUNT must be numeric") from exc
    if not 1 <= count <= 1000:
        raise ValueError("ANALYSIS_API_CANDLE_COUNT must be between 1 and 1000")
    try:
        timeout = float(env.get("ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS", "10"))
    except ValueError as exc:
        raise ValueError(
            "ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS must be numeric"
        ) from exc
    if not 0 < timeout <= 60:
        raise ValueError(
            "ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS must be between 0 and 60"
        )
    return MarketGatewayProvider(
        base_url=base_url,
        fetch=_http_reader(timeout),
        count=count,
    )


def _loopback_origin(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "ANALYSIS_API_GATEWAY_URL must be a credential-free HTTP(S) origin"
        )
    if parsed.hostname not in _LOOPBACK_HOSTS:
        # This service holds no gateway token by design, and a LAN gateway
        # demands one. Pointing it across the network would either fail every
        # request or require a credential this boundary must not carry.
        raise ValueError(
            "ANALYSIS_API_GATEWAY_URL must address a gateway on this host"
        )
    return normalized


def _http_reader(timeout: float) -> Callable[[str], bytes]:
    def read(url: str) -> bytes:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read(_MAX_RESPONSE_BYTES)

    return read


def _bar(
    symbol: str,
    interval: str,
    duration: timedelta,
    item: Any,
    cutoff: datetime,
) -> OHLCVBar:
    if not isinstance(item, dict):
        raise MarketGatewayUnavailable("a completed candle is malformed")
    if item.get("complete") is not True:
        raise MarketGatewayUnavailable("a candle in the completed series is open")
    closed_at = _timestamp(item, "timestamp")
    # availableAt is when the exchange published the bar and is the earliest
    # instant the chain may claim to have known it; receivedAt is when the
    # gateway itself held it. Reading one in place of the other, or falling
    # back to the candle's own close time, moves that instant earlier than it
    # truly was and lets a backtest see the future.
    available_at = _timestamp(item, "availableAt")
    received_at = _timestamp(item, "receivedAt")
    if received_at < available_at:
        raise MarketGatewayUnavailable("a candle was received before it was published")
    if available_at > cutoff or received_at > cutoff:
        raise MarketGatewayUnavailable("a candle is later than the decision cutoff")
    prices = {name: _number(item, name) for name in ("open", "high", "low", "close")}
    volume = _number(item, "volume")
    try:
        return OHLCVBar(
            symbol=symbol,
            interval=interval,
            opened_at=closed_at - duration,
            closed_at=closed_at,
            available_at=available_at,
            volume=volume,
            **prices,
        )
    except (TypeError, ValueError) as error:
        raise MarketGatewayUnavailable(
            "a completed candle failed the bar model's own checks"
        ) from error


def _timestamp(item: Mapping[str, Any], key: str) -> datetime:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MarketGatewayUnavailable(f"{key} is missing from the gateway response")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise MarketGatewayUnavailable(f"{key} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketGatewayUnavailable(f"{key} is missing timezone information")
    return parsed.astimezone(timezone.utc)


def _number(item: Mapping[str, Any], key: str) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketGatewayUnavailable(f"{key} is not a number in the gateway response")
    return float(value)
