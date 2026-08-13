import { afterEach, beforeEach, expect, it, jest } from "@jest/globals";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { PropsWithChildren } from "react";

import { PairingError, type PairingClient } from "@/data/pairingClient";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";
import type { SecureStoreBackend } from "@/security/secureStore";

import { DeviceSessionProvider, useDeviceSession } from "../DeviceSessionProvider";

const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";

function credential(): DeviceCredential {
  return {
    deviceId: "6b0f2c48-9a11-4f0e-8f3d-2c7e5a1b9d40",
    deviceToken,
    expiresAt: "2026-11-10T00:00:00.000Z",
  };
}

function memoryBackend(seed?: string) {
  const values = new Map<string, string>();
  if (seed !== undefined) {
    values.set("us-stock-helper/device-credential", seed);
  }
  const backend: SecureStoreBackend = {
    readValue: async (key) => values.get(key) ?? null,
    writeValue: async (key, value) => {
      values.set(key, value);
    },
    deleteValue: async (key) => {
      values.delete(key);
    },
  };
  return { backend, values };
}

function acceptingClient(): PairingClient {
  return { pair: async () => credential() };
}

function rejectingClient(error: PairingError): PairingClient {
  return {
    pair: async () => {
      throw error;
    },
  };
}

async function renderSession({
  backend,
  pairingClient,
}: {
  backend: SecureStoreBackend;
  pairingClient?: PairingClient;
}) {
  const wrapper = ({ children }: PropsWithChildren) => (
    <DeviceSessionProvider
      credentialStore={createDeviceCredentialStore(backend)}
      {...(pairingClient ? { pairingClient } : {})}>
      {children}
    </DeviceSessionProvider>
  );
  return renderHook(() => useDeviceSession(), { wrapper });
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

it("reports that it is still reading the Keychain before it has an answer", async () => {
  const backend: SecureStoreBackend = {
    readValue: () => new Promise<string | null>(() => undefined),
    writeValue: async () => undefined,
    deleteValue: async () => undefined,
  };

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });

  // An unanswered read is not an answer. Reporting "unpaired" here would show
  // the pairing screen to a device that turns out to be paired a tick later.
  expect(result.current.session.status).toBe("checking");
  expect(result.current.deviceToken).toBeNull();
});

it("says the device is unpaired once the secure store has been read", async () => {
  const { backend } = memoryBackend();

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });

  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  expect(result.current.deviceToken).toBeNull();
  expect(result.current.session.failure).toBeNull();
});

it("restores an existing pairing and offers its token to callers", async () => {
  const { backend } = memoryBackend(JSON.stringify(credential()));

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });

  await waitFor(() => expect(result.current.session.status).toBe("paired"));
  expect(result.current.session.deviceId).toBe(credential().deviceId);
  expect(result.current.session.expiresAt).toBe(credential().expiresAt);
  expect(result.current.deviceToken).toBe(deviceToken);
});

it("keeps a device paired after exchanging a code, and persists it securely", async () => {
  const { backend, values } = memoryBackend();

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  expect(result.current.session.status).toBe("paired");
  expect(result.current.deviceToken).toBe(deviceToken);
  expect(values.get("us-stock-helper/device-credential")).toContain(deviceToken);
});

it("never lets a device token reach AsyncStorage", async () => {
  const { backend } = memoryBackend();

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  const keys = await AsyncStorage.getAllKeys();
  const entries = await AsyncStorage.multiGet(keys);
  for (const [, value] of entries) {
    expect(value ?? "").not.toContain(deviceToken);
  }
});

it("never writes a device token to a console log", async () => {
  const { backend } = memoryBackend();

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  for (const spy of consoleSpies) {
    for (const call of spy.mock.calls) {
      expect(JSON.stringify(call)).not.toContain(deviceToken);
    }
  }
});

