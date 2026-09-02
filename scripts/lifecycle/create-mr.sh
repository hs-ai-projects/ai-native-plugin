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
PYTHON="$("$SCRIPT_DIR/../bootstrap/ensure-python-deps.sh")"

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

# ── 3.2 契约收敛闸门（spec 3.2.4 / 7.15，挂在建 MR 这一侧）────────────
# 带 contract.json 的任务必须"对齐已确认且本地状态收敛"才能建 MR；未确认 exit 2。
# 真实运行设 CREATE_MR_FEISHU_CONVERGE=1 时先调 partner.py gather 把群里最新确认
# 收敛回本地（dry-run 不做飞书查询，仅本地校验）。
contract_file="$PWD/.ai-devflow/$task_id/contract.json"
if [ -f "$contract_file" ]; then
  if [ "$dry_run" != "1" ] && [ "${CREATE_MR_FEISHU_CONVERGE:-0}" = "1" ]; then
    "$PYTHON" "$SCRIPT_DIR/../collab/partner.py" gather "$task_id" --dir "$PWD" >/dev/null 2>&1 || true
  fi
  gate_out=$("$PYTHON" - "$contract_file" "$PWD/.ai-devflow/$task_id/contract-state.json" <<'PY' 2>/dev/null || echo "BAD"
import json, os, sys
c = json.load(open(sys.argv[1]))
meta = (c.get("meta") or {}).get("version") or ""
sp = sys.argv[2]
if not os.path.isfile(sp):
    print("MISSING_STATE")
    raise SystemExit(0)
s = json.load(open(sp))
status = s.get("status") or ""
ack = s.get("ack_version") or ""
if status == "aligned" and ack and ack == meta:
    print("OK")
else:
    print(f"BAD status={status} ack={ack} meta={meta}")
PY
)
  case "$gate_out" in
    OK) ;;
    MISSING_STATE)
      echo "ERROR: contract.json 存在但没有 contract-state.json —— 该任务未完成 3.2 阶段0 对齐/确认" >&2
      exit 2 ;;
    *)
      echo "ERROR: 契约未确认收敛（spec 3.2.4）：$gate_out" >&2
      echo "  需先在群里完成 [cc-task $task_id][contract ...] 确认，或用 partner.py gather 收敛后再建 MR。" >&2
      exit 2 ;;
  esac
fi

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
