from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from information_layer.factors import (
    FactorInput,
    FactorReading,
    FactorSnapshot,
    FactorUnavailable,
)
from us_stock_helper_analysis_api.institutional_flow_provider import (
    InstitutionalFlowReading,
)
from us_stock_helper_analysis_api.service import AnalysisService
from us_stock_helper_core import OHLCVBar


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)


def bars(
    count: int = 40,
    *,
    flat: bool = False,
    newest_available_at: datetime = AS_OF,
) -> tuple[OHLCVBar, ...]:
    rows = []
    for index in range(count):
        closed_at = newest_available_at - timedelta(days=count - 1 - index)
        price = 100.0 if flat else 100.0 + index * 0.5
        rows.append(
            OHLCVBar(
                symbol="NVDA",
                interval="day",
                opened_at=closed_at - timedelta(days=1),
                closed_at=closed_at,
                available_at=closed_at,
                open=price,
                high=price if flat else price + 0.5,
                low=price if flat else price - 0.5,
                close=price,
                volume=1_000_000.0,
            )
        )
    return tuple(rows)


def evidence(
    *,
    stamped: bool = False,
    stale: bool = False,
) -> tuple[EvidenceEvent, ...]:
    # A collector stamps what it measured; evidence that reached the service
    # by any other route carries no measurement at all.
    stamps = (
        (("freshness_seconds", "1140"), ("stale", "true" if stale else "false"))
        if stamped
        else ()
    )
    return tuple(
        EvidenceEvent.create(
            event_id=event_id,
            claim_key=f"claim-{event_id}",
            headline="NVIDIA raises full-year revenue guidance",
            summary="The chipmaker lifted its outlook.",
            provenance=SourceProvenance(
                source_id=f"feed:{publisher}",
                publisher_id=publisher,
                publisher_name=publisher,
                canonical_url=f"https://{publisher}.example/{event_id}",
                source_type="wire",
                reliability=0.9,
            ),
            event_time=AS_OF - timedelta(minutes=40),
            published_at=AS_OF - timedelta(minutes=30),
            first_seen_at=AS_OF - timedelta(minutes=20),
            available_at=AS_OF - timedelta(minutes=19),
            retrieved_at=AS_OF - timedelta(minutes=18),
            claim_status=ClaimStatus.VERIFIED,
            sentiment=0.7,
            confidence=0.9,
            symbol_relevance=(("NVDA", 0.95),),
            attributes=stamps,
        )
        for event_id, publisher in (("a", "reuters"), ("b", "bloomberg"))
    )


class Provider:
    def __init__(
        self,
        *,
        rows: tuple[OHLCVBar, ...] | None = None,
        stamped: bool = False,
        stale: bool = False,
    ) -> None:
        self.rows = bars() if rows is None else rows
        self.stamped = stamped
        self.stale = stale
        self.queries: list[tuple[str, str]] = []

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self.queries.append((symbol, interval))
        return self.rows

    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
        return evidence(stamped=self.stamped, stale=self.stale)


class SnapshotWithAnomalousHoldings:
    @property
    def institutional_holdings(self) -> tuple[()]:
        raise AssertionError("daily analysis must not read stock-snapshot holdings")


class CandlesOnlyProvider(Provider):
    stock_snapshot = SnapshotWithAnomalousHoldings()


def measured_factor(name: str, value: float) -> FactorReading:
    published = AS_OF - timedelta(days=1)
    return FactorReading.measured(
        factor=name,
        method_version=f"{name}-test-v1",
        as_of=AS_OF,
        value=value,
        detail=f"{name} measured from a primary source",
        inputs=(
            FactorInput(
                name=f"{name}_input",
                value=value,
                observed_at=published,
                available_at=published,
                source_url="https://example.test/factor",
            ),
        ),
    )


