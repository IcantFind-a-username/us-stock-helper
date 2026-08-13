import { expect, it } from "@jest/globals";

import {
  describePairingFailure,
  pairingFailureReasons,
  type PairingFailureReason,
} from "../pairing";

it("gives every failure reason its own readable Chinese title", () => {
  const titles = pairingFailureReasons.map(
    (reason) => describePairingFailure({ reason }).title,
  );

  expect(new Set(titles).size).toBe(pairingFailureReasons.length);
  for (const title of titles) {
    expect(title).toMatch(/[一-龥]/);
    expect(title).not.toMatch(/[a-z]-[a-z]/);
  }
});

it("gives every failure reason its own readable Chinese body", () => {
  const bodies = pairingFailureReasons.map(
    (reason) => describePairingFailure({ reason }).body,
  );

  expect(new Set(bodies).size).toBe(pairingFailureReasons.length);
  for (const body of bodies) {
    expect(body.length).toBeGreaterThan(10);
    expect(body).toMatch(/[一-龥]/);
  }
});

it("distinguishes a wrong code from an expired one and from a reused one", () => {
  const wrong = describePairingFailure({ reason: "invalid-code" });
  const expired = describePairingFailure({ reason: "expired-code" });
  const used = describePairingFailure({ reason: "code-used" });

  expect(wrong.title).toBe("配对码不正确");
  expect(expired.title).toBe("配对码已过期");
  expect(used.title).toBe("配对码已被使用");
  expect(expired.body).toContain("重新生成");
  expect(used.body).toContain("只能使用一次");
});

it("states the rate-limit wait when the server supplied one", () => {
  const described = describePairingFailure({
    reason: "rate-limited",
    retryAfterSeconds: 900,
  });

  expect(described.title).toBe("尝试次数过多");
  expect(described.body).toContain("900 秒");
});

it("says the wait is unknown rather than inventing a retry delay", () => {
  const described = describePairingFailure({ reason: "rate-limited" });

  expect(described.body).toContain("没有给出");
  expect(described.body).not.toMatch(/\d+\s*秒/);
});

it("never leaks an internal enum name into user-facing copy", () => {
  for (const reason of pairingFailureReasons) {
    const described = describePairingFailure({ reason });
    expect(described.title).not.toContain(reason);
    expect(described.body).not.toContain(reason);
  }
});

it("keeps the reason list and the copy table in step", () => {
  const unknown = "not-a-reason" as PairingFailureReason;

  expect(() => describePairingFailure({ reason: unknown })).toThrow(
    "unknown pairing failure reason",
  );
});
