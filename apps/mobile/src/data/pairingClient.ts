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
 *
 * The wire contract is `services/device_auth` plus Task 2 of
 * `docs/superpowers/plans/2026-07-25-single-user-cloud-runtime.md`:
 * `POST /v1/device-pairings`, unauthenticated and rate-limited, answering
 * `{deviceId, deviceToken, expiresAt}` exactly once. The request carries the
 * pairing code and nothing else, because `redeem_pairing_code` labels the new
 * device from the code the operator issued and refuses by design to let any
 * caller-supplied string reach an operator's listing.
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

/**
 * Codes that name a problem with the endpoint, or with this caller's standing
 * at it, rather than with the pairing code.
 *
 * They are the only thing that separates a read-only gateway with no pairing
 * route from a pairing endpoint that refused a code, because both of them
 * answer 401. Sending a reader who hit the first one back to retype their code
 * is the failure this table exists to prevent.
 */
const reasonByErrorCode: Record<string, PairingFailureReason> = {
  AUTH_REQUIRED: "pairing-unsupported",
  PATH_NOT_ALLOWED: "pairing-unsupported",
  METHOD_NOT_ALLOWED: "pairing-unsupported",
  INVALID_ARGUMENT: "pairing-unsupported",
  CLIENT_NOT_ALLOWED: "client-not-allowed",
  DEVICE_REVOKED: "revoked",
  RATE_LIMITED: "rate-limited",
  // Honoured only because a server stated one of them outright. device_auth
  // answers every bad code with a single refusal so that failed guesses teach
  // an attacker nothing, so none of these arrives from the server this app
  // pairs with, and none of them is ever inferred from a status alone.
  INVALID_PAIRING_CODE: "invalid-code",
  PAIRING_CODE_NOT_FOUND: "invalid-code",
  PAIRING_CODE_EXPIRED: "expired-code",
  PAIRING_CODE_CONSUMED: "code-used",
  ALREADY_PAIRED: "code-used",
};

/**
 * What a status means on its own, once no error code has named the failure.
 *
 * A refusal collapses to one reason here. The statuses that could be read as
 * "expired" or "already used" are only ever that reading by convention, and a
 * wrong reading costs the reader a code they did not need to reissue or a
 * retype that could never have worked.
 */
const reasonByStatus: Record<number, PairingFailureReason> = {
  400: "pairing-unsupported",
  401: "code-refused",
  403: "client-not-allowed",
  404: "pairing-unsupported",
  405: "pairing-unsupported",
  409: "code-refused",
  410: "code-refused",
  429: "rate-limited",
  501: "pairing-unsupported",
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
    async pair({ code }, callerSignal) {
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
            body: JSON.stringify({ pairingCode }),
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
