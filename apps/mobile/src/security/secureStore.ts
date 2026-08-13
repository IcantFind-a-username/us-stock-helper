/**
 * The narrow secure-storage surface this app needs, kept as an interface so the
 * device token has exactly one door out of the process.
 *
 * Backed by `expo-secure-store`. No fallback to AsyncStorage or the
 * filesystem may be added in its place: those are plaintext and reach iCloud
 * backups, which is precisely what the Keychain is here to avoid. A Keychain
 * this process cannot reach is reported as that, never as an empty read.
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

type ExpoSecureStore = {
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: string;
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(
    key: string,
    value: string,
    options: { keychainAccessible: string },
  ): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
};

/**
 * Loaded on use rather than at import.
 *
 * Adding an Expo native module requires the native client to be rebuilt, and
 * a phone already in someone's hand cannot do that. Importing at module scope
 * threw during bundle evaluation and took the entire app down — strictly
 * worse than the stated refusal it was meant to replace, because a reader
 * who cannot pair can still read the market.
 */
function loadSecureStore(): ExpoSecureStore | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- a
    // static import evaluates at bundle load, which is the crash this avoids.
    return require("expo-secure-store") as ExpoSecureStore;
  } catch {
    return null;
  }
}

const keychainBackend: SecureStoreBackend = {
  async readValue(key) {
    const SecureStore = requireSecureStore();
    try {
      return await SecureStore.getItemAsync(key);
    } catch (error) {
      throw new SecureStoreUnavailableError(describe(error));
    }
  },
  async writeValue(key, value, options) {
    const SecureStore = requireSecureStore();
    try {
      await SecureStore.setItemAsync(key, value, {
        keychainAccessible: accessibilityClass(SecureStore, options.accessibility),
      });
    } catch (error) {
      throw new SecureStoreUnavailableError(describe(error));
    }
  },
  async deleteValue(key) {
    const SecureStore = requireSecureStore();
    try {
      await SecureStore.deleteItemAsync(key);
    } catch (error) {
      throw new SecureStoreUnavailableError(describe(error));
    }
  },
};

function requireSecureStore(): ExpoSecureStore {
  const module = loadSecureStore();
  if (!module) throw new SecureStoreUnavailableError(missingModuleMessage);
  return module;
}

function accessibilityClass(
  SecureStore: ExpoSecureStore,
  value: SecureValueAccessibility,
) {
  // The only class excluded from both iCloud Keychain and encrypted device
  // backups, so a token written under it cannot be restored onto another
  // phone.
  if (value === "when-unlocked-this-device-only") {
    return SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY;
  }
  throw new SecureStoreUnavailableError(
    `unsupported keychain accessibility: ${value}`,
  );
}

function describe(error: unknown) {
  return error instanceof Error
    ? `the keychain could not be reached: ${error.message}`
    : "the keychain could not be reached";
}

export function resolveSecureStoreBackend(): SecureStoreBackend {
  return loadSecureStore() ? keychainBackend : unavailableBackend;
}
