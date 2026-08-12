import { afterEach, beforeEach, expect, it } from "@jest/globals";

import {
  getAnalysisRuntimeConfig,
  getMarketRuntimeConfig,
} from "../runtimeConfig";

const originalDevDescriptor = Object.getOwnPropertyDescriptor(
  globalThis,
  "__DEV__",
);
const originalApiUrl = process.env.EXPO_PUBLIC_MARKET_API_URL;
const originalDevelopmentToken =
  process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN;
const originalGatewayToken = process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN;
const originalAnalysisUrl = process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
const originalAnalysisToken = process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN;

function setDevelopment(value: boolean) {
  Object.defineProperty(globalThis, "__DEV__", {
    configurable: true,
    value,
    writable: true,
  });
}

function restoreEnvironmentValue(
  key:
    | "EXPO_PUBLIC_MARKET_API_URL"
    | "EXPO_PUBLIC_MARKET_API_DEV_TOKEN"
    | "EXPO_PUBLIC_MARKET_GATEWAY_TOKEN"
    | "EXPO_PUBLIC_ANALYSIS_API_URL"
    | "EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN",
  value: string | undefined,
) {
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
}

beforeEach(() => {
  delete process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN;
  delete process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN;
  delete process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
  delete process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN;
});

afterEach(() => {
  if (originalDevDescriptor) {
    Object.defineProperty(globalThis, "__DEV__", originalDevDescriptor);
  } else {
    delete (globalThis as { __DEV__?: boolean }).__DEV__;
  }
  restoreEnvironmentValue("EXPO_PUBLIC_MARKET_API_URL", originalApiUrl);
  restoreEnvironmentValue(
    "EXPO_PUBLIC_MARKET_API_DEV_TOKEN",
    originalDevelopmentToken,
  );
  restoreEnvironmentValue(
    "EXPO_PUBLIC_MARKET_GATEWAY_TOKEN",
    originalGatewayToken,
  );
  restoreEnvironmentValue("EXPO_PUBLIC_ANALYSIS_API_URL", originalAnalysisUrl);
  restoreEnvironmentValue(
    "EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN",
    originalAnalysisToken,
  );
});

it("fails closed when the primary development token is present in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN = "release-secret";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "development token is forbidden in production configuration",
  );
});

it("fails closed when the compatibility gateway token is present in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = "release-secret";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "development token is forbidden in production configuration",
  );
});

it("uses the primary development token in development", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_URL = " http://127.0.0.1:8765 ";
  process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN = " primary-secret ";

  expect(getMarketRuntimeConfig()).toEqual({
    apiUrl: "http://127.0.0.1:8765",
    authorizationToken: "primary-secret",
  });
});

it("uses the compatibility gateway token in development", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_URL = " http://127.0.0.1:8765 ";
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = " development-secret ";

  expect(getMarketRuntimeConfig()).toEqual({
    apiUrl: "http://127.0.0.1:8765",
    authorizationToken: "development-secret",
  });
});

it("rejects different development token names as an explicit conflict", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN = "primary-secret";
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = "different-secret";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "configure only one market gateway development token",
  );
});

it("rejects both development token names even when their values match", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_DEV_TOKEN = "same-secret";
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = "same-secret";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "configure only one market gateway development token",
  );
});

it("reads the analysis service URL independently of the market gateway", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_URL = "http://127.0.0.1:8765";
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = " http://127.0.0.1:8788 ";
  process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN = " analysis-secret ";

  expect(getAnalysisRuntimeConfig()).toEqual({
    apiUrl: "http://127.0.0.1:8788",
    authorizationToken: "analysis-secret",
  });
});

it("reports an unconfigured analysis service as absent rather than guessing one", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_URL = "http://127.0.0.1:8765";

  expect(getAnalysisRuntimeConfig()).toEqual({ apiUrl: null });
});

it("fails closed when an analysis development token is present in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN = "release-secret";

  expect(() => getAnalysisRuntimeConfig()).toThrow(
    "development token is forbidden in production configuration",
  );
});
