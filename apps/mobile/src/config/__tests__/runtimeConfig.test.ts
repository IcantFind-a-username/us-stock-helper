import { afterEach, expect, it } from "@jest/globals";

import { getMarketRuntimeConfig } from "../runtimeConfig";

const originalDevDescriptor = Object.getOwnPropertyDescriptor(
  globalThis,
  "__DEV__",
);
const originalApiUrl = process.env.EXPO_PUBLIC_MARKET_API_URL;
const originalGatewayToken = process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN;

function setDevelopment(value: boolean) {
  Object.defineProperty(globalThis, "__DEV__", {
    configurable: true,
    value,
    writable: true,
  });
}

function restoreEnvironmentValue(
  key: "EXPO_PUBLIC_MARKET_API_URL" | "EXPO_PUBLIC_MARKET_GATEWAY_TOKEN",
  value: string | undefined,
) {
  if (value === undefined) {
    delete process.env[key];
  } else {
    process.env[key] = value;
  }
}

afterEach(() => {
  if (originalDevDescriptor) {
    Object.defineProperty(globalThis, "__DEV__", originalDevDescriptor);
  } else {
    delete (globalThis as { __DEV__?: boolean }).__DEV__;
  }
  restoreEnvironmentValue("EXPO_PUBLIC_MARKET_API_URL", originalApiUrl);
  restoreEnvironmentValue(
    "EXPO_PUBLIC_MARKET_GATEWAY_TOKEN",
    originalGatewayToken,
  );
});

it("fails closed when the public gateway token is present in production", () => {
  setDevelopment(false);
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = "release-secret";

  expect(() => getMarketRuntimeConfig()).toThrow(
    "development token is forbidden in production configuration",
  );
});

it("passes the public gateway token only in development", () => {
  setDevelopment(true);
  process.env.EXPO_PUBLIC_MARKET_API_URL = " http://127.0.0.1:8765 ";
  process.env.EXPO_PUBLIC_MARKET_GATEWAY_TOKEN = " development-secret ";

  expect(getMarketRuntimeConfig()).toEqual({
    apiUrl: "http://127.0.0.1:8765",
    authorizationToken: "development-secret",
  });
});
