export const colors = {
  background: "#EEF1F5",
  backgroundRaised: "#F7F9FC",
  card: "#FFFFFF",
  ink: "#0D1729",
  muted: "#718096",
  line: "#DCE2EB",
  navy: "#0B1424",
  navyRaised: "#111E33",
  navyLine: "#223A60",
  navyMuted: "#AABBD3",
  navyEyebrow: "#8DA2C2",
  blue: "#4285FF",
  blueBright: "#77B7FF",
  blueSoft: "#EAF2FF",
  green: "#20BF79",
  greenSoft: "#E8F8F0",
  red: "#EF5B62",
  redSoft: "#FFEDEF",
  amber: "#F4AD42",
  amberSoft: "#FFF4DF",
  purple: "#7860D9",
  purpleSoft: "#F0EDFF",
} as const;

export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 17,
  round: 32,
  pill: 999,
} as const;

export const layout = {
  /**
   * The tab bar's own `tabBarStyle.height` in `app/(tabs)/_layout.tsx`.
   *
   * Anything absolutely positioned near the bottom of the screen that has to
   * stay clear of the tab bar reads this instead of a second literal 66 that
   * could drift from the one the navigator actually renders at.
   */
  tabBarHeight: 66,
} as const;

export const shadow = {
  card: {
    shadowColor: "#23324A",
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 1,
  },
  hero: {
    shadowColor: "#0D1D37",
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.18,
    shadowRadius: 25,
    elevation: 4,
  },
} as const;
