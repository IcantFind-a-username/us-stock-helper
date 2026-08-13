import { afterEach, beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  createDeviceCredentialStore,
  deviceCredentialKey,
  type DeviceCredential,
} from "../deviceCredentialStore";
import {
  resolveSecureStoreBackend,
  SecureStoreUnavailableError,
  type SecureStoreBackend,
} from "../secureStore";

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
  const writes: { key: string; accessibility: string }[] = [];
  const backend: SecureStoreBackend = {
    readValue: async (key) => values.get(key) ?? null,
    writeValue: async (key, value, options) => {
      writes.push({ key, accessibility: options.accessibility });
      values.set(key, value);
    },
    deleteValue: async (key) => {
      values.delete(key);
    },
  };
  return { backend, values, writes };
}

const consoleSpies = [] as jest.SpiedFunction<(...args: unknown[]) => void>[];

beforeEach(async () => {
  await AsyncStorage.clear();
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    consoleSpies.push(
      jest.spyOn(console, method).mockImplementation(() => undefined),
    );
  }
});

afterEach(() => {
  while (consoleSpies.length > 0) consoleSpies.pop()?.mockRestore();
});

it("reports an unpaired device as absent with a reason rather than a bare null", async () => {
  const { backend } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  expect(await store.read()).toEqual({ credential: null, reason: "not-paired" });
});

it("round-trips a stored credential", async () => {
  const { backend } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  await store.save(credential());

  expect(await store.read()).toEqual({ credential: credential(), reason: null });
});

it("stores the token where an iCloud backup cannot reach it", async () => {
  const { backend, writes } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  await store.save(credential());

  // This accessibility class is the only one excluded from iCloud Keychain and
  // from encrypted device backups, which is what keeps the token on-device.
  expect(writes).toEqual([
    { key: deviceCredentialKey, accessibility: "when-unlocked-this-device-only" },
  ]);
});

it("never puts the token into AsyncStorage", async () => {
  const { backend } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  await store.save(credential());

  const keys = await AsyncStorage.getAllKeys();
  expect(keys).toEqual([]);
  const entries = await AsyncStorage.multiGet([...keys, deviceCredentialKey]);
  for (const [, value] of entries) {
    expect(value ?? "").not.toContain(deviceToken);
  }
});

it("never writes the token to a console log", async () => {
  const { backend } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  await store.save(credential());
  await store.read();
  await store.clear();

  for (const spy of consoleSpies) {
    for (const call of spy.mock.calls) {
      expect(JSON.stringify(call)).not.toContain(deviceToken);
    }
  }
});

it("keeps the token out of the error raised when secure storage fails", async () => {
  const backend: SecureStoreBackend = {
    readValue: async () => null,
    writeValue: async (_key, value) => {
      throw new Error(`keychain refused payload ${value}`);
    },
    deleteValue: async () => undefined,
  };
  const store = createDeviceCredentialStore(backend);

  const error = await store.save(credential()).catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(SecureStoreUnavailableError);
  expect(JSON.stringify(error, Object.getOwnPropertyNames(error))).not.toContain(
    deviceToken,
  );
});

it("reports an unavailable secure store instead of pretending the device is unpaired", async () => {
  const store = createDeviceCredentialStore(resolveSecureStoreBackend());

  expect(await store.read()).toEqual({
    credential: null,
    reason: "secure-store-unavailable",
  });
});

it("names the package an operator has to install for secure storage", async () => {
  const backend = resolveSecureStoreBackend();

  const error = await backend
    .writeValue("k", "v", { accessibility: "when-unlocked-this-device-only" })
    .catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(SecureStoreUnavailableError);
  expect((error as Error).message).toContain("expo-secure-store");
});

it("reports unreadable stored bytes as unreadable rather than as unpaired", async () => {
  const { backend, values } = memoryBackend();
  values.set(deviceCredentialKey, "{not json");
  const store = createDeviceCredentialStore(backend);

  expect(await store.read()).toEqual({ credential: null, reason: "unreadable" });
});

it("reports a stored record missing its token as unreadable", async () => {
  const { backend, values } = memoryBackend();
  values.set(
    deviceCredentialKey,
    JSON.stringify({ deviceId: "abc", expiresAt: null }),
  );
  const store = createDeviceCredentialStore(backend);

  expect(await store.read()).toEqual({ credential: null, reason: "unreadable" });
});

it("refuses to store a token too short to be a 256-bit secret", async () => {
  const { backend, writes } = memoryBackend();
  const store = createDeviceCredentialStore(backend);

  await expect(
    store.save({ ...credential(), deviceToken: "short-token" }),
  ).rejects.toThrow("device token is too short to be a device secret");
  expect(writes).toEqual([]);
});

it("forgets the credential when the pairing is cleared", async () => {
  const { backend, values } = memoryBackend();
  const store = createDeviceCredentialStore(backend);
  await store.save(credential());

  await store.clear();

  expect(values.size).toBe(0);
  expect(await store.read()).toEqual({ credential: null, reason: "not-paired" });
});
