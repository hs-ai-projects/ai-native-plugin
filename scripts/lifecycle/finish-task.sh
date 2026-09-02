#!/bin/bash
# finish-task.sh <task_id> <repo> <sandbox_path> <mr_url>
#
# 任务终态收尾：merge MR + 清理 sandbox + 自动记录真实 token 用量/会话详情。
# 埋点是这个脚本自身固定执行的动作。GitLab 操作统一走 glab CLI（spec 4.3）。
# 去掉评审回路（spec 第 2 节）：MR 评论由用户人工处理，本脚本不检查 glab mr note list。
# Ported from ai-native/scripts/finish-task.sh；HARNESS_SCRIPTS 默认指向 telemetry/
# 子目录（emit-event.py / session-usage.py 所在），python 一律走插件 venv。
set -euo pipefail

task_id="${1:?usage: finish-task.sh <task_id> <repo> <sandbox_path> <mr_url>}"
repo="${2:?repo required}"
sandbox_path="${3:?sandbox_path required}"
mr_url="${4:?mr_url required}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$("$SCRIPT_DIR/../bootstrap/ensure-python-deps.sh")"
HARNESS_SCRIPTS="${HARNESS_SCRIPTS:-$SCRIPT_DIR/../telemetry}"

glab mr merge "$mr_url" --yes --remove-source-branch \
  || { echo "ERROR: glab mr merge failed" >&2; exit 1; }

git -C "$sandbox_path" worktree remove --force "$sandbox_path" \
  || echo "[finish-task] warning: worktree remove failed for $sandbox_path"

"$PYTHON" "$HARNESS_SCRIPTS/emit-event.py" mr_merged --task-id "$task_id" --repo "$repo" || true

usage_json=$("$PYTHON" "$HARNESS_SCRIPTS/session-usage.py" report "$task_id" 2>/tmp/session-usage-err.log) \
  || { echo "[finish-task] warning: session-usage.py failed, skipping cost event"; cat /tmp/session-usage-err.log >&2; usage_json=""; }
if [ -n "$usage_json" ]; then
  "$PYTHON" "$HARNESS_SCRIPTS/emit-event.py" cost --task-id "$task_id" --repo "$repo" --data "$usage_json" || true
fi

"$PYTHON" "$HARNESS_SCRIPTS/emit-event.py" state_change --task-id "$task_id" --repo "$repo" \
  --data '{"state":"done"}' || true

echo "[finish-task] task $task_id done: MR merged, sandbox cleaned, usage recorded"
