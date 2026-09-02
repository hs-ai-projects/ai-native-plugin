#!/bin/bash
# verify_runner 的集成单测：必胜 / 必败 / 缺命令层 / 非法 harness / timeout 超时。
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$ROOT/scripts/verify_runner.py"
PYTHON="$("$ROOT/scripts/ensure-python-deps.sh")"
[ -n "$PYTHON" ] || { echo "SKIP: ensure-python-deps failed"; exit 0; }

# Windows：git-bash 的 /tmp 与 /c/... 路径原生 Windows python 读不到，统一转 C:/... 形式；
# Linux 无 cygpath 保持原生路径。
to_win() { command -v cygpath >/dev/null 2>&1 && cygpath -m "$1" || echo "$1"; }
runner_win=$(to_win "$RUNNER")
root=$(mktemp -d)
root_win=$(to_win "$root")
trap 'rm -rf "$root"' EXIT

# 1) 必胜 repo：unit_cmd 成功 → verification.json PASS
mkdir -p "$root/pass"
cat > "$root/pass/harness.yaml" <<'YAML'
project:
  name: pass
  stack:
    type: backend
    backend_unit_cmd: "python3 -c 'print(1)'"
gates:
  fast: [unit]
  full: [unit, contract]
YAML
"$PYTHON" "$runner_win" "$root_win/pass" >/dev/null 2>&1
[ "$("$PYTHON" -X utf8 -c "import json; print(json.load(open(r'$root_win/pass/.ai-devflow/verification.json'))['result'])")" = "PASS" ] \
  && echo "PASS-repo: OK" || { echo "PASS-repo: FAILED"; exit 1; }

# 2) 必败 repo：unit_cmd 失败 → FAIL + failures + evidence log
mkdir -p "$root/fail"
cat > "$root/fail/harness.yaml" <<'YAML'
project:
  name: fail
  stack:
    type: frontend
    frontend_unit_cmd: "no-such-command --definitely-fail"
gates:
  full: [unit]
YAML
"$PYTHON" "$runner_win" "$root_win/fail" >/dev/null 2>&1
v="$root_win/fail/.ai-devflow/verification.json"
"$PYTHON" - "$v" <<'PY' 2>/dev/null || exit 1
import json, os, sys
d = json.load(open(sys.argv[1]))
assert d['result'] == 'FAIL', 'expected FAIL'
assert d['failures'] and d['failures'][0]['owner_hint'] == 'frontend'
assert d['failures'][0].get('subtype') == 'assertion_failed', d['failures'][0]
assert 'evidence' in d['failures'][0] and 'log' in d['failures'][0]['evidence']
assert os.path.exists(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), d['failures'][0]['evidence']['log']))
print("FAIL-repo: OK")
PY
[ $? -eq 0 ] || { echo "FAIL-repo: FAILED"; exit 1; }

# 3) 缺命令层：contract 未配置 → NOT_RUN，整体仍 PASS
mkdir -p "$root/noconf"
cat > "$root/noconf/harness.yaml" <<'YAML'
project:
  name: noconf
  stack:
    type: backend
    backend_unit_cmd: "true"
gates:
  full: [unit, contract]
YAML
"$PYTHON" "$runner_win" "$root_win/noconf" >/dev/null 2>&1
"$PYTHON" - "$root_win/noconf/.ai-devflow/verification.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d['result'] == 'PASS'
assert d['tests']['contract']['result'] == 'NOT_RUN'
print("NOT_RUN-layer: OK")
PY
[ $? -eq 0 ] || { echo "NOT_RUN-layer: FAILED"; exit 1; }

# 4) 非法 harness（缺 harness.yaml）→ 退出码 2
if "$PYTHON" "$runner_win" "$root_win/noexist" >/dev/null 2>&1; then
  echo "NO-HARNESS: FAILED (expected exit 2)"; exit 1
else
  echo "NO-HARNESS: OK"
fi

# 5) timeout：VERIFY_TIMEOUT_SECONDS=1 + sleep 5 → result=ERROR, subtype=timeout
mkdir -p "$root/slow"
cat > "$root/slow/harness.yaml" <<'YAML'
project:
  name: slow
  stack:
    type: backend
    backend_unit_cmd: "sleep 5"
gates:
  full: [unit]
YAML
VERIFY_TIMEOUT_SECONDS=1 "$PYTHON" "$runner_win" "$root_win/slow" >/dev/null 2>&1
"$PYTHON" - "$root_win/slow/.ai-devflow/verification.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
u = d['tests']['unit']
assert u['result'] == 'ERROR', f"expected ERROR, got {u['result']}"
assert u['subtype'] == 'timeout', f"expected timeout, got {u.get('subtype')}"
print("TIMEOUT-layer: OK")
PY
[ $? -eq 0 ] || { echo "TIMEOUT-layer: FAILED"; exit 1; }

echo "test_full_verify: ALL OK"
