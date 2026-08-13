import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { getDeviceSessionRuntimeConfig } from "@/config/runtimeConfig";
import {
  createPairingClient,
  PairingError,
  type PairingClient,
} from "@/data/pairingClient";
import type { PairingFailure, PairingFailureReason } from "@/domain/pairing";
import {
  createDeviceCredentialStore,
  type DeviceCredential,
  type DeviceCredentialAbsence,
  type DeviceCredentialStore,
} from "@/security/deviceCredentialStore";
import {
  resolveSecureStoreBackend,
  SecureStoreUnavailableError,
} from "@/security/secureStore";

/**
 * Owns the answer to "may this app ask the server anything yet".
 *
 * The state is deliberately five-valued rather than a boolean: "still reading
 * the Keychain" is not "unpaired", and "the server revoked us" is not "you
 * never paired". Every screen downstream renders one of these words, so a state
 * that guessed would put a guess on the screen.
 */

export type DeviceSessionStatus =
  | "checking"
  | "unpaired"
  | "pairing"
  | "paired"
  | "revoked";

export type DeviceSessionState = {
  status: DeviceSessionStatus;
  deviceId: string | null;
  expiresAt: string | null;
  failure: PairingFailure | null;
};

type DeviceSessionRecord = DeviceSessionState & {
  deviceToken: string | null;
};

type DeviceSessionContextValue = {
  session: DeviceSessionState;
  pairingRequired: boolean;
  deviceToken: string | null;
  pair(code: string): Promise<void>;
  forgetDevice(): Promise<void>;
  reportRevoked(): Promise<void>;
};

type DeviceSessionProviderProps = PropsWithChildren<{
  credentialStore?: DeviceCredentialStore;
  pairingClient?: PairingClient;
  pairingRequired?: boolean;
}>;

const DeviceSessionContext = createContext<DeviceSessionContextValue | null>(
  null,
);

const checkingRecord: DeviceSessionRecord = {
  status: "checking",
  deviceId: null,
  expiresAt: null,
  failure: null,
  deviceToken: null,
};

function unpairedRecord(failure: PairingFailure | null): DeviceSessionRecord {
  return {
    status: "unpaired",
    deviceId: null,
    expiresAt: null,
    failure,
    deviceToken: null,
  };
}

function pairedRecord(credential: DeviceCredential): DeviceSessionRecord {
  return {
    status: "paired",
    deviceId: credential.deviceId,
    expiresAt: credential.expiresAt,
    failure: null,
    deviceToken: credential.deviceToken,
  };
}

function failure(
  reason: PairingFailureReason,
  retryAfterSeconds: number | null = null,
): PairingFailure {
  return { reason, retryAfterSeconds };
}

const reasonByAbsence: Record<
  Exclude<DeviceCredentialAbsence, "not-paired">,
  PairingFailureReason
> = {
  "secure-store-unavailable": "secure-store-unavailable",
  unreadable: "stored-credential-unreadable",
};

function toFailure(error: unknown): PairingFailure {
  if (error instanceof PairingError) {
    return failure(error.reason, error.retryAfterSeconds);
  }
  if (error instanceof SecureStoreUnavailableError) {
    return failure("secure-store-unavailable");
  }
  return failure("unexpected");
}

