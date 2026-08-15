from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.models import OHLCVBar
from us_stock_helper_core.relative_strength import (
    SECTOR_RS_VERSION,
    CorrelationRegimeResult,
    RelativeStrengthRanking,
    SectorRelativeStrength,
    correlation_regime,
    relative_strength_ranking,
)


BASE_DAY = datetime(2026, 7, 20, 21, tzinfo=UTC)
ONE_DAY = timedelta(days=1)


def day(index: int) -> datetime:
    return BASE_DAY + ONE_DAY * index


def daily_bar(
    symbol: str,
    index: int,
    close: float,
    *,
    available_at: datetime | None = None,
) -> OHLCVBar:
    closed_at = day(index)
    return OHLCVBar(
        symbol=symbol,
        interval="day",
        opened_at=closed_at - ONE_DAY,
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1_000.0,
    )


def series(symbol: str, closes: list[float]) -> tuple[OHLCVBar, ...]:
    return tuple(daily_bar(symbol, index, close) for index, close in enumerate(closes))


# --- Hand-computed relative-strength fixture (period=3 EMA anchor) -------
#
# RS per lookback L = latest_close / EMA(L, seeded by SMA) - 1.
# EMA seed (index L-1) = SMA of the first L values; each later bar updates
# with multiplier 2/(L+1). "Excess return" = sector metric - benchmark metric.
#
# Benchmark closes: 100, 102, 101, 105
#   EMA(3) seed (idx2) = (100+102+101)/3 = 101.0
#   EMA(3) at idx3 = (105-101)*0.5+101 = 103.0
#   benchmark_return = 105/103 - 1 = 0.019417475728155338
#
# Sector X closes: 50, 49, 52, 60
#   EMA(3) seed (idx2) = (50+49+52)/3 = 50.333333333333336
#   EMA(3) at idx3 = (60-50.333333333333336)*0.5+50.333333333333336 = 55.16666666666667
#   X_return = 60/55.16666666666667 - 1 = 0.08761329305135934
#   excess_X = 0.08761329305135934 - 0.019417475728155338 = 0.06819581732320401
#
# Sector Y closes: 50, 50, 50, 50 (flat -> EMA always 50, return exactly 0)
#   excess_Y = 0.0 - 0.019417475728155338 = -0.019417475728155338
_BENCHMARK = series("SPY", [100, 102, 101, 105])
_SECTOR_X = series("XLK", [50, 49, 52, 60])
_SECTOR_Y = series("XLU", [50, 50, 50, 50])
_SECTOR_Z_SHORT = series("XLF", [50, 55])  # only 2 bars, < period 3


class RelativeStrengthRankingTests(unittest.TestCase):
    def test_hand_computed_excess_return_and_rank(self) -> None:
        cutoff = day(3)
        universe = {"XLK": _SECTOR_X, "XLU": _SECTOR_Y}

        result = relative_strength_ranking(
            universe, _BENCHMARK, cutoff, lookbacks=(3,), minimum_universe=2
        )

        self.assertIsInstance(result, RelativeStrengthRanking)
        self.assertEqual(result.benchmark_symbol, "SPY")
        self.assertEqual(result.universe_size, 2)
        self.assertEqual(result.lookbacks, (3,))
        self.assertEqual(len(result.results), 2)

        by_symbol = {row.symbol: row for row in result.results}
        xlk = by_symbol["XLK"]
        xlu = by_symbol["XLU"]

        self.assertIsInstance(xlk, SectorRelativeStrength)
        self.assertEqual(xlk.quality_status, "live")
        assert xlk.sector_return is not None and xlk.benchmark_return is not None
        self.assertAlmostEqual(xlk.benchmark_return, 0.019417475728155338, places=9)
        self.assertAlmostEqual(xlk.sector_return, 0.08761329305135934, places=9)
        self.assertAlmostEqual(xlk.excess_return, 0.06819581732320401, places=9)
        self.assertEqual(xlk.rank, 1)
        self.assertEqual(xlk.method_version, SECTOR_RS_VERSION)

        self.assertEqual(xlu.quality_status, "live")
        assert xlu.excess_return is not None
        self.assertAlmostEqual(xlu.excess_return, -0.019417475728155338, places=9)
        self.assertEqual(xlu.rank, 2)

    def test_insufficient_warm_up_is_typed_unavailable_without_blocking_others(
        self,
    ) -> None:
        cutoff = day(3)
        universe = {"XLK": _SECTOR_X, "XLU": _SECTOR_Y, "XLF": _SECTOR_Z_SHORT}

        result = relative_strength_ranking(
            universe, _BENCHMARK, cutoff, lookbacks=(3,), minimum_universe=2
        )

        by_symbol = {row.symbol: row for row in result.results}
        xlf = by_symbol["XLF"]
        self.assertEqual(xlf.quality_status, "unavailable")
        self.assertIsNone(xlf.sector_return)
        self.assertIsNone(xlf.benchmark_return)
        self.assertIsNone(xlf.excess_return)
        self.assertIsNone(xlf.rank)
        self.assertIn("warm-up", xlf.missing_reason or "")

        # XLK and XLU still have two eligible peers (each other), so ranking
        # proceeds without XLF.
        self.assertEqual(by_symbol["XLK"].quality_status, "live")
        self.assertEqual(by_symbol["XLK"].rank, 1)
        self.assertEqual(by_symbol["XLU"].quality_status, "live")
        self.assertEqual(by_symbol["XLU"].rank, 2)

    def test_sub_minimum_universe_is_typed_unavailable_not_zero(self) -> None:
        cutoff = day(3)
        universe = {"XLK": _SECTOR_X}

        result = relative_strength_ranking(
            universe, _BENCHMARK, cutoff, lookbacks=(3,), minimum_universe=2
        )

        self.assertEqual(len(result.results), 1)
        row = result.results[0]
        self.assertEqual(row.quality_status, "unavailable")
        self.assertIsNone(row.sector_return)
        self.assertIsNone(row.excess_return)
        self.assertIsNone(row.rank)
        self.assertIn("universe", row.missing_reason or "")

    def test_a_bar_added_after_the_cutoff_cannot_change_yesterdays_ranking(
        self,
    ) -> None:
        cutoff = day(3)
        universe = {"XLK": _SECTOR_X, "XLU": _SECTOR_Y}
        baseline = relative_strength_ranking(
            universe, _BENCHMARK, cutoff, lookbacks=(3,), minimum_universe=2
        )

        future_universe = {
            "XLK": _SECTOR_X + (daily_bar("XLK", 4, 999.0),),
            "XLU": _SECTOR_Y,
        }
        result = relative_strength_ranking(
            future_universe, _BENCHMARK, cutoff, lookbacks=(3,), minimum_universe=2
        )

        self.assertEqual(result.results, baseline.results)


