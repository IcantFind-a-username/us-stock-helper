"""The thirteen analysis frameworks that give the council its differences.

Personality comes from the method, not from impersonating a named investor:
a framework's methodology and its declared blind spots are checkable, whereas
a claim about what a real person would say is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import HORIZONS


ADVISORY_NOTE = (
    "本视角输出是分析建议而非操作指令，受硬门否决，且幅度有上限。"
)


@dataclass(frozen=True, slots=True)
class AnalysisFramework:
    id: str
    display_name: str
    methodology: str
    blind_spots: tuple[str, ...]
    suitable_horizons: tuple[str, ...]
    advisory_note: str = ADVISORY_NOTE

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.display_name.strip():
            raise ValueError("框架 id 与名称不能为空")
        if not self.methodology.strip():
            raise ValueError("框架必须写明方法论")
        if not self.blind_spots or any(
            not item.strip() for item in self.blind_spots
        ):
            raise ValueError("框架必须写明已知盲区")
        unknown = set(self.suitable_horizons) - set(HORIZONS)
        if unknown or not self.suitable_horizons:
            raise ValueError("框架适用周期必须取自已知周期")


ANALYSIS_FRAMEWORKS: tuple[AnalysisFramework, ...] = (
    AnalysisFramework(
        id="value",
        display_name="价值锚定框架",
        methodology="用现金流与资产的可验证锚点判断价格偏离，只在偏离足够大时表态。",
        blind_spots=(
            "对故事驱动的重估反应迟钝",
            "在会计口径变更时锚点会失真",
        ),
        suitable_horizons=("swing", "long"),
    ),
    AnalysisFramework(
        id="growth",
        display_name="成长曲线框架",
        methodology="追踪收入与渗透率的加速度，判断增长斜率是否在被重新定价。",
        blind_spots=(
            "容易把一次性拉动当成趋势",
            "对估值上限缺乏约束",
        ),
        suitable_horizons=("swing", "long"),
    ),
    AnalysisFramework(
        id="macro",
        display_name="宏观周期框架",
        methodology="从利率、通胀与信用条件的方向推断资产的贴现环境如何变化。",
        blind_spots=(
            "个股特异性事件几乎被忽略",
            "宏观数据本身滞后且常被修订",
        ),
        suitable_horizons=("swing", "long"),
    ),
    AnalysisFramework(
        id="geopolitics",
        display_name="地缘与政策框架",
        methodology="识别管制、关税与合规变化对收入可达性的直接约束。",
        blind_spots=(
            "政策落地时点极难预测",
            "容易高估公开表态的执行力度",
        ),
        suitable_horizons=("short", "swing", "long"),
    ),
    AnalysisFramework(
        id="technical",
        display_name="技术结构框架",
        methodology="只读已完成的价格与量能结构，判断当前处于何种趋势阶段。",
        blind_spots=(
            "对基本面突变完全无感",
            "在低流动性下形态噪声极大",
        ),
        suitable_horizons=("short", "swing"),
    ),
    AnalysisFramework(
        id="quantitative",
        display_name="量化统计框架",
        methodology="以可回测的统计特征衡量当前状态相对历史分布的位置。",
        blind_spots=(
            "样本外结构断裂时失效",
            "无法解释新出现的因果机制",
        ),
        suitable_horizons=("short", "swing"),
    ),
    AnalysisFramework(
        id="risk",
        display_name="风险控制框架",
        methodology="先量化最坏情形的损失路径，再判断当前赔率是否值得承担。",
        blind_spots=(
            "系统性低估上行空间",
            "在低波动期会显得过度保守",
        ),
        suitable_horizons=("short", "swing", "long"),
    ),
    AnalysisFramework(
        id="contrarian",
        display_name="逆向共识框架",
        methodology="度量一致预期的拥挤程度，在共识与证据背离处寻找错价。",
        blind_spots=(
            "容易过早站到趋势对面",
            "把持续的强趋势误判为拥挤",
        ),
        suitable_horizons=("swing", "long"),
    ),
    AnalysisFramework(
        id="quality",
        display_name="商业质量框架",
        methodology="考察护城河、定价权与资本回报的持续性，判断优势是否在变化。",
        blind_spots=(
            "对周期性拐点反应慢",
            "倾向于为确定性支付过高价格",
        ),
        suitable_horizons=("long",),
    ),
    AnalysisFramework(
        id="catalyst",
        display_name="事件催化框架",
        methodology="把已发生事件拆成可验证的时间表，判断哪一步尚未被定价。",
        blind_spots=(
            "事件延期时判断整体失效",
            "对慢变量与长期趋势不敏感",
        ),
        suitable_horizons=("short", "swing"),
    ),
    AnalysisFramework(
        id="liquidity",
        display_name="资金流与流动性框架",
        methodology="观察成交结构与可得流动性，判断价格变动能否被真实资金承接。",
        blind_spots=(
            "资金数据披露稀疏且滞后",
            "无法区分被动配置与主动观点",
        ),
        suitable_horizons=("short", "swing"),
    ),
    AnalysisFramework(
        id="tail_risk",
        display_name="尾部风险框架",
        methodology="专门为低概率高冲击情形定价，检查敞口是否具备凸性。",
        blind_spots=(
            "长期看会持续付出保护成本",
            "对常态区间的判断价值有限",
        ),
        suitable_horizons=("short", "swing", "long"),
    ),
    AnalysisFramework(
        id="supply_chain",
        display_name="产业链传导框架",
        methodology="沿上下游追踪订单、产能与库存的传导链条，定位冲击的落点。",
        blind_spots=(
            "链条数据多为二手且口径不一",
            "传导时滞难以精确到季度",
        ),
        suitable_horizons=("swing", "long"),
    ),
)


_BY_ID = {framework.id: framework for framework in ANALYSIS_FRAMEWORKS}


def framework_by_id(framework_id: str) -> AnalysisFramework:
    try:
        return _BY_ID[framework_id]
    except KeyError as exc:
        raise KeyError(f"未知分析框架: {framework_id}") from exc


def select_frameworks(
    *, horizon: str, maximum: int
) -> tuple[AnalysisFramework, ...]:
    if maximum < 1:
        raise ValueError("maximum 必须为正")
    if horizon not in HORIZONS:
        raise ValueError(f"horizon 必须是 {HORIZONS} 之一")
    # Declaration order is the tie-break so the same request always convenes
    # the same seats; a shuffled council is not comparable across runs.
    eligible = [
        framework
        for framework in ANALYSIS_FRAMEWORKS
        if horizon in framework.suitable_horizons
    ]
    return tuple(eligible[:maximum])
