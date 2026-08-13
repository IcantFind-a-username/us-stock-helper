import { expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { PairingError, type PairingClient } from "@/data/pairingClient";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";
import type { SecureStoreBackend } from "@/security/secureStore";
import { DeviceSessionProvider } from "@/state/DeviceSessionProvider";

import { PairDeviceScreen } from "../PairDeviceScreen";

const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";

function credential(): DeviceCredential {
  return {
    deviceId: "6b0f2c48-9a11-4f0e-8f3d-2c7e5a1b9d40",
    deviceToken,
    expiresAt: "2026-11-10T00:00:00.000Z",
  };
}

function memoryBackend() {
  const values = new Map<string, string>();
  const backend: SecureStoreBackend = {
    readValue: async (key) => values.get(key) ?? null,
    writeValue: async (key, value) => {
      values.set(key, value);
    },
    deleteValue: async (key) => {
      values.delete(key);
    },
  };
  return backend;
}

async function renderPairing(pairingClient: PairingClient) {
  const view = await render(
    <DeviceSessionProvider
      credentialStore={createDeviceCredentialStore(memoryBackend())}
      deviceName="iPhone"
      pairingClient={pairingClient}>
      <PairDeviceScreen />
    </DeviceSessionProvider>,
  );
  await waitFor(() => expect(view.getByText("未配对")).toBeTruthy());
  return view;
}

function acceptingClient(): PairingClient {
  return { pair: async () => credential() };
}

it("states that the device is not paired instead of showing an empty screen", async () => {
  const view = await renderPairing(acceptingClient());

  expect(view.getByText("未配对")).toBeTruthy();
  expect(view.getByText(/未配对前不会显示任何行情或结论/)).toBeTruthy();
  expect(view.getByLabelText("配对码")).toBeTruthy();
});

it("asks for a code before spending a server attempt on an empty one", async () => {
  const pair = jest.fn(async () => credential());
  const view = await renderPairing({ pair } as unknown as PairingClient);

  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(view.getByText("请输入配对码")).toBeTruthy());
  expect(pair).not.toHaveBeenCalled();
});

it("confirms a completed pairing without ever printing the token", async () => {
  const view = await renderPairing(acceptingClient());

  await fireEvent.changeText(view.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(view.getByText("已配对")).toBeTruthy());
  expect(view.queryByText(deviceToken)).toBeNull();
  expect(JSON.stringify(view.toJSON())).not.toContain(deviceToken);
});

it("tells a wrong code apart from an expired one in the copy it shows", async () => {
  const wrongView = await renderPairing({
    pair: async () => {
      throw new PairingError("invalid-code", "rejected");
    },
  });
  await fireEvent.changeText(wrongView.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(wrongView.getByRole("button", { name: "完成配对" }));
  await waitFor(() => expect(wrongView.getByText("配对码不正确")).toBeTruthy());

  const expiredView = await renderPairing({
    pair: async () => {
      throw new PairingError("expired-code", "rejected");
    },
  });
  await fireEvent.changeText(expiredView.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(expiredView.getByRole("button", { name: "完成配对" }));
  await waitFor(() => expect(expiredView.getByText("配对码已过期")).toBeTruthy());
});

it("shows the rate limiter's own wording, including the wait it stated", async () => {
  const view = await renderPairing({
    pair: async () => {
      throw new PairingError("rate-limited", "locked out", {
        retryAfterSeconds: 900,
      });
    },
  });

  await fireEvent.changeText(view.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(view.getByText("尝试次数过多")).toBeTruthy());
  expect(view.getByText(/900 秒/)).toBeTruthy();
});

it("shows no English enum name when a failure is displayed", async () => {
  const view = await renderPairing({
    pair: async () => {
      throw new PairingError("code-used", "already consumed");
    },
  });

  await fireEvent.changeText(view.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(view.getByText("配对码已被使用")).toBeTruthy());
  expect(JSON.stringify(view.toJSON())).not.toContain("code-used");
});

it("keeps the device stated as unpaired while an exchange is in flight", async () => {
  let release: (value: DeviceCredential) => void = () => undefined;
  const view = await renderPairing({
    pair: () =>
      new Promise<DeviceCredential>((resolve) => {
        release = resolve;
      }),
  });

  await fireEvent.changeText(view.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));

  await waitFor(() => expect(view.getByText("配对中")).toBeTruthy());
  expect(view.getByRole("button", { name: "完成配对" }).props.accessibilityState)
    .toMatchObject({ disabled: true });

  release(credential());
  await waitFor(() => expect(view.getByText("已配对")).toBeTruthy());
});