# --- Hand-computed correlation-regime fixtures (window=3 -> 3 daily returns)
#
# P returns: +10%, -10%, +10%   (closes 100 -> 110 -> 99 -> 108.9)
# Q returns: identical to P     (closes 50 -> 55 -> 49.5 -> 54.45)     corr(P,Q)=+1.0
# R returns: exact negation of P (closes 50 -> 45 -> 49.5 -> 44.55)    corr(P,R)=-1.0, corr(Q,R)=-1.0
# average pairwise correlation = (1.0 - 1.0 - 1.0) / 3 = -0.3333... -> below the
# risk_on_threshold (0.3) -> "risk_on" (differentiated / uncorrelated market)
_P = series("XLK", [100, 110, 99, 108.9])
_Q = series("XLU", [50, 55, 49.5, 54.45])
_R = series("XLE", [50, 45, 49.5, 44.55])

# S1, S2, S3 all share P's exact return pattern (+10%,-10%,+10%) at different
# price levels -> every pairwise correlation is +1.0 -> average = 1.0 ->
# at/above the risk_off_threshold (0.6) -> "risk_off" (everything moves together)
_S1 = series("XLK", [100, 110, 99, 108.9])
_S2 = series("XLU", [60, 66, 59.4, 65.34])
_S3 = series("XLE", [25, 27.5, 24.75, 27.225])

_FLAT = series("XLF", [50, 50, 50, 50])


class CorrelationRegimeTests(unittest.TestCase):
    def test_hand_computed_risk_on_regime(self) -> None:
        cutoff = day(3)
        universe = {"XLK": _P, "XLU": _Q, "XLE": _R}

        result = correlation_regime(universe, cutoff, window=3)

        self.assertIsInstance(result, CorrelationRegimeResult)
        self.assertEqual(result.quality_status, "live")
        self.assertEqual(result.window, 3)
        self.assertEqual(result.universe_size, 3)
        assert result.average_pairwise_correlation is not None
        self.assertAlmostEqual(
            result.average_pairwise_correlation, -1.0 / 3.0, places=9
        )
        self.assertEqual(result.regime, "risk_on")
        self.assertEqual(result.method_version, SECTOR_RS_VERSION)

    def test_hand_computed_risk_off_regime(self) -> None:
        cutoff = day(3)
        universe = {"XLK": _S1, "XLU": _S2, "XLE": _S3}

        result = correlation_regime(universe, cutoff, window=3)

        self.assertEqual(result.quality_status, "live")
        assert result.average_pairwise_correlation is not None
        self.assertAlmostEqual(result.average_pairwise_correlation, 1.0, places=9)
        self.assertEqual(result.regime, "risk_off")

    def test_flat_series_is_excluded_and_can_trip_typed_unavailable(self) -> None:
        cutoff = day(3)
        # Only two non-flat series remain eligible once XLF (flat) is excluded,
        # which is below the default minimum_universe of three.
        universe = {"XLK": _P, "XLU": _Q, "XLF": _FLAT}

        result = correlation_regime(universe, cutoff, window=3)

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.average_pairwise_correlation)
        self.assertIsNone(result.regime)
        self.assertNotIn("XLF", result.eligible_symbols)
        self.assertIn("eligible", result.missing_reason or "")

    def test_insufficient_window_is_typed_unavailable(self) -> None:
        cutoff = day(1)
        short_universe = {
            "XLK": _P[:2],
            "XLU": _Q[:2],
            "XLE": _R[:2],
        }

        result = correlation_regime(short_universe, cutoff, window=3)

        self.assertEqual(result.quality_status, "unavailable")
        self.assertEqual(result.eligible_symbols, ())

    def test_sub_minimum_universe_is_typed_unavailable_not_zero(self) -> None:
        cutoff = day(3)
        universe = {"XLK": _P, "XLU": _Q}

        result = correlation_regime(universe, cutoff, window=3, minimum_universe=3)

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.average_pairwise_correlation)
        self.assertEqual(result.universe_size, 2)

    def test_a_bar_added_after_the_cutoff_cannot_change_yesterdays_regime(
        self,
    ) -> None:
        cutoff = day(3)
        universe = {"XLK": _P, "XLU": _Q, "XLE": _R}
        baseline = correlation_regime(universe, cutoff, window=3)

        future_universe = {
            "XLK": _P + (daily_bar("XLK", 4, 1.0),),
            "XLU": _Q,
            "XLE": _R,
        }
        result = correlation_regime(future_universe, cutoff, window=3)

        self.assertEqual(
            result.average_pairwise_correlation, baseline.average_pairwise_correlation
        )
        self.assertEqual(result.regime, baseline.regime)


if __name__ == "__main__":
    unittest.main()
