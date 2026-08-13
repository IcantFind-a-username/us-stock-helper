"""Prompts. The evidence-only rule lives here and nowhere else."""

from __future__ import annotations

from typing import Sequence

from .evidence import EvidencePacket
from .frameworks import ADVISORY_NOTE, AnalysisFramework


EVIDENCE_ONLY_SYSTEM_PROMPT = """你是美股信息的跨源解读助手。你的输出只用于分析，不构成任何操作指令。

硬性约束：
1. 你只能基于给定证据包中的条目推理。证据包之外的事实、数字、公司、机构、时间一律不得出现。
2. 证据无法回答的问题，直接说不知道，并写进 unknowns；绝不用常识、记忆或推测补齐。
3. 每一条结论都必须在 citations 里至少给出一个 evidence_id，并从该条目原文逐字复制一段作为 quote。改写过的引文视为无效。
4. 不要自己写链接。链接由系统按 evidence_id 从冻结证据包解析，你写的链接会被丢弃。
5. 不要给出任何交易动作、仓位大小或收益承诺。
6. 必须主动寻找反证；找不到反证时，在 unknowns 中写明这一点。
7. 时间以证据条目自带的 available_at 与 received_at 为准，不要自行推算"最近""刚刚"这类相对时间。
"""


def build_council_system_prompt(
    frameworks: Sequence[AnalysisFramework],
) -> str:
    if not frameworks:
        raise ValueError("顾问委员会至少需要一个席位")
    lines = [
        EVIDENCE_ONLY_SYSTEM_PROMPT,
        "",
        "顾问委员会席位。每个席位用一种分析框架独立表态，彼此不得互相附和：",
    ]
    for framework in frameworks:
        lines.append(
            f"- {framework.id}（{framework.display_name}）"
            f" 方法论：{framework.methodology}"
            f" 已知盲区：{'；'.join(framework.blind_spots)}"
        )
    lines.extend(
        (
            "",
            "每个席位必须在 blind_spot_note 里写明本次判断受自身盲区影响的具体位置。",
            "席位之间出现分歧时如实保留分歧，不要合并成一个折中说法。",
            ADVISORY_NOTE,
        )
    )
    return "\n".join(lines)


def build_news_user_message(packet: EvidencePacket) -> str:
    return "\n".join(
        (
            "以下是冻结的证据包，只允许使用其中内容：",
            "",
            packet.render(),
            "请给出：跨源解读（几家信源、是否互相独立、是否互相印证）、",
            "对该标的的投资影响、以及证据回答不了的问题。",
        )
    )


def build_council_user_message(
    packet: EvidencePacket,
    *,
    baseline_score: float,
    baseline_direction: str,
) -> str:
    return "\n".join(
        (
            "以下是冻结的证据包，只允许使用其中内容：",
            "",
            packet.render(),
            "确定性代码已给出的客观基线（仅供参考，不要试图改写它）：",
            f"- 基线分数: {baseline_score}",
            f"- 基线方向: {baseline_direction}",
            "",
            "请让每个席位给出立场、结论与反证。结论必须逐条带上 citations。",
        )
    )
