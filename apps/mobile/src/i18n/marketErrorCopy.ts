import type { MarketDataErrorCategory } from "@/data/marketRepository";

/**
 * What each transport failure says to the person holding the phone.
 *
 * The screens used to print the category identifier — `malformed`, `offline` —
 * straight into a Text node, which named the failure to nobody: the reader
 * reads Chinese, and even in English "malformed" describes a broken payload,
 * which most of these are not.
 *
 * Every entry answers three questions, because a failure the reader cannot act
 * on is barely better than a blank cell: what was refused, who refused it, and
 * what to do next. Where the answer to the last one is "nothing, this is not
 * yours to fix", the copy says exactly that instead of implying an action.
 */
export type MarketErrorCopy = {
  /** For the watchlist score column: at most five characters at 8pt type. */
  label: string;
  /** One sentence naming the failure, used for spoken labels and headings. */
  title: string;
  /** What was refused, by whom, and what the reader should do about it. */
  body: string;
};

const COPY: Record<MarketDataErrorCategory, MarketErrorCopy> = {
  "analysis-failed": {
    label: "分析失败",
    title: "分析服务没能算出结论",
    body: "服务端明确回答这只标的的决策链没跑完，但没有说明卡在哪一步——它不会把上游的原始错误原文透传出来，因为那段文字可能带有账号信息。这不是你的操作问题。打开这只标的的个股页，行情那一栏通常会写明具体原因。",
  },
  "auth-required": {
    label: "需配对",
    title: "这台手机的配对令牌已失效",
    body: "服务端不认这台设备的令牌：可能从未配对过，也可能令牌已被撤销或过期。请在服务器上重新生成配对码，回到「配对设备」重配一次。这与券商账号是否登录无关。",
  },
  "auth-unavailable": {
    label: "凭据故障",
    title: "服务端读不到存放设备令牌的库",
    body: "服务器上保存设备身份的数据库暂时无法读取，所以它无法确认这台手机是谁。服务端选择拒绝而不是放行，这是对的。这不是你的操作问题，需要在服务器上查日志排查后重试。",
  },
  "client-not-allowed": {
    label: "网络受限",
    title: "服务端不接受来自这台设备的请求",
    body: "请求在进入接口之前就被服务端的来源白名单挡下了，和行情权限无关。请确认手机连的是正确的服务器地址，或者在服务器上把这部手机所在的网段加进允许列表。",
  },
  configuration: {
    label: "未配置",
    title: "这台设备还没有配置服务地址",
    body: "App 不知道该连哪一个服务。请先填好行情网关与分析服务的地址再回到这里。在配好之前，App 不会拿演示数据顶替真实行情。",
  },
  contract: {
    label: "网关过旧",
    title: "网关返回的字段比本版 App 需要的少",
    body: "网关还在用旧的接口版本，缺了 App 需要的字段。App 拒绝按猜测把缺失的字段补齐。请更新本机网关服务后重试；不会自动切换成演示数据。",
  },
  "invalid-request": {
    label: "参数被拒",
    title: "服务端不接受这次请求的参数",
    body: "App 发出的标的代码、周期或数量被服务端判定为非法。这几乎总是两端版本不一致造成的。请确认 App 与服务端是同一版本后重试。",
  },
  "login-required": {
    label: "未登录",
    title: "OpenD 还没有登录券商账号",
    body: "行情网关连上了 OpenD，但 OpenD 自己还没登录，因此拿不到任何行情。请在运行 OpenD 的那台机器上完成登录后重试。App 不保存也不代填任何账号凭据。",
  },
  // MALFORMED_PROVIDER_DATA covers roughly twenty distinct checks — missing
  // quote fields, an undeclared price-adjustment basis, a repeated pagination
  // page, out-of-order candles. Naming one of them here would put an
  // explanation on screen that the gateway never made, and the ones that
  // never heal on their own would carry advice to wait that cannot work.
  malformed: {
    label: "数据被拒",
    title: "这只标的的行情数据没通过校验",
    body: "网关检查了数据供应商送来的这份行情，发现它不符合要求，于是拒收了——宁可不显示，也不拿可能不准确的数据给你算结论。网关没有说明具体是哪一项不合格，所以这里不猜。这不是你的操作问题。可以过一会儿再刷新；如果这只标的一直如此，多半是供应商对它的数据本身有缺失，换一只看。",
  },
  offline: {
    label: "连不上",
    title: "连不上行情服务",
    body: "请求没有送达。请确认 OpenD 在运行、手机和服务器在同一个网络里，然后重试。不会自动切换成演示数据。",
  },
  permission: {
    label: "无权限",
    title: "这个账号没有该标的的行情权限",
    body: "OpenD 已经登录，但账号没有订阅这只标的所属市场的行情。请在券商客户端里确认行情权限后重试。",
  },
  "provider-error": {
    label: "上游报错",
    title: "行情源返回了预期之外的错误",
    body: "上游接口回了一个网关无法归类的错误。网关没有转述它的原文，因为那段文字可能带有账号或主机信息。这不是你的操作问题；稍后重试，若一直如此请查看网关日志。",
  },
  "rate-limited": {
    label: "太频繁",
    title: "请求频率超过了行情源的限额",
    body: "短时间内向行情接口发的请求太多，已被限流。等一会儿会自动恢复；少按几次刷新、或者把自选列表收起来，可以恢复得更快。",
  },
  "route-unsupported": {
    label: "接口缺失",
    title: "服务端没有这个接口",
    body: "App 请求的路径或方法在服务端不存在。多半是服务端版本比 App 旧，也可能这个地址指向的根本不是本项目的服务。请核对地址并更新服务端。",
  },
  "sdk-unavailable": {
    label: "缺组件",
    title: "服务端缺少连接行情源所需的组件",
    body: "网关所在的机器上没有装券商的 SDK，它没法向 OpenD 取数。这需要在服务器上装好依赖再重启网关，在这里反复重试不会有帮助。",
  },
  stale: {
    label: "数据过旧",
    title: "行情数据太旧，已被拒收",
    body: "网关拿到的数据超出了允许的时效窗口。App 不显示过期数据，也不会把它当成最新价来用。稍后重试；若一直如此，请检查 OpenD 与行情源之间的连接。",
  },
  timeout: {
    label: "超时",
    title: "服务在超时前没有回应",
    body: "请求已经发出，但没有等到回应。服务器可能正忙，也可能网络不稳。稍后重试即可。",
  },
  unspecified: {
    label: "原因未明",
    title: "服务端说这份数据不可用，却没有给出原因",
    body: "响应里没有带任何错误码，所以 App 说不出原因——这里不做猜测，也不会随便挑一个理由填上。请到服务端日志里查这次请求，或者稍后重试。",
  },
  unsupported: {
    label: "不支持",
    title: "网关不提供这项能力",
    body: "服务端明确回答它没有实现这次请求所需的能力。这通常出现在精简部署上。请确认网关的部署形态，或者换成完整版本。",
  },
  validation: {
    label: "响应异常",
    title: "App 看不懂服务端返回的内容",
    body: "连接是通的，响应也能解析成 JSON，但里面的字段不符合约定。App 拒绝按猜测使用其中任何一部分。请确认连的确实是本项目的服务，并让两端版本保持一致。",
  },
};

/**
 * The copy for one category, or a throw.
 *
 * There is deliberately no fallback string. A category reaches here only from
 * a closed union, so a miss means the union grew and this table did not — and
 * a generic "出错了" in that case would quietly bury the new failure among the
 * ones that already have an explanation.
 */
export function describeMarketError(
  category: MarketDataErrorCategory,
): MarketErrorCopy {
  const copy = COPY[category];
  if (!copy) throw new Error("unknown market error category");
  return copy;
}
