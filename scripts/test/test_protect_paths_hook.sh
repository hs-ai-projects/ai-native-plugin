#!/bin/bash
# protect-paths.sh 单测：受保护路径阻止、普通文件放行。
set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/scripts/hooks/protect-paths.sh"
command -v jq >/dev/null 2>&1 || { echo "SKIP: need jq"; exit 0; }
[ -f "$HOOK" ] || { echo "protect-paths.sh missing"; exit 1; }

echo '{"tool_input":{"file_path":"/app/repo/.ai-devflow/verification.json"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "block .ai-devflow: OK" || { echo "block .ai-devflow: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo '{"tool_input":{"file_path":"/app/repo/harness.yaml"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "block harness.yaml: OK" || { echo "block harness.yaml: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo '{"tool_input":{"file_path":"/app/repo/src/app.py"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow normal file: OK" || { echo "allow normal file: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo "test_protect_paths_hook: ALL OK"
