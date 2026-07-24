import { expect, it, jest } from "@jest/globals";
import { fireEvent, render } from "@testing-library/react-native";

import { AgentScreen } from "../AgentScreen";

const mockPush = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

it("keeps the objective-first response order and exposes safe local actions", async () => {
  const view = await render(<AgentScreen />);

  const titles = view
    .getAllByTestId("conversation-section-title")
    .map((node) => node.props.children);
  expect(titles).toEqual([
    "客观结论",
    "证据",
    "最强反证",
    "缺失信息与不确定性",
    "个性化风险场景",
    "引用",
  ]);
  expect(view.getByText("演示数据 · 非实时行情")).toBeTruthy();
  expect(view.getByText(/公开理念的风格模拟，不代表真人背书/)).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "为什么短线不追高？" }));
  expect(view.getAllByText("为什么短线不追高？")).toHaveLength(2);
  expect(view.getAllByText(/确定性演示回复/)).toHaveLength(2);
  expect(view.getByText(/不会因为你的高回报偏好而上调客观置信度/)).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "查看本轮引用" }));
  expect(view.getByText("本轮证据与引用")).toBeTruthy();
  expect(view.getByText("演示：NVDA 机构持仓与财报快照")).toBeTruthy();
  await fireEvent.press(view.getByRole("button", { name: "关闭本轮证据与引用" }));

  await fireEvent.press(view.getByRole("button", { name: "申请补充调查" }));
  expect(view.getByText("已创建演示调查请求；未向外部服务发送。")).toBeTruthy();

  await fireEvent.press(view.getByRole("button", { name: "进入 13 风格顾问会诊" }));
  expect(mockPush).toHaveBeenLastCalledWith({
    pathname: "/stocks/[symbol]/advisers",
    params: { symbol: "NVDA" },
  });
});
