from __future__ import annotations

from datetime import UTC, datetime
import unittest

from us_stock_helper_core.breadth import PercentAboveMAResult
from us_stock_helper_core.models import Direction
from us_stock_helper_core.patterns import MagicNineSignal, TDSetupResult
from us_stock_helper_core.plain_language import (
    BANNED_VERBS,
    PLAIN_LANGUAGE_VERSION,
    BREADTH_READINGS,
    RVOL_READINGS,
    SECTOR_RS_READINGS,
    VOLATILITY_READINGS,
    PlainReading,
    breadth_reading,
    classify_breadth,
    classify_magic_nine_last_completed,
    classify_magic_nine_progress,
    classify_rvol,
    classify_sector_rs,
    classify_volatility,
    magic_nine_last_completed_reading,
    magic_nine_progress_reading,
    rvol_reading,
    sector_rs_reading,
    volatility_reading,
)
from us_stock_helper_core.relative_strength import SectorRelativeStrength
from us_stock_helper_core.rvol import RelativeVolumeResult
from us_stock_helper_core.volatility import VolatilityEstimate


NOW = datetime(2026, 8, 15, 16, 0, tzinfo=UTC)


def _rvol(
    *,
    quality_status: str = "live",
    ratio: float | None = None,
    missing_reason: str | None = None,
) -> RelativeVolumeResult:
    if quality_status == "live":
        assert ratio is not None
        return RelativeVolumeResult(
            symbol="NVDA",
            interval="5m",
            as_of=NOW,
            session="2026-08-15",
            bucket="09:35",
            buckets_elapsed=5,
            minimum_buckets_elapsed=2,
            lookback_sessions=20,
            sessions_used=20,
            current_cumulative_volume=ratio * 1_000_000.0,
            historical_mean_cumulative_volume=1_000_000.0,
            ratio=ratio,
            quality_status="live",
            missing_reason=None,
        )
    return RelativeVolumeResult(
        symbol="NVDA",
        interval="5m",
        as_of=NOW,
        session="2026-08-15",
        bucket="09:35",
        buckets_elapsed=1,
        minimum_buckets_elapsed=2,
        lookback_sessions=20,
        sessions_used=0,
        current_cumulative_volume=None,
        historical_mean_cumulative_volume=None,
        ratio=None,
        quality_status="unavailable",
        missing_reason=missing_reason,
    )


def _volatility(
    *,
    estimator: str = "close_to_close",
    quality_status: str = "live",
    value: float | None = None,
    missing_reason: str | None = None,
) -> VolatilityEstimate:
    method_version = (
        "close-to-close-realized-v1" if estimator == "close_to_close" else "range-vol-v1"
    )
    if quality_status == "live":
        assert value is not None
        return VolatilityEstimate(
            value=value,
            sample_size=60,
            interval="day",
            as_of=NOW,
            quality_status="live",
            missing_reason=None,
            estimator=estimator,
            method_version=method_version,
        )
    return VolatilityEstimate(
        value=None,
        sample_size=1,
        interval="day",
        as_of=NOW,
        quality_status="unavailable",
        missing_reason=missing_reason,
        estimator=estimator,
        method_version=method_version,
    )


def _breadth(
    *, quality_status: str = "live", percent_above: float | None = None
) -> PercentAboveMAResult:
    if quality_status == "live":
        assert percent_above is not None
        return PercentAboveMAResult(
            as_of=NOW,
            universe_size=10,
            minimum_universe=5,
            period=50,
            eligible_symbols=10,
            percent_above=percent_above,
            quality_status="live",
            missing_reason=None,
        )
    return PercentAboveMAResult(
        as_of=NOW,
        universe_size=2,
        minimum_universe=5,
        period=50,
        eligible_symbols=2,
        percent_above=None,
        quality_status="unavailable",
        missing_reason="insufficient eligible symbols: 2 of 5 have 50+ bars (universe 2)",
    )


def _sector_rs(
    *, quality_status: str = "live", excess_return: float | None = None
) -> SectorRelativeStrength:
    if quality_status == "live":
        assert excess_return is not None
        sector_return = 0.05
        benchmark_return = sector_return - excess_return
        return SectorRelativeStrength(
            symbol="XLK",
            lookback=21,
            sector_return=sector_return,
            benchmark_return=benchmark_return,
            excess_return=sector_return - benchmark_return,
            rank=1,
            quality_status="live",
            missing_reason=None,
        )
    return SectorRelativeStrength(
        symbol="XLK",
        lookback=21,
        sector_return=None,
        benchmark_return=None,
        excess_return=None,
        rank=None,
        quality_status="unavailable",
        missing_reason="insufficient warm-up history for the 21-bar EMA anchor",
    )


