import {
  SecureStoreUnavailableError,
  type SecureStoreBackend,
} from "./secureStore";

/**
 * The one place a device token is allowed to rest.
 *
 * Reads answer with an absence and its cause rather than a bare null: "nothing
 * stored yet", "the Keychain could not be reached" and "the stored bytes do not
 * parse" send the reader to three different actions, and a screen that cannot
 * tell them apart will show the wrong one.
 */

export const deviceCredentialKey = "us-stock-helper/device-credential";

/**
 * The server issues at least 256 bits of randomness. Anything materially
 * shorter did not come from the pairing endpoint this app trusts.
 */
export const minimumDeviceTokenLength = 32;

export type DeviceCredential = {
  deviceId: string;
  deviceToken: string;
  expiresAt: string | null;
};

export type DeviceCredentialAbsence =
  | "not-paired"
  | "secure-store-unavailable"
  | "unreadable";

export type DeviceCredentialRead =
  | { credential: DeviceCredential; reason: null }
  | { credential: null; reason: DeviceCredentialAbsence };

export interface DeviceCredentialStore {
  read(): Promise<DeviceCredentialRead>;
  save(credential: DeviceCredential): Promise<void>;
  clear(): Promise<void>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeCredential(raw: string): DeviceCredential | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(parsed)) return null;
  const { deviceId, deviceToken, expiresAt } = parsed;
  if (typeof deviceId !== "string" || deviceId.trim() === "") return null;
  if (
    typeof deviceToken !== "string" ||
    deviceToken.length < minimumDeviceTokenLength
  ) {
    return null;
  }
  if (expiresAt !== null && typeof expiresAt !== "string") return null;
  return { deviceId, deviceToken, expiresAt };
}

export function createDeviceCredentialStore(
  backend: SecureStoreBackend,
): DeviceCredentialStore {
  return {
    async read() {
      let raw: string | null;
      try {
        raw = await backend.readValue(deviceCredentialKey);
      } catch {
        return { credential: null, reason: "secure-store-unavailable" };
      }
      if (raw === null) return { credential: null, reason: "not-paired" };
      const credential = decodeCredential(raw);
      if (credential === null) return { credential: null, reason: "unreadable" };
      return { credential, reason: null };
    },

    async save(credential) {
      if (credential.deviceToken.length < minimumDeviceTokenLength) {
        throw new Error("device token is too short to be a device secret");
      }
      try {
        await backend.writeValue(
          deviceCredentialKey,
          JSON.stringify(credential),
          { accessibility: "when-unlocked-this-device-only" },
        );
      } catch {
        // The backend's own error is dropped rather than wrapped: it was handed
        // the token and may well be quoting it back inside its message.
        throw new SecureStoreUnavailableError(
          "the device token could not be written to secure storage",
        );
      }
    },

    async clear() {
      try {
        await backend.deleteValue(deviceCredentialKey);
      } catch {
        throw new SecureStoreUnavailableError(
          "the device token could not be removed from secure storage",
        );
      }
    },
  };
}
