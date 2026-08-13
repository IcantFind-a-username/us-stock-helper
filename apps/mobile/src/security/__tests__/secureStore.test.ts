import { expect, it, jest } from "@jest/globals";

import {
  resolveSecureStoreBackend,
  SecureStoreUnavailableError,
} from "../secureStore";

/**
 * The wrapper was written before `expo-secure-store` was installed, so it
 * refused every operation and pairing died at its last step. Every other test
 * injects its own backend, which is why nothing caught it: the failure lived
 * only in the one code path a real build takes.
 */

it("resolves a backend that can actually store a value", async () => {
  const backend = resolveSecureStoreBackend();

  await expect(
    backend.writeValue("probe", "value", {
      accessibility: "when-unlocked-this-device-only",
    }),
  ).resolves.toBeUndefined();
  await expect(backend.readValue("probe")).resolves.toBe("value");
  await expect(backend.deleteValue("probe")).resolves.toBeUndefined();
});

it("keeps the token off iCloud and off other devices", async () => {
  const SecureStore = jest.requireMock("expo-secure-store") as {
    setItemAsync: jest.Mock<
      (key: string, value: string, options: { keychainAccessible: string }) => Promise<void>
    >;
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: string;
  };
  SecureStore.setItemAsync.mockClear();

  await resolveSecureStoreBackend().writeValue("k", "v", {
    accessibility: "when-unlocked-this-device-only",
  });

  const call = SecureStore.setItemAsync.mock.calls[0];
  expect(call).toBeDefined();
  const options = call![2];
  // This is the one accessibility class excluded from both iCloud Keychain
  // and encrypted device backups, so a token written under it cannot be
  // restored onto a different phone.
  expect(options.keychainAccessible).toBe(
    SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  );
});

it("still reports an unreachable Keychain as its own condition", async () => {
  const SecureStore = jest.requireMock("expo-secure-store") as {
    getItemAsync: jest.Mock<() => Promise<string | null>>;
  };
  SecureStore.getItemAsync.mockRejectedValueOnce(new Error("keychain locked"));

  await expect(resolveSecureStoreBackend().readValue("k")).rejects.toBeInstanceOf(
    SecureStoreUnavailableError,
  );
});

it("does not crash the app when the native module is absent from the build", () => {
  // Adding an Expo native module needs the native client rebuilt, which a
  // phone in someone's pocket cannot do. A top-level import threw at module
  // load and took the whole app down with it — worse than the honest refusal
  // it replaced.
  jest.isolateModules(() => {
    jest.doMock("expo-secure-store", () => {
      throw new Error("Cannot find native module 'ExpoSecureStore'");
    });

    const { resolveSecureStoreBackend: resolve } = require("../secureStore");

    expect(() => resolve()).not.toThrow();
  });
});