export function DeviceSessionProvider({
  children,
  credentialStore,
  pairingClient,
  pairingRequired,
}: DeviceSessionProviderProps) {
  // Resolving the backend loads a native module. A build whose credential
  // comes from a development LAN token never pairs and has no use for the
  // Keychain, so reaching for it there can only fail — and on a phone whose
  // native client predates the dependency, that failure took down an app
  // that had no reason to care whether it was installed.
  const runtimeConfig = useMemo(() => {
    if (pairingClient && pairingRequired !== undefined) return null;
    try {
      return getDeviceSessionRuntimeConfig();
    } catch {
      return null;
    }
  }, [pairingClient, pairingRequired]);
  // The prop is only supplied by tests; a real build leaves it undefined and
  // the answer comes from the runtime config, so the decision has to be made
  // after that is read rather than from the prop alone.
  const pairs = pairingRequired ?? runtimeConfig?.pairingRequired ?? true;
  const store = useMemo(() => {
    if (credentialStore) return credentialStore;
    // Resolving the backend loads a native module. A build whose credential
    // comes from a development LAN token never pairs, so the Keychain has
    // nothing to hold for it — and on a phone whose native client predates
    // the dependency, asking for it anyway took the whole app down.
    if (!pairs) return null;
    return createDeviceCredentialStore(resolveSecureStoreBackend());
  }, [credentialStore, pairs]);
  const client = useMemo(() => {
    if (pairingClient) return { client: pairingClient, reason: null };
    if (!runtimeConfig?.apiUrl) {
      return { client: null, reason: "not-configured" as PairingFailureReason };
    }
    try {
      return {
        client: createPairingClient({
          baseUrl: runtimeConfig.apiUrl,
          development: typeof __DEV__ !== "undefined" && __DEV__,
        }),
        reason: null,
      };
    } catch (error) {
      return { client: null, reason: toFailure(error).reason };
    }
  }, [pairingClient, runtimeConfig]);
  const [record, setRecord] = useState<DeviceSessionRecord>(checkingRecord);

  useEffect(() => {
    let active = true;
    if (!store) {
      // Nothing to read: this build never pairs, so there is no credential
      // and no Keychain to ask about one.
      setRecord(unpairedRecord(null));
      return;
    }
    void store
      .read()
      .then((result) => {
        if (!active) return;
        if (result.credential !== null) {
          setRecord(pairedRecord(result.credential));
          return;
        }
        setRecord(
          unpairedRecord(
            result.reason === "not-paired"
              ? null
              : failure(reasonByAbsence[result.reason]),
          ),
        );
      })
      .catch(() => {
        if (!active) return;
        setRecord(unpairedRecord(failure("secure-store-unavailable")));
      });
    return () => {
      active = false;
    };
  }, [store]);

  const pair = useCallback(
    async (code: string) => {
      if (client.client === null) {
        setRecord(unpairedRecord(failure(client.reason ?? "not-configured")));
        return;
      }
      if (!store) {
        // A build with nowhere to keep the token must not report a pairing it
        // cannot survive a relaunch with.
        setRecord(unpairedRecord(failure("secure-store-unavailable")));
        return;
      }
      setRecord((current) => ({ ...current, status: "pairing", failure: null }));
      try {
        const credential = await client.client.pair({ code });
        // The token is only ever announced as held after it is durably held: a
        // session that lived in memory alone would look identical on screen and
        // then disappear at the next launch with no explanation.
        await store.save(credential);
        setRecord(pairedRecord(credential));
      } catch (error) {
        setRecord(unpairedRecord(toFailure(error)));
      }
    },
    [client, store],
  );

  const forgetDevice = useCallback(async () => {
    await store?.clear().catch(() => undefined);
    setRecord(unpairedRecord(null));
  }, [store]);

  const reportRevoked = useCallback(async () => {
    await store?.clear().catch(() => undefined);
    setRecord({
      status: "revoked",
      deviceId: null,
      expiresAt: null,
      failure: failure("revoked"),
      deviceToken: null,
    });
  }, [store]);

  const value = useMemo<DeviceSessionContextValue>(() => {
    const { deviceToken, ...session } = record;
    return {
      session,
      pairingRequired: pairingRequired ?? runtimeConfig?.pairingRequired ?? true,
      deviceToken,
      pair,
      forgetDevice,
      reportRevoked,
    };
  }, [forgetDevice, pair, pairingRequired, record, reportRevoked, runtimeConfig]);

  return (
    <DeviceSessionContext.Provider value={value}>
      {children}
    </DeviceSessionContext.Provider>
  );
}

export function useDeviceSession(): DeviceSessionContextValue {
  const value = useContext(DeviceSessionContext);
  if (value === null) {
    throw new Error("useDeviceSession must be used within DeviceSessionProvider");
  }
  return value;
}