class ProviderWithFactors(Provider):
    def __init__(self) -> None:
        super().__init__()
        self.factor_queries: list[tuple[str, datetime]] = []

    def factors_for(self, symbol: str, as_of: datetime) -> FactorSnapshot:
        self.factor_queries.append((symbol, as_of))
        return FactorSnapshot(
            symbol=symbol,
            as_of=as_of,
            macro=measured_factor("macro", 0.2),
            geopolitics=FactorReading.unavailable(
                factor="geopolitics",
                method_version="abstained-v1",
                as_of=as_of,
                reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
                detail="No qualified source.",
            ),
            fundamentals=measured_factor("fundamentals", 0.6),
        )


class ProviderWithBrokenFactors(Provider):
    """`factors_for` exists but raises — the whole factor layer is down."""

    def factors_for(self, symbol: str, as_of: datetime) -> FactorSnapshot:
        raise RuntimeError("factor source unreachable")


class ProviderWithMalformedFactors(Provider):
    """`factors_for` exists but hands back something that is not a snapshot."""

    def factors_for(self, symbol: str, as_of: datetime) -> object:
        return {"not": "a snapshot"}


class ProviderWithInstitutionalFlow(Provider):
    def __init__(self, reading: InstitutionalFlowReading) -> None:
        super().__init__()
        self.reading_value = reading
        self.institutional_flow_queries: list[tuple[str, datetime]] = []

    def institutional_flow_for(
        self, symbol: str, as_of: datetime
    ) -> InstitutionalFlowReading:
        self.institutional_flow_queries.append((symbol, as_of))
        return self.reading_value


class ProviderWithBrokenInstitutionalFlow(Provider):
    """`institutional_flow_for` exists but raises — one source is down."""

    def institutional_flow_for(
        self, symbol: str, as_of: datetime
    ) -> InstitutionalFlowReading:
        raise RuntimeError("institutional flow source unreachable")


class ProviderWithMalformedInstitutionalFlow(Provider):
    """`institutional_flow_for` exists but hands back the wrong shape."""

    def institutional_flow_for(self, symbol: str, as_of: datetime) -> object:
        return {"not": "a reading"}


def service(provider: Provider | None = None) -> AnalysisService:
    return AnalysisService(provider or Provider(), clock=lambda: AS_OF)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= _all_keys(item)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found |= _all_keys(item)
        return found
    return set()


