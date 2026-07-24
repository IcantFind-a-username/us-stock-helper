from __future__ import annotations

import math
import re

from .models import CompactRender, EvidencePacket


_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII_RUN = re.compile(r"[A-Za-z0-9_.:+-]+")


def estimate_tokens(text: str) -> int:
    """Conservative local estimate; production callers may replace the tokenizer."""

    cjk_count = len(_CJK.findall(text))
    without_cjk = _CJK.sub(" ", text)
    ascii_tokens = sum(
        math.ceil(len(match.group(0)) / 4)
        for match in _ASCII_RUN.finditer(without_cjk)
    )
    punctuation = len(
        re.sub(r"[\sA-Za-z0-9_.:+\-\u3400-\u9fff]", "", text)
    )
    return cjk_count + ascii_tokens + math.ceil(punctuation / 2)


def compact_render(packet: EvidencePacket, *, max_tokens: int) -> CompactRender:
    if max_tokens < 24:
        raise ValueError("max_tokens must be at least 24")

    citation_by_event = {
        citation.event_id: citation.citation_id for citation in packet.citations
    }
    first_citation = (
        f" [{packet.citations[0].citation_id}]" if packet.citations else ""
    )
    lines = [
        (
            f"结论:{packet.sentiment.conclusion} "
            f"行动分:{packet.sentiment.action_score:+.2f} "
            f"置信:{packet.sentiment.confidence:.2f}"
            f"{first_citation}"
        )
    ]
    omitted = 0
    for cluster in sorted(
        packet.clusters,
        key=lambda item: (
            not item.actionable,
            -abs(item.sentiment),
            item.cluster_id,
        ),
    ):
        marker = (
            "观察"
            if not cluster.actionable
            else ("利多" if cluster.sentiment > 0 else "利空")
        )
        citation_id = citation_by_event.get(cluster.active_event_id)
        suffix = f" [{citation_id}]" if citation_id else ""
        candidate = (
            f"{marker}:{cluster.headline} "
            f"s={cluster.sentiment:+.2f} "
            f"n={cluster.independent_source_count}{suffix}"
        )
        if estimate_tokens("\n".join((*lines, candidate))) <= max_tokens:
            lines.append(candidate)
        else:
            omitted += 1

    if packet.sentiment.uncertainty:
        uncertainty = "不确定:" + "、".join(packet.sentiment.uncertainty)
        if estimate_tokens("\n".join((*lines, uncertainty))) <= max_tokens:
            lines.append(uncertainty)
        else:
            omitted += 1

    if omitted:
        marker = f"…省略{omitted}项"
        if estimate_tokens("\n".join((*lines, marker))) <= max_tokens:
            lines.append(marker)

    text = "\n".join(lines)
    return CompactRender(
        text=text,
        estimated_tokens=estimate_tokens(text),
        truncated=bool(omitted),
    )
