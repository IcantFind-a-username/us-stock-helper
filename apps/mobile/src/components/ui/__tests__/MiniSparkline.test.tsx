import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";
import { Platform } from "react-native";

import { MiniSparkline } from "../MiniSparkline";

function findPathData(node: unknown): string | undefined {
  if (!node || typeof node !== "object") return undefined;

  const { children, props } = node as {
    children?: unknown[];
    props?: { d?: unknown };
  };

  if (typeof props?.d === "string") return props.d;

  return children?.map(findPathData).find((pathData) => pathData !== undefined);
}

it("hides the decorative sparkline from native accessibility services", async () => {
  expect(Platform.OS).not.toBe("web");

  const view = await render(<MiniSparkline direction="bullish" />);
  const sparkline = view.root;
  if (!sparkline) throw new Error("Expected MiniSparkline root");

  expect(sparkline.props.accessibilityElementsHidden).toBe(true);
  expect(sparkline.props.importantForAccessibility).toBe("no-hide-descendants");
  expect(findPathData(view.toJSON())).toBe(
    "M1 18 L10 15 L19 16 L28 9 L37 12 L46 5 L55 8 L64 2",
  );
});
