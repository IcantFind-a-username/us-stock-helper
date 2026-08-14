#!/bin/sh
# The foreground supervisor is intentionally retired.  A non-zero exit keeps
# old automation from mistaking this migration notice for a running stack.

printf '%s\n' \
  'run_local_dev_stack.sh is retired; the durable stack is managed by launchd.' \
  'Run: python3 scripts/local_runtime.py install' >&2
exit 2
