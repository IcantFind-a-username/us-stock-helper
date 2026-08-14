#!/usr/bin/env bash
# 只跑与当前改动相关的测试套件，作为每轮迭代的退出门禁。
# 用法: bash scripts/test_changed.sh [base-ref]   (默认 origin/feature/iphone-demo)
# 改动范围 = base-ref...HEAD 的提交差异 + 工作区未提交改动。
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

BASE="${1:-origin/feature/iphone-demo}"
changed="$( { git diff --name-only "$BASE"...HEAD 2>/dev/null; git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard; } | sort -u)"

if [ -z "$changed" ]; then
  echo "test_changed: 没有检测到改动，无事可做"
  exit 0
fi

fail=0
ran=0

for svc in services/*/; do
  name="$(basename "$svc")"
  if grep -q "^services/$name/" <<<"$changed"; then
    ran=1
    echo "=== services/$name ==="
    python3 -m pip install -q -e "$svc" || { fail=1; continue; }
    python3 -m pytest "${svc%/}/tests" -q || fail=1
  fi
done

# deploy/ 与 scripts/ 的套件面向 macOS；仅在 Darwin 上作为门禁
if [ "$(uname)" = "Darwin" ]; then
  for extra in deploy scripts; do
    if grep -q "^$extra/" <<<"$changed"; then
      ran=1
      echo "=== $extra ==="
      python3 -m pytest "$extra/tests" -q || fail=1
    fi
  done
elif grep -qE "^(deploy|scripts)/" <<<"$changed"; then
  echo "test_changed: 改动涉及 deploy/ 或 scripts/，其套件面向 macOS，本机($(uname))跳过 —— 需在 macOS 上验证"
fi

if grep -q "^apps/mobile/" <<<"$changed"; then
  ran=1
  echo "=== apps/mobile ==="
  if [ -d apps/mobile/node_modules ]; then
    (cd apps/mobile && npm run typecheck && npm test) || fail=1
  else
    echo "test_changed: apps/mobile/node_modules 缺失，先运行 npm ci（CI 中会自动跑）"
    fail=1
  fi
fi

if [ "$ran" = 0 ]; then
  echo "test_changed: 改动不涉及任何测试套件覆盖的目录，改动文件如下："
  echo "$changed"
fi

exit $fail
