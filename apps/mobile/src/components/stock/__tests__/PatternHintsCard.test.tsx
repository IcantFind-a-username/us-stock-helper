import { expect, it, describe } from "@jest/globals";
import { render, userEvent } from "@testing-library/react-native";

import type { PatternShapeDetection } from "@/domain/models";

import { PatternHintsCard } from "../PatternHintsCard";

const BANNED_VERBS = ["买入", "卖出", "加仓", "抄底", "梭哈"];

function unavailableDetection(
  detector: PatternShapeDetection["detector"],
  minimumWindow: number,
): PatternShapeDetection {
  return {
    detector,
    minimumWindow,
    sampleSize: 2,
    qualityStatus: "unavailable",
    missingReason: `完整K线不足 ${minimumWindow} 根`,
    methodVersion: "patterns-shapes-v1",
    signals: [],
  };
}

function liveEmptyDetection(
  detector: PatternShapeDetection["detector"],
  minimumWindow: number,
): PatternShapeDetection {
  return {
    detector,
    minimumWindow,
    sampleSize: 20,
    qualityStatus: "live",
    missingReason: null,
    methodVersion: "patterns-shapes-v1",
    signals: [],
  };
}

function confirmedDoubleBottomDetection(): PatternShapeDetection {
  return {
    detector: "double_extreme",
    minimumWindow: 7,
    sampleSize: 8,
    qualityStatus: "live",
    missingReason: null,
    methodVersion: "patterns-shapes-v1",
    signals: [
      {
        kind: "double_bottom",
        name: "W底",
        status: "confirmed",
        direction: "bullish",
        bars: [
          { index: 1, closedAt: "2026-07-25T15:50:00.000Z" },
          { index: 5, closedAt: "2026-07-25T15:54:00.000Z" },
          { index: 7, closedAt: "2026-07-25T15:56:00.000Z" },
        ],
        anchorIndex: 5,
        eventIndex: 7,
        invalidation: "收盘跌破颈线 104.00",
        explanation: "两个低点幅度接近；颈线 104.00。",
        reading: {
          summary:
            "W底已确认：价格两次探底后，收盘站上了颈线，短线动能转强的信号出现了。",
          detail:
            "两个相近的低点之间夹着一个反弹高点，即颈线；收盘价升破颈线视为形态确认。",
          honesty: "历史胜率待回测",
        },
        methodVersion: "patterns-shapes-v1",
      },
    ],
  };
}

function formingFractalDetection(): PatternShapeDetection {
  return {
    detector: "fractal",
    minimumWindow: 3,
    sampleSize: 5,
    qualityStatus: "live",
    missingReason: null,
    methodVersion: "patterns-shapes-v1",
    signals: [
      {
        kind: "fractal_bottom",
        name: "底分型",
        status: "confirmed",
        direction: "bullish",
        bars: [
          { index: 2, closedAt: "2026-07-25T15:50:00.000Z" },
          { index: 3, closedAt: "2026-07-25T15:52:00.000Z" },
          { index: 4, closedAt: "2026-07-25T15:54:00.000Z" },
        ],
        anchorIndex: 3,
        eventIndex: 4,
        invalidation: "收盘价跌破分型低点 90.00",
        explanation: "中间K线的最低价同时低于左右两根K线。",
        reading: {
          summary:
            "底分型：连续下跌后，中间这根K线的最低点比两边都低，又收回来了——短线卖压可能衰竭的第一个迹象。",
          detail: "第三根K线收盘后才能确认。",
          honesty: "历史胜率待回测",
        },
        methodVersion: "patterns-shapes-v1",
      },
    ],
  };
}

describe("PatternHintsCard", () => {
  it("lists the confirmed and invalidated status distinctly", async () => {
    const view = await render(
      <PatternHintsCard
        detections={[confirmedDoubleBottomDetection(), formingFractalDetection()]}
      />,
    );

    expect(view.getByText("W底")).toBeTruthy();
    expect(view.getByText("底分型")).toBeTruthy();
    expect(view.getAllByText("已确认").length).toBe(2);
  });

  it("expands a signal's three-layer reading on tap", async () => {
    const view = await render(
      <PatternHintsCard detections={[confirmedDoubleBottomDetection()]} />,
    );

    expect(view.queryByText(/两个相近的低点/)).toBeNull();
    await userEvent.setup().press(view.getByLabelText(/白话解读/));
    expect(view.getByText(/两个相近的低点/)).toBeTruthy();
    expect(view.getByText(/收盘跌破颈线 104.00/)).toBeTruthy();
    expect(view.getByText(/历史胜率待回测/)).toBeTruthy();
  });

  it("discloses insufficient data honestly instead of a false empty read", async () => {
    const view = await render(
      <PatternHintsCard
        detections={[unavailableDetection("fractal", 3), unavailableDetection("double_extreme", 7)]}
      />,
    );

    expect(view.getByText(/完整K线数量不足/)).toBeTruthy();
  });

  it("reports a genuine zero as no current detections, not an error", async () => {
    const view = await render(
      <PatternHintsCard
        detections={[liveEmptyDetection("fractal", 3), liveEmptyDetection("double_extreme", 7)]}
      />,
    );

    expect(view.getByText(/当前没有识别到形态/)).toBeTruthy();
  });

  it("never renders a banned action verb in any reading layer", async () => {
    const view = await render(
      <PatternHintsCard
        detections={[confirmedDoubleBottomDetection(), formingFractalDetection()]}
      />,
    );
    const user = userEvent.setup();
    const labels = view.getAllByLabelText(/白话解读/);
    for (const label of labels) {
      await user.press(label);
    }

    const text = view.toJSON();
    const serialized = JSON.stringify(text);
    for (const verb of BANNED_VERBS) {
      expect(serialized.includes(verb)).toBe(false);
    }
  });
});
