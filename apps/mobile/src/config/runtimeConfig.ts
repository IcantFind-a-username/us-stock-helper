export type MarketRuntimeConfig = {
  apiUrl: string | null;
  authorizationToken?: string;
};

export type AnalysisRuntimeConfig = MarketRuntimeConfig;

export type DeviceSessionRuntimeConfig = {
  apiUrl: string | null;
  pairingRequired: boolean;
};

type RuntimeConfigInput = {
  apiUrl?: string | undefined;
  development: boolean;
  developmentToken?: string | undefined;
};

const loopbackHostnames = new Set(["127.0.0.1", "localhost", "::1"]);

function parseOrigin(apiUrl: string): URL {
  try {
    return new URL(apiUrl);
  } catch {
    throw new Error("API origin is not a valid URL");
  }
}

/**
 * A development build may talk plain HTTP because the server it talks to is on
 * the same machine or the same desk. A shipped build reaches its server across
 * the public internet, where a bearer token in cleartext is a token given away,
 * so the loopback exemption ends at the development build.
 */
function assertOriginPolicy(apiUrl: string, development: boolean): void {
  const parsed = parseOrigin(apiUrl);
  if (parsed.username !== "" || parsed.password !== "") {
    throw new Error("API origin must not carry embedded credentials");
  }
  if (parsed.protocol === "https:") return;
  if (development && parsed.protocol === "http:") return;
  throw new Error("a production build requires an https API origin");
}

function isLoopbackOrigin(apiUrl: string | null): boolean {
  if (apiUrl === null) return false;
  try {
    return loopbackHostnames.has(new URL(apiUrl).hostname);
  } catch {
    return false;
  }
}

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
  if (normalizedUrl !== null) {
    assertOriginPolicy(normalizedUrl, development);
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

export function getAnalysisRuntimeConfig(): AnalysisRuntimeConfig {
  const development = typeof __DEV__ !== "undefined" && __DEV__;

  return readRuntimeConfig({
    apiUrl: process.env.EXPO_PUBLIC_ANALYSIS_API_URL,
    development,
    developmentToken:
      process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN?.trim() || undefined,
  });
}

/**
 * Pairing is what supplies the credential when nothing else does. A development
 * loopback service authenticates nobody, and a development LAN token is already
 * a credential, so those two builds are left alone; every other build — and
 * every production build without exception — has to pair before it can ask the
 * server anything.
 */
export function getDeviceSessionRuntimeConfig(): DeviceSessionRuntimeConfig {
  const development = typeof __DEV__ !== "undefined" && __DEV__;
  const config = getAnalysisRuntimeConfig();
  const pairingRequired =
    !development ||
    (config.authorizationToken === undefined && !isLoopbackOrigin(config.apiUrl));

  return { apiUrl: config.apiUrl, pairingRequired };
}