class AnalysisContractTests(unittest.TestCase):
    def test_a_decision_reports_its_score_and_what_it_could_not_see(self) -> None:
        provider = Provider()
        result = service(provider).decision("NVDA", "short")

        self.assertEqual(result["schemaVersion"], "1")
        self.assertEqual(result["symbol"], "NVDA")
        self.assertEqual(result["horizon"], "short")
        self.assertEqual(result["interval"], "day")
        self.assertEqual(provider.queries, [("NVDA", "day")])
        self.assertEqual(result["decisionCutoff"], "2026-07-25T16:00:00Z")
        score = result["score"]
        self.assertGreaterEqual(score["value"], 0.0)
        self.assertLessEqual(score["value"], 100.0)
        # Macro, geopolitics, institutional flow and fundamentals have no feed
        # yet, and the response has to say so rather than imply a full picture.
        self.assertIn("macro", score["unavailableFactors"])
        self.assertLess(score["factorCoverage"], 1.0)
        self.assertGreater(score["factorCoverage"], 0.0)

    def test_every_factor_contribution_is_itemized(self) -> None:
        result = service().decision("NVDA", "short")

        names = {item["name"] for item in result["score"]["contributions"]}
        self.assertIn("technical_trend", names)
        unavailable = next(
            item
            for item in result["score"]["contributions"]
            if item["name"] == "macro"
        )
        self.assertIsNone(unavailable["rawValue"])
        self.assertEqual(unavailable["points"], 0.0)

    def test_public_macro_and_fundamentals_reach_the_score_for_any_symbol(self) -> None:
        provider = ProviderWithFactors()

        result = service(provider).decision("nvda", "short")

        self.assertEqual(provider.factor_queries, [("NVDA", AS_OF)])
        self.assertAlmostEqual(result["score"]["factorCoverage"], 0.8)
        self.assertNotIn("macro", result["score"]["unavailableFactors"])
        self.assertNotIn("fundamentals", result["score"]["unavailableFactors"])
        contributions = {
            item["name"]: item for item in result["score"]["contributions"]
        }
        self.assertEqual(contributions["macro"]["rawValue"], 0.2)
        self.assertEqual(contributions["fundamentals"]["rawValue"], 0.6)

    def test_unavailable_factor_notes_name_the_factor_and_the_reason_code(
        self,
    ) -> None:
        # Pinned deliberately in this raw, code-bearing shape: `name` and
        # `reason.value` are stable wire identifiers (mirrors "Hard gate
        # active: <gate>,<gate>"), and apps/mobile/src/i18n/serverVocabulary.ts
        # is what turns this into Chinese for the screen, not this service.
        # This is the exact note Franz's 2026-08-15 real-mode QA reported as
        # unreadable code-log English on the stock page.
        provider = ProviderWithFactors()

        result = service(provider).decision("NVDA", "short")

        self.assertIn(
            "geopolitics unavailable (no_qualified_source).", result["notes"]
        )

    def test_a_broken_factor_source_degrades_into_a_chinese_note(self) -> None:
        # Investor-readable Chinese (2026-08-15 served-copy sweep): this is
        # pure server-authored prose with no embedded machine identifier, so
        # unlike the note pinned above it is translated at the source.
        result = service(ProviderWithBrokenFactors()).decision("NVDA", "short")

        self.assertIn("本次未能读取公开因子数据源。", result["notes"])
        self.assertFalse(
            any("Public factor sources" in note for note in result["notes"])
        )

    def test_a_malformed_factor_snapshot_degrades_into_a_chinese_note(self) -> None:
        result = service(ProviderWithMalformedFactors()).decision("NVDA", "short")

        self.assertIn("公开因子数据源返回了不支持的快照格式。", result["notes"])

    def test_institutional_flow_reaches_the_score_when_the_provider_supplies_it(
        self,
    ) -> None:
        # 2026-08-15 institutional-capital factor wiring: this factor used to
        # be permanently unavailable everywhere. A provider that actually
        # supplies data must lift factor_coverage and land a real
        # contribution, not stay stuck in unavailableFactors.
        provider = ProviderWithInstitutionalFlow(
            InstitutionalFlowReading(
                value=0.42, unavailable_reason=None, detail="blended"
            )
        )

        result = service(provider).decision("NVDA", "short")

        self.assertEqual(provider.institutional_flow_queries, [("NVDA", AS_OF)])
        self.assertNotIn(
            "institutional_flow", result["score"]["unavailableFactors"]
        )
        contributions = {
            item["name"]: item for item in result["score"]["contributions"]
        }
        self.assertEqual(contributions["institutional_flow"]["rawValue"], 0.42)
        self.assertFalse(
            any("institutional_flow unavailable" in note for note in result["notes"])
        )

    def test_institutional_flow_stays_honestly_unavailable_with_a_named_reason(
        self,
    ) -> None:
        # The named reason distinguishes "no data for this symbol today"
        # from the old blanket "未接入" — the exact semantics the plan asked
        # for: symbols without data show *why*, not a generic never-wired
        # label.
        provider = ProviderWithInstitutionalFlow(
            InstitutionalFlowReading(
                value=None,
                unavailable_reason=FactorUnavailable.NO_DATA_AT_CUTOFF,
                detail="neither ingredient was available",
            )
        )

        result = service(provider).decision("NVDA", "short")

        self.assertIn("institutional_flow", result["score"]["unavailableFactors"])
        self.assertIn(
            "institutional_flow unavailable (no_data_at_cutoff).",
            result["notes"],
        )

    def test_a_broken_institutional_flow_source_degrades_into_a_chinese_note(
        self,
    ) -> None:
        result = service(ProviderWithBrokenInstitutionalFlow()).decision(
            "NVDA", "short"
        )

        self.assertIn("本次未能读取机构资金数据源。", result["notes"])
        self.assertIn(
            "institutional_flow", result["score"]["unavailableFactors"]
        )

    def test_a_malformed_institutional_flow_reading_degrades_into_a_chinese_note(
        self,
    ) -> None:
        result = service(ProviderWithMalformedInstitutionalFlow()).decision(
            "NVDA", "short"
        )

        self.assertIn("机构资金数据源返回了不支持的读数格式。", result["notes"])

    def test_the_forecast_carries_three_scenarios_and_its_disclaimer(self) -> None:
        forecast = service().decision("NVDA", "short")["forecast"]

        self.assertIsNotNone(forecast)
        kinds = [case["kind"] for case in forecast["cases"]]
        self.assertEqual(sorted(kinds), ["base", "bear", "bull"])
        self.assertAlmostEqual(
            sum(case["probability"] for case in forecast["cases"]), 1.0, places=9
        )
        self.assertTrue(forecast["disclaimer"])
        self.assertEqual(forecast["calibrationStatus"], "uncalibrated")
        self.assertTrue(forecast["invalidationConditions"])

    def test_the_forecast_invalidation_condition_and_scenarios_are_chinese(
        self,
    ) -> None:
        # Investor-readable Chinese (2026-08-15 served-copy sweep): both ride
        # the wire verbatim with no client-side translation table.
        forecast = service().decision("NVDA", "short")["forecast"]

        self.assertIn("引用的证据被撤回或被证伪。", forecast["invalidationConditions"])
        explanations = {case["kind"]: case["explanation"] for case in forecast["cases"]}
        for explanation in explanations.values():
            self.assertNotRegex(explanation, r"[a-z]{3,}")

    def test_an_unmeasurable_volatility_yields_no_forecast_and_says_why(
        self,
    ) -> None:
        result = service(Provider(rows=bars(flat=True))).decision("NVDA", "short")

        # A band of no width shown as confidently as a measured one is worse
        # than showing nothing.
        self.assertIsNone(result["forecast"])
        self.assertIsNone(result["riskPlan"])
        self.assertTrue(
            any("volatility" in note.lower() for note in result["notes"])
        )

    def test_the_plan_is_analysis_only_and_never_offers_to_trade(self) -> None:
        result = service().decision("NVDA", "short")

        plan = result["riskPlan"]
        self.assertIn(plan["action"], {"long", "short", "watch", "avoid"})
        self.assertLessEqual(plan["maxPositionPercent"], 100.0)
        self.assertGreaterEqual(plan["leverage"], 0.0)
        # The invariant is that nothing here can act, not that the word
        # "order" is absent — the plan's own warning says it cannot place one.
        self.assertTrue(
            any("cannot" in warning.lower() for warning in plan["warnings"])
        )
        forbidden_fields = {
            "orderId",
            "submitOrder",
            "quantity",
            "accountId",
            "brokerToken",
        }
        self.assertEqual(forbidden_fields & set(_all_keys(result)), set())

    def test_evidence_citations_travel_with_the_conclusion(self) -> None:
        result = service().decision("NVDA", "short")

        self.assertTrue(result["citations"])
        for citation in result["citations"]:
            self.assertTrue(citation["url"].startswith("https://"))
            self.assertTrue(citation["publisher"])
            self.assertTrue(citation["availableAt"])

    def test_a_citation_carries_the_age_measured_when_it_was_read(self) -> None:
        result = service(Provider(stamped=True)).decision("NVDA", "short")

        for citation in result["citations"]:
            self.assertEqual(citation["freshnessSeconds"], 1140)
            self.assertIs(citation["stale"], False)

    def test_evidence_with_no_measured_age_says_so_rather_than_reporting_zero(
        self,
    ) -> None:
        # Zero seconds old is a measurement. Evidence that never passed a
        # collector has no measurement at all, and the two must not look alike.
        result = service().decision("NVDA", "short")

        for citation in result["citations"]:
            self.assertIsNone(citation["freshnessSeconds"])
            self.assertIsNone(citation["stale"])

    def test_stale_evidence_is_cited_and_flagged_rather_than_dropped(self) -> None:
        result = service(Provider(stamped=True, stale=True)).decision("NVDA", "short")

        self.assertTrue(result["citations"])
        for citation in result["citations"]:
            self.assertIs(citation["stale"], True)
        self.assertTrue(any("stale" in note.lower() for note in result["notes"]))

    def test_a_symbol_with_zero_evidence_serves_an_unmeasured_sentiment(
        self,
    ) -> None:
        # sentiment.py's uncertainty marker used to be gated on `clusters`
        # being non-empty, so a symbol with no evidence at all -- the
        # simplest way to be unmeasured -- served conclusion 中性 with an
        # empty uncertainty array, indistinguishable from a measured neutral
        # read straight off the wire.
        class NoEvidenceProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return ()

        result = service(NoEvidenceProvider()).decision("NVDA", "short")

        self.assertEqual(result["citations"], [])
        self.assertIn("情绪未测量", result["sentiment"]["uncertainty"])
        self.assertIn("market_sentiment", result["score"]["unavailableFactors"])

    def test_an_unknown_horizon_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            service().decision("NVDA", "forever")

    def test_the_requested_symbol_reaches_the_provider_normalized(self) -> None:
        provider = Provider()

        service(provider).decision(" nvda ", "short")

        self.assertEqual(provider.queries[0][0], "NVDA")

    def test_no_bars_yields_an_explicit_unavailable_rather_than_a_guess(
        self,
    ) -> None:
        result = service(Provider(rows=())).decision("NVDA", "short")

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["score"])
        self.assertTrue(result["notes"])

    def test_a_live_decision_is_marked_live(self) -> None:
        self.assertEqual(service().decision("NVDA", "short")["status"], "live")

    def test_completed_daily_bars_stay_live_when_snapshot_holdings_are_anomalous(
        self,
    ) -> None:
        result = service(CandlesOnlyProvider()).decision("NVDA", "short")

        self.assertEqual(result["status"], "live")
        self.assertEqual(result["interval"], "day")
        self.assertIsInstance(result["score"]["value"], float)

    def test_a_short_horizon_decision_on_yesterdays_close_is_not_stale_gated(
        self,
    ) -> None:
        # This is the shape live data actually takes: every horizon is fed
        # completed daily bars, and mid-session the newest one is yesterday's
        # close (~22h old). A freshness gate budgeted for intraday cadence
        # stale-gated this every request outside the 20 minutes after a
        # session's close.
        provider = Provider(
            rows=bars(newest_available_at=AS_OF - timedelta(hours=22))
        )

        result = service(provider).decision("NVDA", "short")

        self.assertNotIn("stale_data", result["score"]["blockedBy"])
        self.assertTrue(result["score"]["actionable"])
        self.assertNotEqual(result["riskPlan"]["action"], "avoid")

    def test_a_short_horizon_decision_on_a_many_day_old_close_is_still_stale_gated(
        self,
    ) -> None:
        # The wider daily-cadence budget must not stop catching a feed that
        # has genuinely stopped publishing.
        provider = Provider(
            rows=bars(newest_available_at=AS_OF - timedelta(days=10))
        )

        result = service(provider).decision("NVDA", "short")

        self.assertIn("stale_data", result["score"]["blockedBy"])
        self.assertFalse(result["score"]["actionable"])
        self.assertEqual(result["riskPlan"]["action"], "avoid")


