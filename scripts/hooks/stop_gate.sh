#!/usr/bin/env bash
# Stop hook：会话想结束时自动跑与改动相关的测试；不通过就打回去继续修。
# 这是自动迭代的质量门禁，靠机器而不是靠模型自觉。
input="$(cat)"

# 防死循环：上一次 Stop 已经被本 hook 打回过，则放行
if grep -q '"stop_hook_active": *true' <<<"$input"; then
  exit 0
fi

cd "$(git rev-parse --show-toplevel)" || exit 0

out="$(bash scripts/test_changed.sh 2>&1)" && exit 0

{
  echo "改动相关测试未全部通过，请修复后再结束（scripts/test_changed.sh 输出末尾）："
  tail -30 <<<"$out"
} >&2
exit 2
