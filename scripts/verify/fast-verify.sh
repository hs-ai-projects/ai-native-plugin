#!/bin/bash
# fast-verify.sh <repo_dir>
# 读取 <repo_dir>/harness.yaml，执行 gates.fast（单元测试），PASS=退出0，FAIL=退出1。
# python 一律走插件 venv（ensure-python-deps.sh），不假设系统已装 PyYAML。
set -u

repo_dir="${1:?usage: fast-verify.sh <repo_dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$("$SCRIPT_DIR/../bootstrap/ensure-python-deps.sh")"
harness="$repo_dir/harness.yaml"

[ -f "$harness" ] || { echo "[fast-verify] FAIL: no harness.yaml in $repo_dir"; exit 1; }

stack_type=$("$PYTHON" -c "import yaml; print(yaml.safe_load(open('$harness'))['project']['stack']['type'])" 2>/dev/null)
case "$stack_type" in
  frontend) key="frontend_unit_cmd" ;;
  backend)  key="backend_unit_cmd" ;;
  *)
    echo "[fast-verify] FAIL: unknown stack.type '$stack_type' in $harness"; exit 1
    ;;
esac

# 一次提取 + 判空：缺/空 key → python exit 3 → FAIL exit 1，确保 eval "" 永不发生
cmd=$("$PYTHON" -c "
import sys, yaml
d = yaml.safe_load(open('$harness'))
v = d['project']['stack'].get('$key')
if not v:
    sys.exit(3)
print(v)
") || { echo "[fast-verify] FAIL: missing/empty project.stack.$key in $harness"; exit 1; }

echo "[fast-verify] $repo_dir :: $cmd"
if ( cd "$repo_dir" && eval "$cmd" >/dev/null 2>&1 ); then
  echo "[fast-verify] PASS: $repo_dir"
  exit 0
else
  echo "[fast-verify] FAIL: $repo_dir"
  exit 1
fi
