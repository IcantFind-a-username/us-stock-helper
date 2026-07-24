import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { colors } from "@/theme/tokens";

type ScoreRingProps = {
  score: number;
  size?: number;
  strokeWidth?: number;
};

export const clampScore = (score: number) =>
  Math.min(100, Math.max(0, score));

export function ScoreRing({
  score,
  size = 54,
  strokeWidth = 6,
}: ScoreRingProps) {
  const normalized = clampScore(score);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = circumference * (normalized / 100);

  return (
    <View
      accessibilityLabel={`市场评分 ${normalized}`}
      style={[styles.container, { height: size, width: size }]}>
      <Svg height={size} width={size}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          fill={colors.navyRaised}
          r={radius}
          stroke="#243653"
          strokeWidth={strokeWidth}
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          fill="none"
          r={radius}
          rotation="-90"
          origin={`${size / 2}, ${size / 2}`}
          stroke={colors.green}
          strokeDasharray={`${progress} ${circumference - progress}`}
          strokeLinecap="round"
          strokeWidth={strokeWidth}
        />
      </Svg>
      <Text style={styles.score}>{normalized}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", justifyContent: "center" },
  score: {
    color: "#EFF6FF",
    fontSize: 15,
    fontVariant: ["tabular-nums"],
    fontWeight: "800",
    position: "absolute",
  },
});