it("keeps the token out of the session state that screens render", async () => {
  const { backend } = memoryBackend();

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  // Screens render this object, and a rendered tree is what a crash reporter
  // and a screenshot both capture. The token stays on the separate handle that
  // only the market layer reads.
  expect(JSON.stringify(result.current.session)).not.toContain(deviceToken);
  expect(Object.values(result.current.session)).not.toContain(deviceToken);
});

it("keeps the token out of a failure raised after the token had arrived", async () => {
  const backend: SecureStoreBackend = {
    readValue: async () => null,
    // A backend that quotes what it was handed is the realistic hazard: the
    // value it is quoting is the token itself.
    writeValue: async (_key, value) => {
      throw new Error(`keychain refused ${value}`);
    },
    deleteValue: async () => undefined,
  };

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  expect(result.current.session.failure?.reason).toBe("secure-store-unavailable");
  expect(JSON.stringify(result.current.session)).not.toContain(deviceToken);
});

it("stays unpaired and names the reason when the server rejects the code", async () => {
  const { backend } = memoryBackend();
  const client = rejectingClient(
    new PairingError("expired-code", "pairing code expired"),
  );

  const { result } = await renderSession({ backend, pairingClient: client });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  expect(result.current.session.status).toBe("unpaired");
  expect(result.current.session.failure).toEqual({
    reason: "expired-code",
    retryAfterSeconds: null,
  });
  expect(result.current.deviceToken).toBeNull();
});

it("carries a rate limiter's retry delay through to the session", async () => {
  const { backend } = memoryBackend();
  const client = rejectingClient(
    new PairingError("rate-limited", "too many attempts", {
      retryAfterSeconds: 900,
    }),
  );

  const { result } = await renderSession({ backend, pairingClient: client });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  expect(result.current.session.failure).toEqual({
    reason: "rate-limited",
    retryAfterSeconds: 900,
  });
});

it("refuses to call itself paired when the token cannot be stored securely", async () => {
  const backend: SecureStoreBackend = {
    readValue: async () => null,
    writeValue: async () => {
      throw new Error("keychain unavailable");
    },
    deleteValue: async () => undefined,
  };
  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));

  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  // A memory-only session would look identical on screen and then vanish, so a
  // token that cannot be stored is treated as a token that was never issued.
  expect(result.current.session.status).toBe("unpaired");
  expect(result.current.session.failure?.reason).toBe("secure-store-unavailable");
  expect(result.current.deviceToken).toBeNull();
});

it("distinguishes an unreadable secure store from an unpaired device", async () => {
  const { backend } = memoryBackend("{not json");

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });

  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  expect(result.current.session.failure?.reason).toBe("stored-credential-unreadable");
});

it("reports a missing server address instead of failing the exchange silently", async () => {
  const { backend } = memoryBackend();

  const { result } = await renderSession({ backend });
  await waitFor(() => expect(result.current.session.status).toBe("unpaired"));
  await act(async () => {
    await result.current.pair("K7Q-4M2-88T");
  });

  expect(result.current.session.failure?.reason).toBe("not-configured");
});

it("forgets a device and returns to a stated unpaired state", async () => {
  const { backend, values } = memoryBackend(JSON.stringify(credential()));

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("paired"));
  await act(async () => {
    await result.current.forgetDevice();
  });

  expect(result.current.session.status).toBe("unpaired");
  expect(result.current.deviceToken).toBeNull();
  expect(values.size).toBe(0);
});

it("clears a stored credential the server has revoked", async () => {
  const { backend, values } = memoryBackend(JSON.stringify(credential()));

  const { result } = await renderSession({ backend, pairingClient: acceptingClient() });
  await waitFor(() => expect(result.current.session.status).toBe("paired"));
  await act(async () => {
    await result.current.reportRevoked();
  });

  expect(result.current.session.status).toBe("revoked");
  expect(result.current.deviceToken).toBeNull();
  expect(values.size).toBe(0);
});

it("refuses to be used outside its provider rather than defaulting to unpaired", async () => {
  await expect(renderHook(() => useDeviceSession())).rejects.toThrow(
    "useDeviceSession must be used within DeviceSessionProvider",
  );
});
