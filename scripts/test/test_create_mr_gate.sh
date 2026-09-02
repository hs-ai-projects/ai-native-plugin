#!/bin/bash
# create-mr.sh 契约收敛闸门（spec 3.2.4 / 7.15）：
# 带 contract.json 的任务，本地状态未收敛到 aligned+ack==meta.version 时 dry-run 也被拦（exit 2）。
set -u
CREATE_MR="$(cd "$(dirname "$0")/../.." && pwd)/scripts/lifecycle/create-mr.sh"
root=$(mktemp -d)
command -v cygpath >/dev/null 2>&1 && root=$(cygpath -m "$root")
trap 'rm -rf "$root"' EXIT

git -C "$root" init -q repo
git -C "$root/repo" config user.email t@t
git -C "$root/repo" config user.name t
echo a > "$root/repo/a.txt"
git -C "$root/repo" add a.txt
git -C "$root/repo" commit -q -m init
git -C "$root/repo" checkout -q -b task/demo/1

mkdir -p "$root/.ai-devflow/demo" "$root/repo/.ai-devflow"
printf '# SPEC: demo\n## 2. Acceptance Criteria\n- AC-01: x\n' > "$root/.ai-devflow/demo/SPEC.md"
printf '# review\n' > "$root/.ai-devflow/demo/review.md"
echo '{"result":"PASS","failures":[]}' > "$root/repo/.ai-devflow/verification.json"
export SPEC_FILE="$root/.ai-devflow/demo/SPEC.md"
export REVIEW_FILE="$root/.ai-devflow/demo/review.md"

cat > "$root/.ai-devflow/demo/contract.json" <<'J'
{"api":[{"path":"/api/x","method":"GET"}],"meta":{"version":"1.0"}}
J

# 1) 有 contract.json 但没有 contract-state.json → 拦截
out=$(cd "$root" && "$CREATE_MR" "$root/repo" "demo" --dry-run 2>&1 || true)
echo "$out" | grep -q "contract-state.json" && echo "missing-state gate: OK" || { echo "missing-state gate FAILED"; exit 1; }

# 2) state 存在但未收敛（pending / ack 缺失）→ 拦截
printf '{"task_id":"demo","status":"pending","ack_version":null,"pending_version":null,"last_cursor_ms":0}\n' > "$root/.ai-devflow/demo/contract-state.json"
out=$(cd "$root" && "$CREATE_MR" "$root/repo" "demo" --dry-run 2>&1 || true)
echo "$out" | grep -qE "未确认收敛|3.2.4" && echo "pending gate: OK" || { echo "pending gate FAILED"; exit 1; }

# 3) state 对齐但 ack_version != meta.version（漂移未收敛）→ 拦截
printf '{"task_id":"demo","status":"aligned","ack_version":"1.0","pending_version":null,"last_cursor_ms":0}\n' > "$root/.ai-devflow/demo/contract-state.json"
sed -i 's/"version":"1.0"/"version":"1.1"/' "$root/.ai-devflow/demo/contract.json"
out=$(cd "$root" && "$CREATE_MR" "$root/repo" "demo" --dry-run 2>&1 || true)
echo "$out" | grep -qE "未确认收敛|meta=" && echo "drift gate: OK" || { echo "drift gate FAILED"; exit 1; }

# 4) 收敛一致（aligned + ack==meta 1.1）→ 放行
printf '{"task_id":"demo","status":"aligned","ack_version":"1.1","pending_version":null,"last_cursor_ms":0}\n' > "$root/.ai-devflow/demo/contract-state.json"
out=$(cd "$root" && "$CREATE_MR" "$root/repo" "demo" --dry-run 2>&1 || true)
echo "$out" | grep -q "DRY-RUN" && echo "aligned pass: OK" || { echo "aligned pass FAILED"; exit 1; }

echo "test_create_mr_gate: ALL OK"
