export type MarketRuntimeConfig = {
  apiUrl: string | null;
  authorizationToken?: string;
};

type RuntimeConfigInput = {
  apiUrl?: string | undefined;
  development: boolean;
  developmentToken?: string | undefined;
};

export function readRuntimeConfig({
  apiUrl,
  development,
  developmentToken,
}: RuntimeConfigInput): MarketRuntimeConfig {
  const normalizedUrl = apiUrl?.trim() || null;
  const normalizedToken = developmentToken?.trim() || undefined;

  if (!development && normalizedToken) {
    throw new Error("development token is forbidden in production configuration");
  }

  return {
    apiUrl: normalizedUrl,
    ...(development && normalizedToken
      ? { authorizationToken: normalizedToken }
      : {}),
  };
}

export function getMarketRuntimeConfig(): MarketRuntimeConfig {
  const development = typeof __DEV__ !== "undefined" && __DEV__;
  const primaryToken =
    process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN?.trim() || undefined;
  const compatibilityToken =
    process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN?.trim() || undefined;

  if (primaryToken && compatibilityToken) {
    throw new Error("configure only one market gateway development token");
  }

  return readRuntimeConfig({
    apiUrl: process.env.EXPO_PUBLIC_MARKET_API_URL,
    development,
    developmentToken: primaryToken ?? compatibilityToken,
  });
}
