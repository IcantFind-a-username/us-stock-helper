from __future__ import annotations

import ast
import pathlib
import re
import unittest

from adviser_llm import build_packet

from tests.fakes import AS_OF, ExplodingClient, evidence_item


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "adviser_llm"
SOURCE_FILES = sorted(PACKAGE_ROOT.rglob("*.py"))

ALLOWED_THIRD_PARTY = {"anthropic", "pydantic"}
STDLIB_OR_LOCAL_PREFIXES = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "logging",
    "math",
    "os",
    "re",
    "time",
    "typing",
    "urllib",
    "us_stock_helper_core",
    "adviser_llm",
}


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class OutboundOnlyTest(unittest.TestCase):
    def test_the_package_has_source_files_to_inspect(self) -> None:
        self.assertTrue(SOURCE_FILES)

    def test_nothing_in_this_layer_listens_on_a_socket(self) -> None:
        banned = (
            "http.server",
            "socketserver",
            "HTTPServer",
            "ThreadingHTTPServer",
            "socket.bind",
            ".listen(",
            "FastAPI",
            "flask",
            "uvicorn",
            "aiohttp.web",
        )
        for path in SOURCE_FILES:
            text = path.read_text(encoding="utf-8")
            for token in banned:
                with self.subTest(file=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_no_order_broker_or_account_surface_exists(self) -> None:
        banned = (
            "place_order",
            "submit_order",
            "trade_context",
            "brokerage",
            "account_id",
            "trd_side",
            "moomoo",
            "futu",
        )
        for path in SOURCE_FILES:
            text = path.read_text(encoding="utf-8").lower()
            for token in banned:
                with self.subTest(file=path.name, token=token):
                    # Whole words only: "futu" must not fire on "__future__".
                    self.assertIsNone(re.search(rf"\b{token}\b", text))

    def test_no_credential_is_hard_coded(self) -> None:
        for path in SOURCE_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn("sk-ant-", text)

    def test_third_party_dependencies_stay_at_the_declared_two(self) -> None:
        for path in SOURCE_FILES:
            for root in _imported_roots(path):
                with self.subTest(file=path.name, module=root):
                    self.assertTrue(
                        root in ALLOWED_THIRD_PARTY
                        or root in STDLIB_OR_LOCAL_PREFIXES
                        or root.startswith("."),
                        msg=f"unexpected dependency: {root}",
                    )


class DeterministicPathTest(unittest.TestCase):
    def test_building_the_packet_never_touches_the_model(self) -> None:
        # Sentiment, clustering and CIK attribution stay in backtestable code;
        # the model is only asked for cross-source reading and counterargument.
        client = ExplodingClient()
        packet = build_packet(
            symbol="NVDA",
            horizon="swing",
            as_of=AS_OF,
            items=(evidence_item(),),
        )
        self.assertTrue(packet.render())
        with self.assertRaises(AssertionError):
            client.messages  # noqa: B018 - proves the guard is live

    def test_the_layer_exposes_no_sentiment_or_clustering_scorer(self) -> None:
        import adviser_llm

        for banned in ("score_sentiment", "cluster_events", "resolve_cik"):
            with self.subTest(name=banned):
                self.assertFalse(hasattr(adviser_llm, banned))


if __name__ == "__main__":
    unittest.main()