def _signal(
    direction: Direction, count: int, *, completed: bool, perfected: bool | None = None
) -> MagicNineSignal:
    return MagicNineSignal(
        direction=direction,
        count=count,
        completed=completed,
        confirmed_at_index=count,
        perfected=perfected,
    )


def _setup(latest: MagicNineSignal | None, signals: tuple[MagicNineSignal, ...] = ()) -> TDSetupResult:
    return TDSetupResult(
        bullish_counts=(0,),
        bearish_counts=(0,),
        signals=signals,
        latest=latest,
    )


class VersionTests(unittest.TestCase):
    def test_version_is_stamped(self) -> None:
        self.assertEqual(PLAIN_LANGUAGE_VERSION, "plain-language-v1")


class BannedVerbGuardTests(unittest.TestCase):
    def test_every_banned_verb_is_present_in_the_guard_list(self) -> None:
        self.assertEqual(
            set(BANNED_VERBS), {"买入", "卖出", "加仓", "抄底", "梭哈"}
        )

    def test_constructing_a_reading_with_a_banned_verb_in_the_headline_raises(self) -> None:
        for verb in BANNED_VERBS:
            with self.assertRaises(ValueError):
                PlainReading(headline=f"现在应该{verb}。", explanation="解释。")

    def test_constructing_a_reading_with_a_banned_verb_in_the_explanation_raises(self) -> None:
        with self.assertRaises(ValueError):
            PlainReading(headline="标题。", explanation="展开解释里建议梭哈。")

    def test_no_shipped_reading_contains_a_banned_verb(self) -> None:
        all_readings: list[PlainReading] = [
            *RVOL_READINGS.values(),
            *VOLATILITY_READINGS.values(),
            *BREADTH_READINGS.values(),
            *SECTOR_RS_READINGS.values(),
        ]
        for reading in all_readings:
            for verb in BANNED_VERBS:
                self.assertNotIn(verb, reading.headline)
                self.assertNotIn(verb, reading.explanation)

    def test_no_magic_nine_reading_contains_a_banned_verb(self) -> None:
        # Magic Nine progress headlines are rendered (count interpolated), so
        # exercise the render path rather than a static dict.
        for direction in (Direction.BULLISH, Direction.BEARISH):
            for count in range(1, 9):
                setup = _setup(_signal(direction, count, completed=False))
                reading = magic_nine_progress_reading(setup)
                for verb in BANNED_VERBS:
                    self.assertNotIn(verb, reading.headline)
                    self.assertNotIn(verb, reading.explanation)
        for perfected in (True, False, None):
            for direction in (Direction.BULLISH, Direction.BEARISH):
                last = _signal(direction, 9, completed=True, perfected=perfected)
                reading = magic_nine_last_completed_reading(last)
                for verb in BANNED_VERBS:
                    self.assertNotIn(verb, reading.headline)
                    self.assertNotIn(verb, reading.explanation)


