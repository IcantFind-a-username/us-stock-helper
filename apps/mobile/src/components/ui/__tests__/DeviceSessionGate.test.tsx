import { expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { StyleSheet, Text } from "react-native";

import type { PairingClient } from "@/data/pairingClient";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";
import type { SecureStoreBackend } from "@/security/secureStore";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";
import { layout, spacing } from "@/theme/tokens";

import { DeviceSessionGate } from "../DeviceSessionGate";

const mockSafeAreaInsets = jest.fn(() => ({ bottom: 0, left: 0, right: 0, top: 0 }));
jest.mock("react-native-safe-area-context", () => ({
  ...(jest.requireActual("react-native-safe-area-context") as object),
  useSafeAreaInsets: () => mockSafeAreaInsets(),
}));

const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";

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

const idleClient: PairingClient = { pair: async () => credential() };

async function renderGate({
  pairingRequired,
  seed,
}: {
  pairingRequired: boolean;
  seed?: string;
}) {
  return render(
    <DeviceSessionProvider
      credentialStore={createDeviceCredentialStore(memoryBackend(seed))}
      pairingClient={idleClient}
      pairingRequired={pairingRequired}>
      <DeviceSessionGate>
        <Text>市场观察</Text>
      </DeviceSessionGate>
    </DeviceSessionProvider>,
  );
}

it("replaces the app with the pairing screen while the device is unpaired", async () => {
  const view = await renderGate({ pairingRequired: true });

  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());
  expect(view.queryByText("市场观察")).toBeNull();
});

it("hands the app over once the device is paired", async () => {
  const view = await renderGate({
    pairingRequired: true,
    seed: JSON.stringify(credential()),
  });

  await waitFor(() => expect(view.getByText("市场观察")).toBeTruthy());
  expect(view.queryByText("未配对")).toBeNull();
});

it("leaves a development build that needs no pairing alone", async () => {
  const view = await renderGate({ pairingRequired: false });

  await waitFor(() => expect(view.getByText("市场观察")).toBeTruthy());
});

it("keeps a way back to the pairing screen reachable while paired, so a server-side revocation is not a dead end", async () => {
  // Nothing behind this gate ever calls reportRevoked() or forgetDevice(): a
  // device the operator revokes stays "paired" here forever, and every
  // screen downstream would answer auth-required with no way to act on it.
  // This is the escape hatch that makes the recovery those two functions
  // were built for actually reachable, instead of code only tests call.
  const view = await renderGate({
    pairingRequired: true,
    seed: JSON.stringify(credential()),
  });

  await waitFor(() => expect(view.getByText("市场观察")).toBeTruthy());

  await fireEvent.press(view.getByLabelText("重新配对设备"));

  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());
  expect(view.queryByText("市场观察")).toBeNull();
});

it("says it is still checking rather than flashing an unpaired screen", async () => {
  const pendingBackend: SecureStoreBackend = {
    readValue: () => new Promise<string | null>(() => undefined),
    writeValue: async () => undefined,
    deleteValue: async () => undefined,
  };
  const view = await render(
    <DeviceSessionProvider
      credentialStore={createDeviceCredentialStore(pendingBackend)}
      pairingClient={idleClient}
      pairingRequired>
      <DeviceSessionGate>
        <Text>市场观察</Text>
      </DeviceSessionGate>
    </DeviceSessionProvider>,
  );

  // Until the Keychain has answered, claiming "unpaired" would be a guess and
  // claiming "paired" would be worse; the app stays behind the gate meanwhile.
  expect(view.getByText("正在检查配对状态")).toBeTruthy();
  expect(view.queryByText("未配对")).toBeNull();
  expect(view.queryByText("市场观察")).toBeNull();
});

it("keeps the recovery pill clear of the tab bar band on a home-indicator phone", async () => {
  // The tab bar renders at `layout.tabBarHeight`, on top of whatever safe-area
  // inset the device itself adds below it. A pill whose `bottom` offset does
  // not clear both is reachable from inside that band — on the five-tab bar
  // that is 复盘 and Agent's own corner, so a mis-tap there wipes a valid
  // pairing credential instead of hitting the tab underneath it.
  mockSafeAreaInsets.mockReturnValue({ bottom: 34, left: 0, right: 0, top: 47 });
  const view = await renderGate({
    pairingRequired: true,
    seed: JSON.stringify(credential()),
  });

  await waitFor(() => expect(view.getByText("市场观察")).toBeTruthy());

  const pill = view.getByLabelText("重新配对设备");
  const style = StyleSheet.flatten(pill.props.style) as {
    bottom?: number;
    minHeight?: number;
    position?: string;
  };

  expect(style.position).toBe("absolute");
  // The non-overlap constraint pixel tests cannot express directly: the pill
  // must clear the tab bar's own height plus whatever the device's home
  // indicator adds beneath it, on every phone, not just the one with no
  // inset a naive fixed offset happens to still clear.
  expect(style.bottom).toBeGreaterThanOrEqual(layout.tabBarHeight + 34);
  // A 44pt target is the platform's own minimum tappable size.
  expect(style.minHeight).toBeGreaterThanOrEqual(44);
});

it("keeps the recovery pill clear of the tab bar band on a home-button phone with no inset", async () => {
  mockSafeAreaInsets.mockReturnValue({ bottom: 0, left: 0, right: 0, top: 20 });
  const view = await renderGate({
    pairingRequired: true,
    seed: JSON.stringify(credential()),
  });

  await waitFor(() => expect(view.getByText("市场观察")).toBeTruthy());

  const pill = view.getByLabelText("重新配对设备");
  const style = StyleSheet.flatten(pill.props.style) as { bottom?: number };

  // Zero inset is not licence to creep back into the tab bar's own band.
  expect(style.bottom).toBeGreaterThanOrEqual(layout.tabBarHeight);
});
