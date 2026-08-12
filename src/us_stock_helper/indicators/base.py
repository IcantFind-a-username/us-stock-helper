"""Shared, serializable indicator data structures."""

from dataclasses import dataclass, field
from math import isfinite
from typing import Dict, Optional, Sequence, Tuple, Union


Number = Union[int, float]
SeriesValue = Optional[Union[float, int, bool, str]]


@dataclass(frozen=True)
class SourceReference:
    """A public source describing the behavior implemented by an indicator."""

    title: str
    url: str
    note: str = ""


@dataclass(frozen=True)
class IndicatorMetadata:
    """Provenance and identity for an indicator implementation."""

    key: str
    display_name: str
    description: str
    implementation_kind: str
    sources: Tuple[SourceReference, ...] = ()
    proprietary_equivalent: bool = False


@dataclass(frozen=True)
class CandleSeries:
    """Validated OHLCV candles in chronological order."""

    close: Sequence[Number]
    high: Sequence[Number]
    low: Sequence[Number]
    volume: Sequence[Number]

    def __post_init__(self) -> None:
        lengths = {len(self.close), len(self.high), len(self.low), len(self.volume)}
        if len(lengths) != 1:
            raise ValueError("OHLCV series must have identical lengths")

        for name, values in (
            ("close", self.close),
            ("high", self.high),
            ("low", self.low),
            ("volume", self.volume),
        ):
            for value in values:
                if not isfinite(float(value)):
                    raise ValueError("%s contains a non-finite value" % name)

        for index, (high, low) in enumerate(zip(self.high, self.low)):
            if float(high) < float(low):
                raise ValueError("high is below low at index %d" % index)

    def __len__(self) -> int:
        return len(self.close)


@dataclass(frozen=True)
class Signal:
    """A point-in-time signal produced without future candle data."""

    index: int
    kind: str
    direction: str
    confidence: float
    reason: str
    evidence: Dict[str, SeriesValue] = field(default_factory=dict)


@dataclass(frozen=True)
class IndicatorResult:
    """Indicator output aligned one-to-one with the input candles."""

    metadata: IndicatorMetadata
    values: Dict[str, Tuple[SeriesValue, ...]]
    signals: Tuple[Signal, ...] = ()

    def __post_init__(self) -> None:
        lengths = {len(values) for values in self.values.values()}
        if len(lengths) > 1:
            raise ValueError("all indicator output series must have identical lengths")

