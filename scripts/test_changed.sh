#!/usr/bin/env bash
# 只跑与当前改动相关的测试套件，作为每轮迭代的退出门禁。
# 用法: bash scripts/test_changed.sh [base-ref]   (默认 origin/feature/iphone-demo)
# 改动范围 = base-ref...HEAD 的提交差异 + 工作区改动 + 未跟踪新文件。
# 输出纪律（机制强制）：完整日志写入 test_changed.log；屏幕上成功只打印摘要行，
# 失败只打印末尾 25 行 —— 避免把大段测试输出灌进 agent 上下文。
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

BASE="${1:-origin/feature/iphone-demo}"
changed="$( { git diff --name-only "$BASE"...HEAD 2>/dev/null; git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard; } | sort -u)"

if [ -z "$changed" ]; then
  echo "test_changed: 没有检测到改动，无事可做"
  exit 0
fi

LOG="test_changed.log"
: >"$LOG"
fail=0
ran=0

# run_suite <标签> <命令...>：完整输出进 $LOG；成功打印末行摘要，失败打印末尾 25 行
run_suite() {
  local label="$1"; shift
  ran=1
  echo "=== $label ===" | tee -a "$LOG"
  local out
  if out="$("$@" 2>&1)"; then
    printf '%s\n' "$out" >>"$LOG"
    printf '%s\n' "$out" | tail -1
  else
    printf '%s\n' "$out" >>"$LOG"
    printf '%s\n' "$out" | tail -25
    fail=1
  fi
}

for svc in services/*/; do
  name="$(basename "$svc")"
  if grep -q "^services/$name/" <<<"$changed"; then
    python3 -m pip install -q -e "$svc" >>"$LOG" 2>&1 || { echo "install $name 失败，见 $LOG"; fail=1; continue; }
    run_suite "services/$name" python3 -m pytest "${svc%/}/tests" -q
  fi
done

# deploy/ 与 scripts/ 的套件面向 macOS；仅在 Darwin 上作为门禁
if [ "$(uname)" = "Darwin" ]; then
  for extra in deploy scripts; do
    if grep -q "^$extra/" <<<"$changed"; then
      run_suite "$extra" python3 -m pytest "$extra/tests" -q
    fi
  done
elif grep -qE "^(deploy|scripts)/" <<<"$changed"; then
  echo "test_changed: 改动涉及 deploy/ 或 scripts/，其套件面向 macOS，本机($(uname))跳过 —— 需在 macOS 上验证"
fi

if grep -q "^apps/mobile/" <<<"$changed"; then
  if [ -d apps/mobile/node_modules ]; then
    run_suite "apps/mobile typecheck" bash -c 'cd apps/mobile && npm run typecheck'
    run_suite "apps/mobile jest" bash -c 'cd apps/mobile && npm test'
  else
    echo "test_changed: apps/mobile/node_modules 缺失，先运行 npm ci（CI 中会自动跑）"
    fail=1
  fi
fi

if [ "$ran" = 0 ]; then
  echo "test_changed: 改动不涉及任何测试套件覆盖的目录，改动文件如下："
  echo "$changed"
fi

if [ "$fail" = 1 ]; then
  echo "test_changed: 存在失败，完整日志见 $LOG"
fi
exit $fail
