/**
 * The vocabulary of pairing failures, and the words a reader actually sees.
 *
 * Every reason is separated from every other one because the recovery differs:
 * a rate-limited device has to wait, a server with no pairing endpoint has to
 * be upgraded, and an unreachable one has to be found first. Collapsing them
 * into one "pairing failed" would leave the reader guessing which they are in.
 *
 * The one place the app deliberately does not separate is the refused code.
 * `services/device_auth` answers "mistyped", "expired" and "already used" with
 * a single refusal so that nobody can learn from the answers which of their
 * guesses had once been real, and this app is not entitled to invent the
 * distinction the server withheld. `code-refused` is that single answer;
 * `invalid-code`, `expired-code` and `code-used` survive for the case where a
 * server states outright which one it was.
 */

export const pairingFailureReasons = [
  "code-refused",
  "invalid-code",
  "expired-code",
  "code-used",
  "rate-limited",
  "revoked",
  "pairing-unsupported",
  "client-not-allowed",
  "insecure-origin",
  "not-configured",
  "offline",
  "timeout",
  "server",
  "malformed",
  "secure-store-unavailable",
  "stored-credential-unreadable",
  "unexpected",
] as const;

export type PairingFailureReason = (typeof pairingFailureReasons)[number];

export type PairingFailure = {
  reason: PairingFailureReason;
  retryAfterSeconds: number | null;
};

export type PairingFailureCopy = {
  title: string;
  body: string;
};

const copyByReason: Record<PairingFailureReason, PairingFailureCopy> = {
  "code-refused": {
    title: "服务器没有接受这个配对码",
    body: "服务器只回答不接受，不说明是打错了、超时作废了，还是已经绑定过别的设备——这样别人就无法靠试错反推出哪些配对码曾经真实存在。请先逐字核对刚才输入的内容，注意区分数字与字母；确认没打错就在服务器上重新生成一个配对码再试。",
  },
  "invalid-code": {
    title: "配对码不正确",
    body: "服务器没有认出这个配对码。请核对服务器上打印的那一串字符，注意区分数字与字母，然后重新输入。",
  },
  "expired-code": {
    title: "配对码已过期",
    body: "配对码有有效期，超时后自动作废。请在服务器上重新生成一个，并尽快在这里输入。",
  },
  "code-used": {
    title: "配对码已被使用",
    body: "每个配对码只能使用一次，这一个已经绑定过设备。请在服务器上重新生成一个再试。",
  },
  "rate-limited": {
    title: "尝试次数过多",
    body: "服务器已暂时拒绝新的配对请求，这是为了阻止有人穷举配对码。",
  },
  revoked: {
    title: "设备授权已被撤销",
    body: "服务器不再接受这台设备的令牌。请在服务器上生成新的配对码，重新完成一次配对。",
  },
  "pairing-unsupported": {
    title: "这个地址上没有配对接口",
    body: "服务器回答说它不提供配对端点，或者看不懂这个配对请求。多半是服务端还没升级到带配对功能的版本，或者这个地址指向的是只提供只读分析的旧网关。请先在服务器上确认配对端点已经上线，再回来重试；反复输入配对码不会有任何帮助。",
  },
  "client-not-allowed": {
    title: "服务器不接受来自这台设备的请求",
    body: "请求在到达配对接口之前就被服务器的来源白名单挡下了，和配对码本身无关。请在服务器上把这台手机所在的网络加入允许列表，或者确认手机连的是正确的服务器地址。",
  },
  "insecure-origin": {
    title: "服务器地址不是 HTTPS",
    body: "配对码和令牌只允许走加密连接。当前配置的服务器地址不是 HTTPS，配对请求已被拒绝发出。",
  },
  "not-configured": {
    title: "尚未配置服务器地址",
    body: "这台设备还不知道要连接哪一个服务器。请先配置分析服务的地址，再回到这里配对。",
  },
  offline: {
    title: "连不上服务器",
    body: "配对请求没有送达服务器。请检查网络或服务器是否在运行，然后重试。",
  },
  timeout: {
    title: "服务器响应超时",
    body: "配对请求在超时前没有等到回应。服务器可能正忙，请稍后重试。",
  },
  server: {
    title: "服务器内部错误",
    body: "服务器返回了错误，配对没有完成。请查看服务器日志确认原因后重试。",
  },
  malformed: {
    title: "服务器返回了无法识别的内容",
    body: "配对响应不符合约定格式，应用已拒绝保存其中的任何内容。请确认连接的确实是本项目的服务。",
  },
  "secure-store-unavailable": {
    title: "设备安全存储不可用",
    body: "令牌必须存入 iOS 钥匙串。当前构建缺少安全存储模块，为避免明文保存，配对已中止。",
  },
  "stored-credential-unreadable": {
    title: "已保存的配对信息无法读取",
    body: "钥匙串里的配对信息已损坏或格式不符。请重新配对一次，覆盖掉这份无法解析的记录。",
  },
  unexpected: {
    title: "配对过程出现未预期的错误",
    body: "配对没有完成，应用没有保存任何令牌。请重试；若反复出现，请查看服务器日志。",
  },
};

/**
 * The retry delay is only ever the one the server stated. When the server gives
 * no delay the copy says so, because a number invented here would send the
 * reader back at exactly the wrong moment and deepen the lockout.
 */
export function describePairingFailure({
  reason,
  retryAfterSeconds,
}: {
  reason: PairingFailureReason;
  retryAfterSeconds?: number | null;
}): PairingFailureCopy {
  const copy = copyByReason[reason];
  if (!copy) {
    throw new Error(`unknown pairing failure reason`);
  }
  if (reason !== "rate-limited") return copy;
  return {
    title: copy.title,
    body:
      retryAfterSeconds === undefined || retryAfterSeconds === null
        ? `${copy.body}服务器没有给出可以重试的时间，请稍后再试。`
        : `${copy.body}请在 ${retryAfterSeconds} 秒后再试。`,
  };
}
