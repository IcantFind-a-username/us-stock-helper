import { afterEach, beforeEach, expect, it } from "@jest/globals";

import {
  getAnalysisRuntimeConfig,
  getDeviceSessionRuntimeConfig,
  getInitialDemoMode,
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
const originalInitialDemoMode = process.env.EXPO_PUBLIC_INITIAL_DEMO_MODE;

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
    | "EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN"
    | "EXPO_PUBLIC_INITIAL_DEMO_MODE",
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
  delete process.env.EXPO_PUBLIC_INITIAL_DEMO_MODE;
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
  restoreEnvironmentValue(
    "EXPO_PUBLIC_INITIAL_DEMO_MODE",
    originalInitialDemoMode,
  );
});

it("can start directly in demo mode only in a development build", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_INITIAL_DEMO_MODE = " true ";

  expect(getInitialDemoMode()).toBe(true);

  setDevelopment(false);
  expect(getInitialDemoMode()).toBe(false);
});

it("rejects a misspelled development demo-mode flag", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_INITIAL_DEMO_MODE = "enabled";

  expect(() => getInitialDemoMode()).toThrow(
    "EXPO_PUBLIC_INITIAL_DEMO_MODE must be true or false",
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

it("rejects a plain-HTTP analysis origin in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://analysis.example.com";

  expect(() => getAnalysisRuntimeConfig()).toThrow(
    "a production build requires an https API origin",
  );
});

it("rejects a loopback analysis origin in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://127.0.0.1:8788";

  // The loopback exemption exists only because a development machine serves the
  // gateway over the loopback interface; a shipped build has no such server.
  expect(() => getAnalysisRuntimeConfig()).toThrow(
    "a production build requires an https API origin",
  );
});

it("accepts an HTTPS cloud analysis origin in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = " https://api.example.com ";

  expect(getAnalysisRuntimeConfig()).toEqual({
    apiUrl: "https://api.example.com",
  });
});

it("rejects a production origin that carries embedded credentials", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "https://user:secret@api.example.com";

  expect(() => getAnalysisRuntimeConfig()).toThrow(
    "API origin must not carry embedded credentials",
  );
});

it("rejects an unparseable production origin instead of treating it as absent", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "api.example.com";

  expect(() => getAnalysisRuntimeConfig()).toThrow("API origin is not a valid URL");
});

it("rejects a plain-HTTP market origin in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_MARKET_API_URL = "http://192.168.1.20:8765";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "a production build requires an https API origin",
  );
});

it("still allows a plain-HTTP loopback origin in development", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://127.0.0.1:8788";

  expect(getAnalysisRuntimeConfig()).toEqual({ apiUrl: "http://127.0.0.1:8788" });
});

it("requires pairing in a production build", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "https://api.example.com";

  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: "https://api.example.com",
    pairingRequired: true,
  });
});

it("requires pairing in production even when the origin is a loopback tunnel", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "https://localhost:8788";

  // A shipped build reached through a local tunnel is still a shipped build:
  // nothing about the hostname makes it a machine the developer controls.
  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: "https://localhost:8788",
    pairingRequired: true,
  });
});

it("does not require pairing against a development loopback service", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://127.0.0.1:8788";

  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: "http://127.0.0.1:8788",
    pairingRequired: false,
  });
});

it("does not require pairing when a development LAN token is configured", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://192.168.1.20:8788";
  process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN = "lan-secret";

  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: "http://192.168.1.20:8788",
    pairingRequired: false,
  });
});

it("requires pairing for a development LAN service that has no token", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = "http://192.168.1.20:8788";

  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: "http://192.168.1.20:8788",
    pairingRequired: true,
  });
});

it("requires pairing when no analysis origin is configured at all", () => {
  setDevelopment(false);

  // An absent origin is reported as null rather than guessed, and the device is
  // still unpaired: the screen has to say so instead of rendering nothing.
  expect(getDeviceSessionRuntimeConfig()).toEqual({
    apiUrl: null,
    pairingRequired: true,
  });
});
