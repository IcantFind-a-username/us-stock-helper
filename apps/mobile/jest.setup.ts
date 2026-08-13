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
