/**
 * The narrow secure-storage surface this app needs, kept as an interface so the
 * device token has exactly one door out of the process.
 *
 * TODO: back `resolveSecureStoreBackend` with `expo-secure-store` once that
 * package is installed (`npx expo install expo-secure-store`, then rebuild the
 * native client). It is deliberately absent from package.json today, and no
 * fallback to AsyncStorage or the filesystem may be added in its place: those
 * are plaintext and reach iCloud backups, which is precisely what the Keychain
 * is being used to avoid. Until then this module fails loudly.
 */

/**
 * The Keychain accessibility class that stays on one device. It is the only one
 * excluded from both iCloud Keychain and encrypted device backups, so a token
 * written under it cannot be restored onto another phone.
 */
export type SecureValueAccessibility = "when-unlocked-this-device-only";

export type SecureStoreWriteOptions = {
  accessibility: SecureValueAccessibility;
};

export interface SecureStoreBackend {
  readValue(key: string): Promise<string | null>;
  writeValue(
    key: string,
    value: string,
    options: SecureStoreWriteOptions,
  ): Promise<void>;
  deleteValue(key: string): Promise<void>;
}

export class SecureStoreUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SecureStoreUnavailableError";
  }
}

const missingModuleMessage =
  "secure storage is unavailable: install expo-secure-store and rebuild the native client";

/**
 * Every operation rejects rather than resolving to nothing, so an absent
 * Keychain surfaces as its own stated condition instead of masquerading as a
 * device that was simply never paired.
 */
const unavailableBackend: SecureStoreBackend = {
  readValue: async () => {
    throw new SecureStoreUnavailableError(missingModuleMessage);
  },
  writeValue: async () => {
    throw new SecureStoreUnavailableError(missingModuleMessage);
  },
  deleteValue: async () => {
    throw new SecureStoreUnavailableError(missingModuleMessage);
  },
};

export function resolveSecureStoreBackend(): SecureStoreBackend {
  return unavailableBackend;
}
