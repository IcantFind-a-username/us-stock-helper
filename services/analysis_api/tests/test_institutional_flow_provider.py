from __future__ import annotations

import unittest
from datetime import UTC, datetime

from information_layer.factors.base import FactorUnavailable
from us_stock_helper_analysis_api.gateway_provider import (
    HoldingsDisclosure,
    InstitutionalFlowInputs,
    MarketGatewayUnavailable,
    SectionFailure,
)
from us_stock_helper_analysis_api.institutional_flow_provider import (
    DISCLOSURE_CONFIDENCE,
    DISCLOSURE_TREND_SCALE_POINTS,
    PROXY_CONFIDENCE,
    GatewayInstitutionalFlowProvider,
    InstitutionalFlowReading,
    blend,
)
from us_stock_helper_core import ParticipationBar


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)
CLOSED_AT = datetime(2026, 7, 25, 15, 55, tzinfo=UTC)


def live_bar(
    *,
    main_activity: float = 100.0,
    retail_activity: float = 50.0,
    net_flow: float = 50.0,
) -> ParticipationBar:
    total = main_activity + retail_activity
    return ParticipationBar(
        symbol="NVDA",
        interval="5m",
        closed_at=CLOSED_AT,
        available_at=CLOSED_AT,
        main_share=main_activity / total,
        retail_share=retail_activity / total,
        main_activity=main_activity,
        retail_activity=retail_activity,
        net_flow=net_flow,
        coverage=1.0,
        quality_status="live",
        missing_reason=None,
        method_version="order-size-activity-share-v1",
    )


def unavailable_bar(reason: str = "zero activity denominator") -> ParticipationBar:
    return ParticipationBar(
        symbol="NVDA",
        interval="5m",
        closed_at=CLOSED_AT,
        available_at=CLOSED_AT,
        main_share=None,
        retail_share=None,
        main_activity=None,
        retail_activity=None,
        net_flow=None,
        coverage=0.0,
        quality_status="unavailable",
        missing_reason=reason,
        method_version="order-size-activity-share-v1",
    )


def disclosure(
    *,
    holding_percent_change: float = 2.5,
    reported_at: datetime = datetime(2026, 6, 30, tzinfo=UTC),
    available_at: datetime = datetime(2026, 7, 20, 22, tzinfo=UTC),
) -> HoldingsDisclosure:
    return HoldingsDisclosure(
        reported_at=reported_at,
        available_at=available_at,
        institution_count_change=3,
        holding_percent=62.0,
        holding_percent_change=holding_percent_change,
    )


class BlendBothIngredientsTests(unittest.TestCase):
    def test_both_ingredients_present_blend_at_their_stated_confidence(self) -> None:
        # proxy_raw = net_flow / (main_activity+retail_activity) = 50/150 = 1/3
        # disclosure_raw = holding_percent_change / scale = 2.5/5.0 = 0.5
        # blended = (1/3*PROXY_CONFIDENCE + 0.5*DISCLOSURE_CONFIDENCE)
        #           / (PROXY_CONFIDENCE + DISCLOSURE_CONFIDENCE)
        inputs = InstitutionalFlowInputs(
            participation_bars=(live_bar(),), holdings=(disclosure(),)
        )

        reading = blend("NVDA", inputs)

        expected = (
            (1 / 3) * PROXY_CONFIDENCE + 0.5 * DISCLOSURE_CONFIDENCE
        ) / (PROXY_CONFIDENCE + DISCLOSURE_CONFIDENCE)
        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(reading.value, expected, places=6)
        self.assertIsNone(reading.unavailable_reason)

    def test_the_proxy_is_discounted_below_its_own_raw_reading(self) -> None:
        # Proxy-vs-disclosure red line: an estimate never reaches the same
        # magnitude a verified disclosure would for the same raw signal.
        proxy_only = blend(
            "NVDA",
            InstitutionalFlowInputs(participation_bars=(live_bar(),), holdings=()),
        )
        disclosure_only = blend(
            "NVDA",
            InstitutionalFlowInputs(
                participation_bars=(),
                holdings=(
                    disclosure(
                        holding_percent_change=(1 / 3)
                        * DISCLOSURE_TREND_SCALE_POINTS
                    ),
                ),
            ),
        )

        # Both start from the same raw signal (1/3): the proxy's contribution
        # must come out strictly smaller once confidence is applied.
        assert proxy_only.value is not None
        assert disclosure_only.value is not None
        self.assertLess(abs(proxy_only.value), abs(disclosure_only.value))
        self.assertAlmostEqual(proxy_only.value, (1 / 3) * PROXY_CONFIDENCE, places=6)
        self.assertAlmostEqual(disclosure_only.value, 1 / 3, places=6)


