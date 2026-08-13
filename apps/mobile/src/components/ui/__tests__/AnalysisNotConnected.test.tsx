import { describe, expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { AnalysisNotConnected } from "../AnalysisNotConnected";

describe("the placeholder that stands in for an unconnected surface", () => {
  it("names what is missing instead of blaming an analysis service that is live", async () => {
    const view = await render(
      <AnalysisNotConnected
        missing="提醒服务尚未部署：分析接口只按标的按需回答，没有提醒或推送路由。"
        surface="提醒"
      />,
    );

    expect(view.getByText(/提醒服务尚未部署/)).toBeTruthy();
    // The old copy said the real analysis service had not shipped. It has, so
    // that sentence was pointing the reader at the wrong missing piece.
    expect(view.queryByText(/真实分析服务上线前/)).toBeNull();
  });

  it("promises the surface stays empty rather than falling back to fixtures", async () => {
    const view = await render(
      <AnalysisNotConnected missing="等待 X" surface="Y" />,
    );

    expect(view.getByTestId("analysis-not-connected")).toHaveTextContent(
      /不会用演示内容顶替/,
    );
  });
});