class RvolCompletenessTests(unittest.TestCase):
    """Every reachable rvol.py state has copy; classify never guesses."""

    def test_ratio_buckets_have_copy(self) -> None:
        cases = {
            "rvol-light": 0.5,
            "rvol-normal": 1.0,
            "rvol-moderate-high": 1.6,
            "rvol-heavy": 2.5,
        }
        for expected_state, ratio in cases.items():
            result = _rvol(ratio=ratio)
            state = classify_rvol(result)
            self.assertEqual(state, expected_state)
            self.assertIn(state, RVOL_READINGS)
            reading = rvol_reading(result)
            self.assertTrue(reading.headline)
            self.assertTrue(reading.explanation)

    def test_bucket_boundaries(self) -> None:
        self.assertEqual(classify_rvol(_rvol(ratio=0.699999)), "rvol-light")
        self.assertEqual(classify_rvol(_rvol(ratio=0.7)), "rvol-normal")
        self.assertEqual(classify_rvol(_rvol(ratio=1.299999)), "rvol-normal")
        self.assertEqual(classify_rvol(_rvol(ratio=1.3)), "rvol-moderate-high")
        self.assertEqual(classify_rvol(_rvol(ratio=1.999999)), "rvol-moderate-high")
        self.assertEqual(classify_rvol(_rvol(ratio=2.0)), "rvol-heavy")

    def test_every_unavailable_reason_rvol_actually_emits_has_copy(self) -> None:
        reasons = {
            "rvol-unavailable-no-data": "no completed bars are knowable as of the cutoff",
            "rvol-unavailable-early-session": "early session: 1 of 2 minimum buckets elapsed",
            "rvol-unavailable-insufficient-history": (
                "insufficient history: 5 of 20 prior sessions have this time-of-day bucket"
            ),
            "rvol-unavailable-zero-baseline": "historical baseline has no volume at this bucket",
        }
        for expected_state, reason in reasons.items():
            result = _rvol(quality_status="unavailable", missing_reason=reason)
            state = classify_rvol(result)
            self.assertEqual(state, expected_state)
            reading = rvol_reading(result)
            self.assertTrue(reading.headline)
            self.assertTrue(reading.explanation)

    def test_an_unrecognized_unavailable_reason_raises_rather_than_falling_back(self) -> None:
        result = _rvol(
            quality_status="unavailable",
            missing_reason="a brand new reason nobody wrote copy for",
        )
        with self.assertRaises(ValueError):
            classify_rvol(result)


class VolatilityCompletenessTests(unittest.TestCase):
    def test_every_estimator_and_regime_bucket_has_copy(self) -> None:
        regimes = {
            "low": 0.10,
            "normal": 0.20,
            "elevated": 0.35,
            "high": 0.60,
        }
        for estimator in ("close_to_close", "parkinson", "garman_klass"):
            for bucket, value in regimes.items():
                result = _volatility(estimator=estimator, value=value)
                state = classify_volatility(result)
                self.assertEqual(state, f"volatility-{estimator}-{bucket}")
                self.assertIn(state, VOLATILITY_READINGS)
                reading = volatility_reading(result)
                self.assertTrue(reading.headline)
                self.assertTrue(reading.explanation)

    def test_every_estimators_unavailable_reasons_have_copy(self) -> None:
        for estimator in ("close_to_close", "parkinson", "garman_klass"):
            insufficient = _volatility(
                estimator=estimator,
                quality_status="unavailable",
                missing_reason="insufficient sample: 3 of 20 returns",
            )
            self.assertEqual(
                classify_volatility(insufficient),
                f"volatility-{estimator}-unavailable-insufficient-sample",
            )
            flat = _volatility(
                estimator=estimator,
                quality_status="unavailable",
                missing_reason="no price variation in the observed window",
            )
            self.assertEqual(
                classify_volatility(flat),
                f"volatility-{estimator}-unavailable-flat",
            )

    def test_an_unrecognized_unavailable_reason_raises(self) -> None:
        result = _volatility(
            quality_status="unavailable", missing_reason="a brand new reason"
        )
        with self.assertRaises(ValueError):
            classify_volatility(result)


class BreadthCompletenessTests(unittest.TestCase):
    def test_strong_weak_mixed_and_unavailable_all_have_copy(self) -> None:
        cases = {
            "breadth-strong": 62.0,
            "breadth-weak": 30.0,
            "breadth-mixed": 50.0,
        }
        for expected_state, percent in cases.items():
            result = _breadth(percent_above=percent)
            state = classify_breadth(result)
            self.assertEqual(state, expected_state)
            reading = breadth_reading(result)
            self.assertTrue(reading.headline)
            self.assertTrue(reading.explanation)

        unavailable = _breadth(quality_status="unavailable")
        self.assertEqual(classify_breadth(unavailable), "breadth-unavailable")
        self.assertIn("breadth-unavailable", BREADTH_READINGS)

    def test_bucket_boundaries(self) -> None:
        self.assertEqual(classify_breadth(_breadth(percent_above=55.0)), "breadth-strong")
        self.assertEqual(classify_breadth(_breadth(percent_above=54.999)), "breadth-mixed")
        self.assertEqual(classify_breadth(_breadth(percent_above=45.0)), "breadth-weak")
        self.assertEqual(classify_breadth(_breadth(percent_above=45.001)), "breadth-mixed")


