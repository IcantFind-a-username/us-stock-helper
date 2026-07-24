import type { Direction } from "@/domain/models";
import { colors } from "@/theme/tokens";
import Svg, { Path } from "react-native-svg";

type MiniSparklineProps = {
  direction: Direction;
  width?: number;
  height?: number;
};

const paths: Record<Direction, string> = {
  bullish: "M1 18 L10 15 L19 16 L28 9 L37 12 L46 5 L55 8 L64 2",
  neutral: "M1 12 L10 10 L19 13 L28 9 L37 12 L46 10 L55 11 L64 8",
  bearish: "M1 3 L10 7 L19 5 L28 12 L37 9 L46 16 L55 14 L64 20",
};

const tones: Record<Direction, string> = {
  bullish: colors.green,
  neutral: colors.muted,
  bearish: colors.red,
};

export function MiniSparkline({
  direction,
  width = 66,
  height = 22,
}: MiniSparklineProps) {
  return (
    <Svg
      accessibilityElementsHidden
      height={height}
      importantForAccessibility="no-hide-descendants"
      viewBox="0 0 66 22"
      width={width}>
      <Path
        d={paths[direction]}
        fill="none"
        stroke={tones[direction]}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
      />
    </Svg>
  );
}
