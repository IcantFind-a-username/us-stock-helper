jest.mock("expo-screen-orientation", () => ({
  lockAsync: jest.fn(),
  unlockAsync: jest.fn(),
  OrientationLock: {
    PORTRAIT_UP: 1,
    LANDSCAPE: 6,
  },
}));
