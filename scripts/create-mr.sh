#!/bin/bash
# create-mr.sh <sandbox_path> <task_id> [--dry-run]
# push sandbox 分支 + 用 glab 创建 MR（描述带 AC + verification + review 摘要）。
# --dry-run：只打印将执行的命令和 MR 描述，不实际 push / mr create。
# GitLab 操作统一走 glab CLI（spec 4.3），不直接拼 GitLab REST API。
# Ported from ai-native/scripts/create-mr.sh；默认产物路径改为仓库相对 .ai-devflow。
set -euo pipefail

sandbox_path="${1:?usage: create-mr.sh <sandbox_path> <task_id> [--dry-run]}"
task_id="${2:?task_id required}"
dry_run=0
if [ -n "${3:-}" ]; then
  [ "$3" = "--dry-run" ] || { echo "ERROR: unknown arg: $3 (only --dry-run)" >&2; exit 1; }
  dry_run=1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$("$SCRIPT_DIR/ensure-python-deps.sh")"

branch=$(git -C "$sandbox_path" rev-parse --abbrev-ref HEAD)
spec="${SPEC_FILE:-$PWD/.ai-devflow/$task_id/SPEC.md}"
review="${REVIEW_FILE:-$PWD/.ai-devflow/$task_id/review.md}"
ver_file="$sandbox_path/.ai-devflow/verification.json"
target=$(git -C "$sandbox_path" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || true)
target="${target:-master}"

title="[$task_id] $(head -1 "$spec" 2>/dev/null | sed 's/^# //' | sed "s/SPEC: //" || true)"

body=$(cat <<BODY
## 任务
$task_id

## Acceptance Criteria（SPEC 第 2 章）
$(grep -E '^\s*-?\s*AC-[0-9]+' "$spec" 2>/dev/null)

## Verification
$(if [ -f "$ver_file" ]; then "$PYTHON" - "$ver_file" <<'PY' 2>/dev/null || echo "(verification unreadable)"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"result={d.get('result')} tests={ {k: v.get('result') for k, v in d.get('tests', {}).items()} }")
print(f"failures={len(d.get('failures', []))}")
PY
fi)

## AI Review 摘要
$(head -8 "$review" 2>/dev/null)
BODY
)

if [ "$dry_run" = "1" ]; then
  echo "=== DRY-RUN: 将执行 ==="
  echo "git -C $sandbox_path push -u origin $branch"
  echo "( cd $sandbox_path && glab mr create --source-branch $branch --target-branch $target --title \"$title\" --description \"$body\" -y )"
  echo "=== MR 描述 ==="
  echo "$body"
  exit 0
fi

git -C "$sandbox_path" push -u origin "$branch" || { echo "ERROR: push failed" >&2; exit 1; }
mr_out=$( ( cd "$sandbox_path" && glab mr create --source-branch "$branch" --target-branch "$target" --title "$title" --description "$body" -y ) 2>&1 ) \
  || { echo "ERROR: glab mr create failed" >&2; echo "$mr_out" >&2; exit 1; }
echo "$mr_out"
url=$(echo "$mr_out" | grep -oE 'https?://[^ ]+/merge_requests/[0-9]+' | head -1 || true)
if [ -n "$url" ]; then
  echo "MR_URL=$url"
fi
echo "MR created for branch $branch"