class SectorRsCompletenessTests(unittest.TestCase):
    def test_leading_lagging_and_unavailable_all_have_copy(self) -> None:
        leading = _sector_rs(excess_return=0.032)
        self.assertEqual(classify_sector_rs(leading), "sector-rs-leading")
        lagging = _sector_rs(excess_return=-0.01)
        self.assertEqual(classify_sector_rs(lagging), "sector-rs-lagging")
        zero = _sector_rs(excess_return=0.0)
        self.assertEqual(classify_sector_rs(zero), "sector-rs-lagging")
        unavailable = _sector_rs(quality_status="unavailable")
        self.assertEqual(classify_sector_rs(unavailable), "sector-rs-unavailable")
        for result in (leading, lagging, zero, unavailable):
            reading = sector_rs_reading(result)
            self.assertTrue(reading.headline)
            self.assertTrue(reading.explanation)


class MagicNineCompletenessTests(unittest.TestCase):
    """Task 7: direction x count bucket x recently-completed x perfected."""

    def test_setup_none_is_unavailable(self) -> None:
        reading = magic_nine_progress_reading(None)
        self.assertEqual(classify_magic_nine_progress(None), "magic-nine-unavailable")
        self.assertTrue(reading.headline)

    def test_no_active_run_has_copy(self) -> None:
        setup = _setup(None)
        self.assertEqual(
            classify_magic_nine_progress(setup), "magic-nine-no-active-run"
        )
        reading = magic_nine_progress_reading(setup)
        self.assertTrue(reading.headline)

    def test_every_direction_and_count_in_progress_has_copy(self) -> None:
        bucket_by_count = {
            1: "early", 2: "early", 3: "early",
            4: "mid", 5: "mid", 6: "mid",
            7: "late", 8: "late",
        }
        for direction in (Direction.BULLISH, Direction.BEARISH):
            direction_key = "bullish" if direction is Direction.BULLISH else "bearish"
            for count, bucket in bucket_by_count.items():
                setup = _setup(_signal(direction, count, completed=False))
                state = classify_magic_nine_progress(setup)
                self.assertEqual(state, f"magic-nine-{direction_key}-{bucket}")
                reading = magic_nine_progress_reading(setup)
                self.assertIn(str(count), reading.headline)

    def test_franz_example_count_2_bearish(self) -> None:
        setup = _setup(_signal(Direction.BEARISH, 2, completed=False))
        reading = magic_nine_progress_reading(setup)
        self.assertIn("2", reading.headline)
        self.assertIn("9", reading.headline)
        self.assertIn("下跌", reading.headline)

    def test_every_direction_and_perfection_state_at_completion_has_copy(self) -> None:
        for direction in (Direction.BULLISH, Direction.BEARISH):
            direction_key = "bullish" if direction is Direction.BULLISH else "bearish"
            for perfected, suffix in (
                (True, "perfected"),
                (False, "unperfected"),
                (None, "unknown"),
            ):
                setup = _setup(
                    _signal(direction, 9, completed=True, perfected=perfected)
                )
                state = classify_magic_nine_progress(setup)
                self.assertEqual(
                    state, f"magic-nine-{direction_key}-complete-{suffix}"
                )
                reading = magic_nine_progress_reading(setup)
                self.assertTrue(reading.headline)

    def test_an_out_of_range_count_raises_rather_than_falling_back(self) -> None:
        setup = _setup(_signal(Direction.BULLISH, 11, completed=False))
        with self.assertRaises(ValueError):
            classify_magic_nine_progress(setup)

    def test_last_completed_none_has_copy(self) -> None:
        self.assertEqual(
            classify_magic_nine_last_completed(None), "magic-nine-last-completed-none"
        )
        reading = magic_nine_last_completed_reading(None)
        self.assertTrue(reading.headline)

    def test_every_last_completed_direction_and_perfection_state_has_copy(self) -> None:
        for direction in (Direction.BULLISH, Direction.BEARISH):
            direction_key = "bullish" if direction is Direction.BULLISH else "bearish"
            for perfected, suffix in (
                (True, "perfected"),
                (False, "unperfected"),
                (None, "unknown"),
            ):
                last = _signal(direction, 9, completed=True, perfected=perfected)
                state = classify_magic_nine_last_completed(last)
                self.assertEqual(
                    state, f"magic-nine-last-completed-{direction_key}-{suffix}"
                )
                reading = magic_nine_last_completed_reading(last)
                self.assertTrue(reading.headline)


if __name__ == "__main__":
    unittest.main()
