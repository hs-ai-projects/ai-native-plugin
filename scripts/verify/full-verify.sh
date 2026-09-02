#!/bin/bash
# full-verify.sh <repo_dir>
# 执行 <repo_dir>/harness.yaml 的 gates.full 各层，汇总 .ai-devflow/verification.json。
# PASS=退出0，FAIL=退出1。
set -u
repo_dir="${1:?usage: full-verify.sh <repo_dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$("$SCRIPT_DIR/../bootstrap/ensure-python-deps.sh")"
exec "$PYTHON" "$SCRIPT_DIR/verify_runner.py" "$repo_dir"
