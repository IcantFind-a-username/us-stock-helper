import { afterEach, beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import { DeviceSessionGate } from "@/components/ui/DeviceSessionGate";
import { decisionFixture } from "@/data/__tests__/decision.fixture";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";
import type { SecureStoreBackend } from "@/security/secureStore";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";
import { useDecision } from "@/state/MarketDataProvider";

import { PairedMarketData } from "../PairedMarketData";

const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";
const pairingCode = "K7Q-4M2-88T";
const analysisOrigin = "https://api.example.com";

function credential(): DeviceCredential {
  return {
    deviceId: "6b0f2c48-9a11-4f0e-8f3d-2c7e5a1b9d40",
    deviceToken,
    expiresAt: null,
  };
}

function memoryBackend(seed?: string) {
  const values = new Map<string, string>();
  if (seed !== undefined) values.set("us-stock-helper/device-credential", seed);
  return {
    readValue: async (key: string) => values.get(key) ?? null,
    writeValue: async (key: string, value: string) => {
      values.set(key, value);
    },
    deleteValue: async (key: string) => {
      values.delete(key);
    },
  } satisfies SecureStoreBackend;
}

function jsonResponse(value: unknown, status: number) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => value,
  } as unknown as Response;
}

type Call = { url: string; init: RequestInit | undefined };

function stubNetwork({ analysisFails = false } = {}) {
  const calls: Call[] = [];
  const fetchMock = jest.fn(async (url: unknown, init?: RequestInit) => {
    const href = String(url);
    calls.push({ url: href, init });
    if (href.endsWith("/v1/device-pairings")) {
      return jsonResponse(credential(), 201);
    }
    if (href.includes("/decision")) {
      if (analysisFails) throw new TypeError("Network request failed");
      return jsonResponse(decisionFixture(), 200);
    }
    throw new TypeError(`unexpected request to ${href}`);
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return { calls, fetchMock };
}

function decisionCall(calls: Call[]) {
  return calls.find((call) => call.url.includes("/decision"));
}

function authorizationOf(call: Call | undefined) {
  const headers = (call?.init?.headers ?? {}) as Record<string, string>;
  const key = Object.keys(headers).find(
    (name) => name.toLowerCase() === "authorization",
  );
  return key === undefined ? null : headers[key];
}

function DecisionProbe() {
  const decision = useDecision("NVDA", "short");
  return <Text>{`分析状态:${decision.status}`}</Text>;
}

async function renderApp(seed?: string) {
  return render(
    <DeviceSessionProvider
      credentialStore={createDeviceCredentialStore(memoryBackend(seed))}
      pairingRequired>
      <DeviceSessionGate>
        <PairedMarketData>
          <DecisionProbe />
        </PairedMarketData>
      </DeviceSessionGate>
    </DeviceSessionProvider>,
  );
}

const originalFetch = globalThis.fetch;
const originalAnalysisUrl = process.env.EXPO_PUBLIC_ANALYSIS_API_URL;
const originalAnalysisToken = process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN;
const originalMarketUrl = process.env.EXPO_PUBLIC_MARKET_API_URL;

beforeEach(async () => {
  await AsyncStorage.clear();
  process.env.EXPO_PUBLIC_ANALYSIS_API_URL = analysisOrigin;
  delete process.env.EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN;
  delete process.env.EXPO_PUBLIC_MARKET_API_URL;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const [key, value] of [
    ["EXPO_PUBLIC_ANALYSIS_API_URL", originalAnalysisUrl],
    ["EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN", originalAnalysisToken],
    ["EXPO_PUBLIC_MARKET_API_URL", originalMarketUrl],
  ] as const) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

it("carries the paired token on the requests that follow the pairing", async () => {
  const { calls } = stubNetwork();
  const view = await renderApp();
  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());

  await fireEvent.changeText(view.getByLabelText("配对码"), pairingCode);
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(decisionCall(calls)).toBeDefined());
  // The point of pairing is the requests it authorizes; a token that stopped
  // at the Keychain would leave the app looking paired and answering nothing.
  expect(authorizationOf(decisionCall(calls))).toBe(`Bearer ${deviceToken}`);
});

it("sends no authorization on the pairing request itself", async () => {
  const { calls } = stubNetwork();
  const view = await renderApp();
  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());

  await fireEvent.changeText(view.getByLabelText("配对码"), pairingCode);
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(decisionCall(calls)).toBeDefined());
  const pairingRequest = calls.find((call) =>
    call.url.endsWith("/v1/device-pairings"),
  );
  expect(pairingRequest?.init?.method).toBe("POST");
  expect(authorizationOf(pairingRequest)).toBeNull();
});

it("submits the pairing code and nothing else about this device", async () => {
  const { calls } = stubNetwork();
  const view = await renderApp();
  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());

  await fireEvent.changeText(view.getByLabelText("配对码"), pairingCode);
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(decisionCall(calls)).toBeDefined());
  const pairingRequest = calls.find((call) =>
    call.url.endsWith("/v1/device-pairings"),
  );
  expect(JSON.parse(String(pairingRequest?.init?.body))).toEqual({
    pairingCode,
  });
});

it("tells an unpaired device apart from a paired one whose service is down", async () => {
  stubNetwork({ analysisFails: true });
  const view = await renderApp(JSON.stringify(credential()));

  await waitFor(() => expect(view.getByText("分析状态:unavailable")).toBeTruthy());
  // A paired device with a dead service must never be sent back to the pairing
  // screen: reissuing a code cannot fix a server that is not answering.
  expect(view.queryByText("未配对")).toBeNull();
  expect(view.queryByLabelText("配对码")).toBeNull();
});

it("keeps an unpaired device on the pairing screen rather than reporting an outage", async () => {
  stubNetwork({ analysisFails: true });
  const view = await renderApp();

  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());
  // Nothing behind the gate may render, so no market surface can claim the
  // service is unavailable when the truth is that nothing has been asked yet.
  expect(view.queryByText(/分析状态:/)).toBeNull();
});

it("keeps the token out of every store and log the pairing touches", async () => {
  const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map(
    (method) => jest.spyOn(console, method).mockImplementation(() => undefined),
  );
  const setItem = jest.spyOn(AsyncStorage, "setItem");
  try {
    stubNetwork();
    const view = await renderApp();
    await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());

    await fireEvent.changeText(view.getByLabelText("配对码"), pairingCode);
    await fireEvent.press(view.getByRole("button", { name: "完成配对" }));
    await waitFor(() => expect(view.getByText("分析状态:live")).toBeTruthy());

    for (const call of setItem.mock.calls) {
      expect(JSON.stringify(call)).not.toContain(deviceToken);
    }
    const entries = await AsyncStorage.multiGet(await AsyncStorage.getAllKeys());
    for (const [, value] of entries) {
      expect(value ?? "").not.toContain(deviceToken);
    }
    for (const spy of consoleSpies) {
      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain(deviceToken);
      }
    }
    expect(JSON.stringify(view.toJSON())).not.toContain(deviceToken);
  } finally {
    setItem.mockRestore();
    for (const spy of consoleSpies) spy.mockRestore();
  }
});
