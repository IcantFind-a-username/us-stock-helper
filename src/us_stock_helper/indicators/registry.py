"""Small registry that lets the application load indicators by stable key."""

from typing import Callable, Dict, Tuple

from .base import CandleSeries, IndicatorResult


IndicatorFunction = Callable[..., IndicatorResult]
_INDICATORS: Dict[str, IndicatorFunction] = {}


def register_indicator(key: str) -> Callable[[IndicatorFunction], IndicatorFunction]:
    def decorator(function: IndicatorFunction) -> IndicatorFunction:
        if key in _INDICATORS:
            raise ValueError("indicator key already registered: %s" % key)
        _INDICATORS[key] = function
        return function

    return decorator


def get_indicator(key: str) -> IndicatorFunction:
    try:
        return _INDICATORS[key]
    except KeyError as exc:
        raise KeyError("unknown indicator: %s" % key) from exc


def list_indicators() -> Tuple[str, ...]:
    return tuple(sorted(_INDICATORS))

