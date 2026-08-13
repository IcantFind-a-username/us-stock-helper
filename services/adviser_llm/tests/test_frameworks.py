from __future__ import annotations

import unittest

from adviser_llm import ANALYSIS_FRAMEWORKS, framework_by_id, select_frameworks


class FrameworkRosterTest(unittest.TestCase):
    def test_the_council_has_thirteen_seats(self) -> None:
        self.assertEqual(len(ANALYSIS_FRAMEWORKS), 13)

    def test_every_seat_is_a_distinct_framework(self) -> None:
        ids = [framework.id for framework in ANALYSIS_FRAMEWORKS]
        self.assertEqual(len(set(ids)), len(ids))

    def test_the_required_lenses_are_all_represented(self) -> None:
        ids = {framework.id for framework in ANALYSIS_FRAMEWORKS}
        for required in (
            "value",
            "growth",
            "macro",
            "geopolitics",
            "technical",
            "quantitative",
            "risk",
            "contrarian",
        ):
            with self.subTest(lens=required):
                self.assertIn(required, ids)

    def test_every_framework_states_a_methodology_and_a_blind_spot(self) -> None:
        for framework in ANALYSIS_FRAMEWORKS:
            with self.subTest(framework=framework.id):
                self.assertTrue(framework.methodology.strip())
                self.assertTrue(framework.blind_spots)
                for blind_spot in framework.blind_spots:
                    self.assertTrue(blind_spot.strip())

    def test_no_framework_claims_to_be_a_named_person(self) -> None:
        # Personality comes from the analysis method, not from impersonating a
        # real investor whose actual views we cannot verify.
        for framework in ANALYSIS_FRAMEWORKS:
            with self.subTest(framework=framework.id):
                self.assertNotIn("巴菲特", framework.display_name)
                self.assertNotIn("Buffett", framework.display_name)

    def test_methodologies_are_not_copies_of_each_other(self) -> None:
        methodologies = {framework.methodology for framework in ANALYSIS_FRAMEWORKS}
        self.assertEqual(len(methodologies), len(ANALYSIS_FRAMEWORKS))

    def test_lookup_by_id(self) -> None:
        self.assertEqual(framework_by_id("value").id, "value")
        with self.assertRaises(KeyError):
            framework_by_id("astrology")


class FrameworkSelectionTest(unittest.TestCase):
    def test_selection_prefers_frameworks_suited_to_the_horizon(self) -> None:
        selected = select_frameworks(horizon="short", maximum=4)
        self.assertLessEqual(len(selected), 4)
        for framework in selected:
            self.assertIn("short", framework.suitable_horizons)

    def test_selection_is_deterministic(self) -> None:
        first = select_frameworks(horizon="swing", maximum=5)
        second = select_frameworks(horizon="swing", maximum=5)
        self.assertEqual(
            [item.id for item in first], [item.id for item in second]
        )

    def test_a_non_positive_maximum_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_frameworks(horizon="swing", maximum=0)

    def test_an_unknown_horizon_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_frameworks(horizon="forever", maximum=3)


if __name__ == "__main__":
    unittest.main()
