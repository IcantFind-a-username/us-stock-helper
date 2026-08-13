import type { NewsClaimStatus } from "@/domain/news";
import { useColorScheme } from "@/hooks/use-color-scheme";
import { colors } from "@/theme/tokens";

type Chip = { background: string; text: string };

export type NewsPalette = {
  surface: string;
  surfaceInset: string;
  ink: string;
  muted: string;
  line: string;
  accent: string;
  notice: string;
  noticeSurface: string;
  claimStatus: Record<NewsClaimStatus, Chip>;
};

/**
 * The soft token backgrounds are near-white, so a dark screen cannot reuse
 * them; it keeps the same hues as foreground on the navy surfaces instead.
 */
const palettes: Record<"light" | "dark", NewsPalette> = {
  light: {
    surface: colors.card,
    surfaceInset: colors.backgroundRaised,
    ink: colors.ink,
    muted: colors.muted,
    line: colors.line,
    accent: colors.blue,
    notice: colors.amber,
    noticeSurface: colors.amberSoft,
    claimStatus: {
      verified: { background: colors.greenSoft, text: colors.green },
      reported: { background: colors.blueSoft, text: colors.blue },
      rumor: { background: colors.amberSoft, text: colors.amber },
    },
  },
  dark: {
    surface: colors.navyRaised,
    surfaceInset: colors.navy,
    ink: colors.card,
    muted: colors.navyMuted,
    line: colors.navyLine,
    accent: colors.blueBright,
    notice: colors.amber,
    noticeSurface: colors.navyLine,
    claimStatus: {
      verified: { background: colors.navyLine, text: colors.green },
      reported: { background: colors.navyLine, text: colors.blueBright },
      rumor: { background: colors.navyLine, text: colors.amber },
    },
  },
};

export function useNewsPalette(): NewsPalette {
  return useColorScheme() === "dark" ? palettes.dark : palettes.light;
}
