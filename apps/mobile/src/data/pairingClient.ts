import type { PairingFailureReason } from "@/domain/pairing";
import {
  minimumDeviceTokenLength,
  type DeviceCredential,
} from "@/security/deviceCredentialStore";

/**
 * Exchanges a short-lived pairing code for a long-lived device token.
 *
 * This is the only unauthenticated call the app makes, and the only moment a
 * secret crosses the wire in the open, so the transport rules are enforced here
 * rather than trusted to the caller. Nothing the server says is copied into a
 * thrown error: its messages quote the code back, and this client's rejections
 * end up in crash reports.
 */

export class PairingError extends Error {
  readonly reason: PairingFailureReason;
  readonly retryAfterSeconds: number | null;

  constructor(
    reason: PairingFailureReason,
    message: string,
    options: { retryAfterSeconds?: number | null } = {},
  ) {
    super(message);
    this.name = "PairingError";
    this.reason = reason;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }
}

export type PairingRequest = {
  code: string;
  deviceName: string;
};

export type PairingClient = {
  pair(request: PairingRequest, signal?: AbortSignal): Promise<DeviceCredential>;
};

type PairingClientOptions = {
  baseUrl: string;
  development: boolean;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
};

const loopbackHostnames = new Set(["127.0.0.1", "localhost", "::1"]);

const reasonByErrorCode: Record<string, PairingFailureReason> = {
  INVALID_PAIRING_CODE: "invalid-code",
  PAIRING_CODE_NOT_FOUND: "invalid-code",
  PAIRING_CODE_EXPIRED: "expired-code",
  PAIRING_CODE_CONSUMED: "code-used",
  ALREADY_PAIRED: "code-used",
  RATE_LIMITED: "rate-limited",
  DEVICE_REVOKED: "revoked",
};

const reasonByStatus: Record<number, PairingFailureReason> = {
  400: "invalid-code",
  401: "invalid-code",
  404: "invalid-code",
  409: "code-used",
  410: "expired-code",
  429: "rate-limited",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function reasonForResponse(status: number, payload: unknown) {
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null;
  const code = error && typeof error.code === "string" ? error.code : null;
  const byCode = code ? reasonByErrorCode[code] : undefined;
  if (byCode) return byCode;
  const byStatus = reasonByStatus[status];
  if (byStatus) return byStatus;
  return status >= 500 ? "server" : "malformed";
}

/**
 * Only a whole number of seconds is honoured. The HTTP-date form of Retry-After
 * is left unparsed on purpose: reading it needs a trustworthy local clock, and
 * a wrong wait is worse here than an admitted unknown one.
 */
function readRetryAfterSeconds(response: Response): number | null {
  const raw = response.headers?.get?.("Retry-After") ?? null;
  if (raw === null || !/^\d+$/.test(raw.trim())) return null;
  return Number.parseInt(raw.trim(), 10);
}

function decodeCredential(payload: unknown): DeviceCredential {
  const malformed = new PairingError(
    "malformed",
    "the pairing response is not a valid device credential",
  );
  if (!isRecord(payload)) throw malformed;
  const { deviceId, deviceToken, expiresAt } = payload;
  if (typeof deviceId !== "string" || deviceId.trim() === "") throw malformed;
  if (
    typeof deviceToken !== "string" ||
    deviceToken.length < minimumDeviceTokenLength
  ) {
    throw malformed;
  }
  if (expiresAt !== null && expiresAt !== undefined) {
    if (typeof expiresAt !== "string") throw malformed;
    const parsed = new Date(expiresAt);
    if (!Number.isFinite(parsed.getTime()) || !/[zZ]|[+-]\d\d:\d\d$/.test(expiresAt)) {
      throw malformed;
    }
    return { deviceId, deviceToken, expiresAt };
  }
  return { deviceId, deviceToken, expiresAt: null };
}

export function createPairingClient({
  baseUrl,
  development,
  fetchImpl = fetch,
  timeoutMs = 8_000,
}: PairingClientOptions): PairingClient {
  const normalizedBaseUrl = baseUrl.trim().replace(/\/+$/, "");
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(normalizedBaseUrl);
  } catch {
    throw new PairingError("not-configured", "the pairing origin is not a valid URL");
  }
  if (parsedBaseUrl.username !== "" || parsedBaseUrl.password !== "") {
    throw new PairingError(
      "insecure-origin",
      "the pairing origin must not carry embedded credentials",
    );
  }
  if (
    (parsedBaseUrl.pathname !== "" && parsedBaseUrl.pathname !== "/") ||
    parsedBaseUrl.search !== "" ||
    parsedBaseUrl.hash !== ""
  ) {
    throw new PairingError(
      "not-configured",
      "the pairing origin must be a bare origin",
    );
  }
  const loopback = loopbackHostnames.has(parsedBaseUrl.hostname);
  if (
    parsedBaseUrl.protocol !== "https:" &&
    !(development && parsedBaseUrl.protocol === "http:" && loopback)
  ) {
    throw new PairingError("insecure-origin", "pairing requires an https origin");
  }

  return {
    async pair({ code, deviceName }, callerSignal) {
      const pairingCode = code.trim();
      if (pairingCode === "") {
        throw new PairingError("invalid-code", "a pairing code is required");
      }
      if (callerSignal?.aborted) {
        const aborted = new Error("pairing was aborted by caller");
        aborted.name = "AbortError";
        throw aborted;
      }

      const controller = new AbortController();
      let abortCause: "caller" | "timeout" | null = null;
      const abortOnce = (cause: "caller" | "timeout") => {
        if (abortCause !== null) return;
        abortCause = cause;
        controller.abort();
      };
      const abortFromCaller = () => abortOnce("caller");
      callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
      const timeout = setTimeout(() => abortOnce("timeout"), timeoutMs);

      try {
        const response = await fetchImpl(
          `${normalizedBaseUrl}/v1/device-pairings`,
          {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              pairingCode,
              deviceName: deviceName.trim(),
            }),
            // A redirect would hand the pairing code to whatever origin the
            // response names, so the request fails instead of following one.
            redirect: "error",
            signal: controller.signal,
          },
        );
        if (response.status >= 300 && response.status < 400) {
          throw new PairingError(
            "malformed",
            "the pairing endpoint answered with a redirect",
          );
        }
        let payload: unknown = null;
        let payloadReadable = true;
        try {
          payload = (await response.json()) as unknown;
        } catch {
          payloadReadable = false;
        }
        if (!response.ok) {
          const reason = reasonForResponse(response.status, payload);
          throw new PairingError(
            reason,
            `the pairing request was refused with HTTP ${response.status}`,
            { retryAfterSeconds: readRetryAfterSeconds(response) },
          );
        }
        if (!payloadReadable) {
          throw new PairingError(
            "malformed",
            "the pairing response body was not JSON",
          );
        }
        return decodeCredential(payload);
      } catch (error) {
        if (abortCause === "timeout") {
          throw new PairingError("timeout", "the pairing request timed out");
        }
        if (abortCause === "caller") {
          const aborted = new Error("pairing was aborted by caller");
          aborted.name = "AbortError";
          throw aborted;
        }
        if (error instanceof PairingError) throw error;
        if (error instanceof Error && error.name === "AbortError") {
          throw new PairingError(
            "offline",
            "the pairing request was aborted without a known cause",
          );
        }
        throw new PairingError("offline", "the pairing service is unreachable");
      } finally {
        clearTimeout(timeout);
        callerSignal?.removeEventListener("abort", abortFromCaller);
      }
    },
  };
}
