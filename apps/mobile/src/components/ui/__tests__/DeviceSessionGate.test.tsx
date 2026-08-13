import { expect, it } from "@jest/globals";
import { render, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import type { PairingClient } from "@/data/pairingClient";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";
import type { SecureStoreBackend } from "@/security/secureStore";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";

import { DeviceSessionGate } from "../DeviceSessionGate";

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
