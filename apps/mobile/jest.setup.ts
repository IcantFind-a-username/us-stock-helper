jest.mock("expo-screen-orientation", () => ({
  lockAsync: jest.fn(),
  unlockAsync: jest.fn(),
  OrientationLock: {
    PORTRAIT_UP: 1,
    LANDSCAPE: 6,
  },
}));

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

// expo-secure-store is a native module; the tests exercise the wrapper's
// contract with it rather than the Keychain itself.
jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: "whenUnlockedThisDeviceOnly",
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      store.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      store.delete(key);
    }),
  };
});

// The library's own SafeAreaProvider only resolves insets from a real native
// event, which never fires under Jest — any tree that calls useSafeAreaInsets
// without this would hang with insets stuck at null and throw. The package's
// own jest mock resolves synchronously to a zero-inset default instead, and
// leaves SafeAreaView itself untouched. A test after a specific device's
// insets overrides this locally with its own jest.mock of the same module.
jest.mock("react-native-safe-area-context", () =>
  require("react-native-safe-area-context/jest/mock").default,
);
