#!/bin/bash
# approval-gate.sh 单测：无标记文件阻止合并、有标记文件放行、无关命令放行。
set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/scripts/hooks/approval-gate.sh"
command -v jq >/dev/null 2>&1 || { echo "SKIP: need jq"; exit 0; }
[ -f "$HOOK" ] || { echo "approval-gate.sh missing"; exit 1; }
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
export APPROVAL_BASE="$root"

echo '{"tool_input":{"command":"bash finish-task.sh t1 repo /app/repo-t1 http://x"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "block without approval: OK" || { echo "block without approval: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

mkdir -p "$root/t1"
touch "$root/t1/HUMAN_APPROVED"
echo '{"tool_input":{"command":"bash finish-task.sh t1 repo /app/repo-t1 http://x"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow with approval: OK" || { echo "allow with approval: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo '{"tool_input":{"command":"ls -la"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow unrelated command: OK" || { echo "allow unrelated command: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo "test_approval_gate_hook: ALL OK"
