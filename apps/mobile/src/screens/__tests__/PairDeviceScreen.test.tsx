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

async function failWith(error: PairingError) {
  const view = await renderPairing({
    pair: async () => {
      throw error;
    },
  });
  await fireEvent.changeText(view.getByLabelText("配对码"), "K7Q-4M2-88T");
  await fireEvent.press(view.getByRole("button", { name: "完成配对" }));
  await waitFor(() => expect(view.getByTestId("pairing-failure")).toBeTruthy());
  return view;
}

it("puts a different and separately actionable screen behind each way pairing fails", async () => {
  const shown: string[] = [];
  for (const error of [
    new PairingError("code-refused", "refused"),
    new PairingError("rate-limited", "throttled", { retryAfterSeconds: 900 }),
    new PairingError("pairing-unsupported", "no endpoint"),
    new PairingError("client-not-allowed", "blocked"),
    new PairingError("offline", "unreachable"),
  ]) {
    const view = await failWith(error);
    // Every run types the same code into the same unpaired screen, so the only
    // thing that can differ between these trees is the failure the card names.
    shown.push(JSON.stringify(view.toJSON()));
  }

  expect(new Set(shown).size).toBe(shown.length);
});

it("does not send a reader back to the keyboard when the server has no pairing endpoint", async () => {
  const view = await failWith(new PairingError("pairing-unsupported", "no endpoint"));

  expect(view.getByText("这个地址上没有配对接口")).toBeTruthy();
  // Retyping is the reflex this screen has to interrupt: no code entered here
  // can create an endpoint that the server is not serving.
  expect(view.queryByText(/逐字核对/)).toBeNull();
  expect(view.getByText(/配对端点/)).toBeTruthy();
});

it("keeps saying the device is unpaired while it explains a server-side failure", async () => {
  const view = await failWith(new PairingError("pairing-unsupported", "no endpoint"));

  // The failure explains why pairing did not happen; it never implies that it
  // did. A device that reads "已配对" here would wait forever for data.
  expect(view.getByText("未配对")).toBeTruthy();
  expect(view.queryByText("已配对")).toBeNull();
  expect(view.getByLabelText("配对码")).toBeTruthy();
});

it("names the single refusal without claiming to know which one it was", async () => {
  const view = await failWith(new PairingError("code-refused", "refused"));

  expect(view.getByText("服务器没有接受这个配对码")).toBeTruthy();
  const rendered = JSON.stringify(view.toJSON());
  expect(rendered).toContain("逐字核对");
  expect(rendered).toContain("重新生成");
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
