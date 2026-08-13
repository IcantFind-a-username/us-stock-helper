from __future__ import annotations

import unittest

from pydantic import ValidationError

from adviser_llm import Citation, Conclusion, CouncilBrief, FrameworkOpinion


class ConclusionSchemaTest(unittest.TestCase):
    def test_conclusion_without_citations_is_rejected_by_the_schema(self) -> None:
        with self.assertRaises(ValidationError):
            Conclusion(
                statement="指引上调利好",
                confidence="medium",
                citations=[],
            )

    def test_conclusion_requires_the_citations_field_at_all(self) -> None:
        with self.assertRaises(ValidationError):
            Conclusion(statement="指引上调利好", confidence="medium")

    def test_model_supplied_url_is_refused(self) -> None:
        # The original link is resolved from the frozen packet, never from the
        # model, because a fabricated URL looks exactly like a real one.
        with self.assertRaises(ValidationError):
            Citation(evidence_id="ev-1", quote="指引上调", url="https://evil.example")

    def test_blank_evidence_id_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Citation(evidence_id="   ", quote="指引上调")

    def test_blank_quote_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Citation(evidence_id="ev-1", quote="")

    def test_confidence_is_ordinal_not_an_invented_number(self) -> None:
        with self.assertRaises(ValidationError):
            Conclusion(
                statement="指引上调利好",
                confidence="0.83",
                citations=[Citation(evidence_id="ev-1", quote="指引上调")],
            )


class SchemaShapeTest(unittest.TestCase):
    def test_generated_json_schema_forbids_extra_properties(self) -> None:
        for model in (Citation, Conclusion, FrameworkOpinion, CouncilBrief):
            with self.subTest(model=model.__name__):
                schema = model.model_json_schema()
                definitions = [schema, *schema.get("$defs", {}).values()]
                for definition in definitions:
                    if definition.get("type") == "object":
                        self.assertIs(
                            definition.get("additionalProperties"),
                            False,
                            msg=f"{model.__name__} allows unmodelled fields",
                        )

    def test_no_schema_field_can_carry_an_order_or_credential(self) -> None:
        forbidden = (
            "order",
            "quantity",
            "shares",
            "broker",
            "account",
            "api_key",
            "token",
            "password",
            "buy",
            "sell",
        )
        for model in (Citation, Conclusion, FrameworkOpinion, CouncilBrief):
            for name in model.model_fields:
                with self.subTest(model=model.__name__, field=name):
                    self.assertNotIn(name.lower(), forbidden)

    def test_framework_opinion_requires_a_stated_blind_spot(self) -> None:
        with self.assertRaises(ValidationError):
            FrameworkOpinion(
                framework_id="value",
                stance="bullish",
                conclusions=[
                    Conclusion(
                        statement="估值有折价",
                        confidence="low",
                        citations=[Citation(evidence_id="ev-1", quote="指引上调")],
                    )
                ],
                blind_spot_note="",
            )

    def test_council_brief_requires_at_least_one_opinion(self) -> None:
        with self.assertRaises(ValidationError):
            CouncilBrief(summary="无", opinions=[])


if __name__ == "__main__":
    unittest.main()
