import { describe, expect, it, jest } from "@jest/globals";

import { createPairingClient, PairingError } from "../pairingClient";

const pairingCode = "K7Q-4M2-88T";
const deviceToken = "8f4c1d2e6b7a09835c4d1e2f6a7b8c9d0e1f2a3b4c5d6e7f";

function pairingPayload() {
  return {
    deviceId: "6b0f2c48-9a11-4f0e-8f3d-2c7e5a1b9d40",
    deviceToken,
    expiresAt: "2026-11-10T00:00:00.000Z",
  };
}

function jsonResponse(
  value: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null },
    json: async () => value,
  } as Response;
}

function clientWith(
  response: Response | (() => Promise<Response>),
  baseUrl = "https://api.example.com",
) {
  const fetchImpl = jest.fn(async () =>
    typeof response === "function" ? response() : response,
  ) as unknown as typeof fetch;
  return {
    fetchImpl,
    client: createPairingClient({ baseUrl, development: false, fetchImpl }),
  };
}

describe("pairing request", () => {
  it("exchanges a pairing code for a device credential", async () => {
    const { client, fetchImpl } = clientWith(jsonResponse(pairingPayload(), 201));

    const credential = await client.pair({
      code: pairingCode,
      deviceName: "iPhone",
    });

    expect(credential).toEqual(pairingPayload());
    const [url, init] = (fetchImpl as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe("https://api.example.com/v1/device-pairings");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      pairingCode,
      deviceName: "iPhone",
    });
  });

  it("sends no authorization header, because pairing is what grants authority", async () => {
    const { client, fetchImpl } = clientWith(jsonResponse(pairingPayload(), 201));

    await client.pair({ code: pairingCode, deviceName: "iPhone" });

    const [, init] = (fetchImpl as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    const headerNames = Object.keys(init.headers as Record<string, string>).map(
      (name) => name.toLowerCase(),
    );
    expect(headerNames).not.toContain("authorization");
  });

  it("refuses to let a redirect carry the pairing code to another origin", async () => {
    const { client, fetchImpl } = clientWith(jsonResponse(null, 302));

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "malformed" });
    const [, init] = (fetchImpl as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(init.redirect).toBe("error");
  });

  it("rejects a blank code without spending a server attempt on it", async () => {
    const { client, fetchImpl } = clientWith(jsonResponse(pairingPayload(), 201));

    await expect(
      client.pair({ code: "   ", deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "invalid-code" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("trims the surrounding whitespace a keyboard adds to a typed code", async () => {
    const { client, fetchImpl } = clientWith(jsonResponse(pairingPayload(), 201));

    await client.pair({ code: `  ${pairingCode} `, deviceName: " iPhone " });

    const [, init] = (fetchImpl as jest.Mock).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(JSON.parse(String(init.body))).toEqual({
      pairingCode,
      deviceName: "iPhone",
    });
  });
});

describe("origin policy", () => {
  it("refuses a plain-HTTP origin in a production build", () => {
    expect(() =>
      createPairingClient({
        baseUrl: "http://api.example.com",
        development: false,
      }),
    ).toThrow(PairingError);
  });

  it("classifies a plain-HTTP production origin as insecure", () => {
    try {
      createPairingClient({
        baseUrl: "http://api.example.com",
        development: false,
      });
      throw new Error("expected the insecure origin to be rejected");
    } catch (error) {
      expect(error).toMatchObject({ reason: "insecure-origin" });
    }
  });

  it("allows a development loopback origin", () => {
    expect(() =>
      createPairingClient({
        baseUrl: "http://127.0.0.1:8788",
        development: true,
      }),
    ).not.toThrow();
  });

  it("refuses a non-loopback plain-HTTP origin even in development", () => {
    // A pairing code travelling over a LAN in the clear is a code anyone on
    // that LAN can replay, so the loopback exemption stops at the interface.
    expect(() =>
      createPairingClient({
        baseUrl: "http://192.168.1.20:8788",
        development: true,
      }),
    ).toThrow("pairing requires an https origin");
  });

  it("refuses an origin that carries embedded credentials", () => {
    try {
      createPairingClient({
        baseUrl: "https://user:secret@api.example.com",
        development: false,
      });
      throw new Error("expected the credentialed origin to be rejected");
    } catch (error) {
      expect(error).toMatchObject({ reason: "insecure-origin" });
      expect((error as Error).message).not.toContain("secret");
    }
  });
});

describe("failure classification", () => {
  it.each([
    [404, "PAIRING_CODE_NOT_FOUND", "invalid-code"],
    [400, "INVALID_PAIRING_CODE", "invalid-code"],
    [410, "PAIRING_CODE_EXPIRED", "expired-code"],
    [409, "PAIRING_CODE_CONSUMED", "code-used"],
    [403, "DEVICE_REVOKED", "revoked"],
    [500, "INTERNAL", "server"],
    [503, "UNAVAILABLE", "server"],
  ])(
    "maps HTTP %s %s to the %s reason",
    async (status, code, reason) => {
      const { client } = clientWith(
        jsonResponse({ error: { code, message: "denied" } }, status as number),
      );

      await expect(
        client.pair({ code: pairingCode, deviceName: "iPhone" }),
      ).rejects.toMatchObject({ reason });
    },
  );

  it("classifies a status the server did not annotate by its HTTP code alone", async () => {
    const { client } = clientWith(jsonResponse({}, 410));

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "expired-code" });
  });

  it("reports the retry delay a rate limiter supplied", async () => {
    const { client } = clientWith(
      jsonResponse({ error: { code: "RATE_LIMITED" } }, 429, {
        "retry-after": "900",
      }),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "rate-limited", retryAfterSeconds: 900 });
  });

  it("leaves the retry delay null when the rate limiter gave none", async () => {
    const { client } = clientWith(jsonResponse({}, 429));

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({
      reason: "rate-limited",
      retryAfterSeconds: null,
    });
  });

  it("ignores an unparseable retry delay instead of inventing one", async () => {
    const { client } = clientWith(
      jsonResponse({}, 429, { "retry-after": "Tue, 10 Nov 2026 00:00:00 GMT" }),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({
      reason: "rate-limited",
      retryAfterSeconds: null,
    });
  });

  it("refuses a negative retry delay rather than showing one to the reader", async () => {
    const { client } = clientWith(
      jsonResponse({}, 429, { "retry-after": "-5" }),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({
      reason: "rate-limited",
      retryAfterSeconds: null,
    });
  });

  it("refuses a retry delay that is not purely a count of seconds", async () => {
    const { client } = clientWith(
      jsonResponse({}, 429, { "retry-after": "30 minutes" }),
    );

    // Reading the leading digits would turn half an hour into thirty seconds
    // and send the reader back while the lockout is still running.
    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({
      reason: "rate-limited",
      retryAfterSeconds: null,
    });
  });

  it("rejects a success payload with no device token", async () => {
    const { client } = clientWith(
      jsonResponse({ deviceId: "abc", expiresAt: null }, 201),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "malformed" });
  });

  it("rejects a device token too short to be a 256-bit secret", async () => {
    const { client } = clientWith(
      jsonResponse({ ...pairingPayload(), deviceToken: "short" }, 201),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "malformed" });
  });

  it("accepts a credential whose expiry the server declined to state", async () => {
    const { client } = clientWith(
      jsonResponse({ ...pairingPayload(), expiresAt: null }, 201),
    );

    // A missing expiry stays null; a guessed one would silently expire a
    // working session or keep a dead one alive on screen.
    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).resolves.toMatchObject({ expiresAt: null });
  });

  it("rejects an expiry that is not an ISO timestamp", async () => {
    const { client } = clientWith(
      jsonResponse({ ...pairingPayload(), expiresAt: "soon" }, 201),
    );

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "malformed" });
  });

  it("reports an unreachable server as offline", async () => {
    const fetchImpl = jest.fn(async () => {
      throw new TypeError("Network request failed");
    }) as unknown as typeof fetch;
    const client = createPairingClient({
      baseUrl: "https://api.example.com",
      development: false,
      fetchImpl,
    });

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "offline" });
  });

  it("reports a body that is not JSON as malformed", async () => {
    const { client } = clientWith({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => {
        throw new SyntaxError("Unexpected token <");
      },
    } as unknown as Response);

    await expect(
      client.pair({ code: pairingCode, deviceName: "iPhone" }),
    ).rejects.toMatchObject({ reason: "malformed" });
  });

  it("aborts and classifies a pairing request that outruns its deadline", async () => {
    jest.useFakeTimers();
    try {
      let fetchSignal: AbortSignal | undefined;
      const fetchImpl = jest.fn(
        async (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            fetchSignal = init?.signal as AbortSignal;
            fetchSignal.addEventListener(
              "abort",
              () =>
                reject(
                  Object.assign(new Error("timed out"), { name: "AbortError" }),
                ),
              { once: true },
            );
          }),
      ) as unknown as typeof fetch;
      const client = createPairingClient({
        baseUrl: "https://api.example.com",
        development: false,
        fetchImpl,
        timeoutMs: 25,
      });

      const request = client.pair({ code: pairingCode, deviceName: "iPhone" });
      await Promise.resolve();
      jest.advanceTimersByTime(25);

      expect(fetchSignal?.aborted).toBe(true);
      await expect(request).rejects.toMatchObject({ reason: "timeout" });
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("secret hygiene", () => {
  it("keeps the pairing code out of every rejection it raises", async () => {
    const { client } = clientWith(
      jsonResponse(
        { error: { code: "INVALID_PAIRING_CODE", message: `code ${pairingCode}` } },
        400,
      ),
    );

    const error = (await client
      .pair({ code: pairingCode, deviceName: "iPhone" })
      .catch((caught: unknown) => caught)) as PairingError;

    expect(error).toBeInstanceOf(PairingError);
    expect(
      JSON.stringify(error, Object.getOwnPropertyNames(error)),
    ).not.toContain(pairingCode);
  });

  it("keeps the issued token out of a rejection raised after it arrived", async () => {
    const { client } = clientWith(
      jsonResponse({ ...pairingPayload(), expiresAt: "soon" }, 201),
    );

    const error = (await client
      .pair({ code: pairingCode, deviceName: "iPhone" })
      .catch((caught: unknown) => caught)) as PairingError;

    expect(
      JSON.stringify(error, Object.getOwnPropertyNames(error)),
    ).not.toContain(deviceToken);
  });
});