if __name__ == "__main__":
    unittest.main()


class CutoffRaceTests(unittest.TestCase):
    def test_a_bar_that_lands_during_the_fetch_does_not_fail_the_request(
        self,
    ) -> None:
        """The cutoff has to be taken after the data is in hand.

        Sampling it first meant any bar published during the round trip was
        newer than the cutoff, and the chain's own invariant then rejected the
        request. The sibling services select as of a cutoff rather than
        exploding on data that arrived a moment early.
        """

        rows = bars()
        late = replace(rows[-1], available_at=AS_OF + timedelta(seconds=2))
        moments = iter([AS_OF, AS_OF + timedelta(seconds=5)])

        class SlowProvider(Provider):
            def bars_for(self, symbol: str, interval: str):
                # The round trip takes time; the bar lands while it is in
                # flight.
                next(moments)
                return super().bars_for(symbol, interval)

        result = AnalysisService(
            SlowProvider(rows=rows[:-1] + (late,)), clock=lambda: next(moments)
        ).decision("NVDA", "short")

        self.assertEqual(result["status"], "live")


class EvidenceCutoffRaceTests(unittest.TestCase):
    """Evidence the request itself fetched must reach the conclusion.

    The bar-side race was fixed by taking the cutoff after the bars were in
    hand; the evidence fetch had the same race with a quieter failure. A live
    collector stamps available_at = retrieved_at, so every event first
    retrieved during the request landed after a cutoff sampled before the
    fetch and was silently filed as future — the request a user makes on
    seeing breaking news was served a measured-looking neutral built on
    nothing, with no disclosure.
    """

    @staticmethod
    def retrieved_now(retrieved: datetime) -> tuple[EvidenceEvent, ...]:
        # The warm-store steady state: a collector polled by the request
        # stamps what it fetched with the moment of the fetch itself.
        return tuple(
            replace(
                item,
                published_at=retrieved - timedelta(minutes=1),
                first_seen_at=retrieved,
                available_at=retrieved,
                retrieved_at=retrieved,
            )
            for item in evidence()
        )

    def test_evidence_fetched_during_the_request_reaches_the_conclusion(
        self,
    ) -> None:
        now = {"value": AS_OF}
        make = self.retrieved_now

        class BreakingNewsProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                # The fetch takes time, and everything it returns was
                # retrieved at the end of that time.
                now["value"] += timedelta(seconds=2)
                return make(now["value"])

        raced = AnalysisService(
            BreakingNewsProvider(), clock=lambda: now["value"]
        ).decision("NVDA", "short")
        settled = service().decision("NVDA", "short")

        # Identical evidence, retrieved during the request instead of before
        # it, must not flip the served conclusion.
        self.assertEqual(
            [item["id"] for item in raced["citations"]],
            [item["id"] for item in settled["citations"]],
        )
        self.assertEqual(
            raced["sentiment"]["conclusion"],
            settled["sentiment"]["conclusion"],
        )
        self.assertEqual(
            raced["sentiment"]["actionScore"],
            settled["sentiment"]["actionScore"],
        )
        self.assertEqual(raced["score"]["value"], settled["score"]["value"])

    def test_evidence_still_future_at_the_cutoff_is_named_in_the_notes(
        self,
    ) -> None:
        # An event stamped after even the honestly-taken cutoff (an embargo,
        # a skewed publisher clock) is excluded by the point-in-time
        # invariant — but never silently: an exclusion the reader cannot see
        # is a patched record, not a protected one.
        embargoed = tuple(
            replace(
                item,
                event_id=f"embargoed-{item.event_id}",
                published_at=AS_OF + timedelta(minutes=5),
                first_seen_at=AS_OF + timedelta(minutes=5),
                available_at=AS_OF + timedelta(minutes=5),
                retrieved_at=AS_OF + timedelta(minutes=5),
            )
            for item in evidence()
        )

        class EmbargoedProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return embargoed

        payload = service(EmbargoedProvider()).decision("NVDA", "short")

        self.assertTrue(
            any(
                "embargoed-a" in note and "embargoed-b" in note
                for note in payload["notes"]
            ),
            f"the excluded evidence was not disclosed: {payload['notes']}",
        )


class UnreadableSourceTests(unittest.TestCase):
    """A partial evidence sweep must be served, and must say it was partial."""

    class PartiallyReadProvider(Provider):
        def evidence_gaps(self) -> tuple[str, ...]:
            return ("sec-current-8-k（unreachable）",)

    def test_a_source_that_could_not_be_read_is_named_in_the_notes(self) -> None:
        # Refusing the whole decision over one slow publisher showed up as
        # every symbol failing at once, so the decision is served — but a
        # reader must not mistake a partial sweep of the news for a full one.
        payload = service(self.PartiallyReadProvider()).decision("NVDA", "short")

        self.assertTrue(
            any("sec-current-8-k" in note for note in payload["notes"]),
            f"the unread source was not named: {payload['notes']}",
        )

    def test_a_complete_sweep_says_nothing_about_gaps(self) -> None:
        payload = service().decision("NVDA", "short")

        self.assertFalse(
            any("情报源" in note for note in payload["notes"]),
            f"a complete sweep invented a gap: {payload['notes']}",
        )