class HonestAbsenceTests(unittest.TestCase):
    def test_neither_ingredient_present_is_honestly_unavailable(self) -> None:
        reading = blend("NVDA", InstitutionalFlowInputs((), ()))

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )
        self.assertIn("NVDA", reading.detail)

    def test_a_participation_bar_that_is_not_live_does_not_count_as_present(
        self,
    ) -> None:
        reading = blend(
            "NVDA",
            InstitutionalFlowInputs(
                participation_bars=(unavailable_bar(),), holdings=()
            ),
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )

    def test_only_the_latest_live_bar_is_read(self) -> None:
        stale = unavailable_bar()
        fresh = live_bar(net_flow=0.0, main_activity=1.0, retail_activity=1.0)
        reading = blend(
            "NVDA",
            InstitutionalFlowInputs(
                participation_bars=(fresh, stale), holdings=()
            ),
        )

        # The unavailable bar sorts after the live one here on purpose: the
        # search must scan for the newest *live* bar, not just take index -1.
        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(reading.value, 0.0, places=6)


class SectionFailureTaxonomyTests(unittest.TestCase):
    """A gateway-declared section failure must not read as a quiet market.

    Before `flow_section_failure`/`holdings_section_failure` existed, both a
    genuinely quiet symbol and a symbol whose gateway sections failed outright
    produced the identical NO_DATA_AT_CUTOFF reading -- the gateway_provider
    empty tuples carried no memory of which case it was.
    """

    def test_both_sections_failing_is_source_unreachable_not_no_data(self) -> None:
        inputs = InstitutionalFlowInputs(
            participation_bars=(),
            holdings=(),
            flow_section_failure=SectionFailure(
                status="unavailable", reason="当前交易时段资金流数据不可用"
            ),
            holdings_section_failure=SectionFailure(
                status="unavailable", reason="机构持仓数据不可用"
            ),
        )

        reading = blend("NVDA", inputs)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.SOURCE_UNREACHABLE
        )
        self.assertIn("当前交易时段资金流数据不可用", reading.detail)
        self.assertIn("机构持仓数据不可用", reading.detail)

    def test_one_failed_section_is_enough_to_call_it_source_unreachable(
        self,
    ) -> None:
        # The flow section failed outright; holdings simply had nothing on
        # file (no failure recorded). The reading still owes the reader the
        # honest "a source failed" reason rather than the softer "no data".
        inputs = InstitutionalFlowInputs(
            participation_bars=(),
            holdings=(),
            flow_section_failure=SectionFailure(status="stale", reason=None),
            holdings_section_failure=None,
        )

        reading = blend("NVDA", inputs)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.SOURCE_UNREACHABLE
        )

    def test_no_declared_failure_at_all_stays_no_data_at_cutoff(self) -> None:
        # Regression guard: a genuinely quiet symbol -- the gateway answered,
        # both sections validated, neither had a row -- must keep reading as
        # NO_DATA_AT_CUTOFF now that failures are tracked, not get swept into
        # SOURCE_UNREACHABLE by accident.
        reading = blend(
            "NVDA",
            InstitutionalFlowInputs(
                participation_bars=(),
                holdings=(),
                flow_section_failure=None,
                holdings_section_failure=None,
            ),
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )


class ReadingInvariantTests(unittest.TestCase):
    def test_a_reading_cannot_carry_both_a_value_and_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            InstitutionalFlowReading(
                value=0.1,
                unavailable_reason=FactorUnavailable.NO_DATA_AT_CUTOFF,
                detail="contradictory",
            )

    def test_a_reading_cannot_carry_neither(self) -> None:
        with self.assertRaises(ValueError):
            InstitutionalFlowReading(
                value=None, unavailable_reason=None, detail="empty"
            )


class GatewayInstitutionalFlowProviderTests(unittest.TestCase):
    def test_a_gateway_failure_degrades_into_source_unreachable(self) -> None:
        class BrokenGateway:
            def institutional_flow_inputs_for(
                self, symbol: str, as_of: datetime
            ) -> InstitutionalFlowInputs:
                raise MarketGatewayUnavailable("the gateway is down")

        provider = GatewayInstitutionalFlowProvider(gateway=BrokenGateway())

        reading = provider.reading(symbol="NVDA", as_of=AS_OF)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.SOURCE_UNREACHABLE
        )

    def test_a_healthy_gateway_reaches_the_blend(self) -> None:
        class WorkingGateway:
            def institutional_flow_inputs_for(
                self, symbol: str, as_of: datetime
            ) -> InstitutionalFlowInputs:
                return InstitutionalFlowInputs(
                    participation_bars=(live_bar(),), holdings=(disclosure(),)
                )

        provider = GatewayInstitutionalFlowProvider(gateway=WorkingGateway())

        reading = provider.reading(symbol="NVDA", as_of=AS_OF)

        self.assertIsNotNone(reading.value)
        self.assertIsNone(reading.unavailable_reason)


if __name__ == "__main__":
    unittest.main()
