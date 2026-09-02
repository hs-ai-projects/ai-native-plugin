#!/bin/bash
# create-mr.sh dry-run 单测：不真 push/mr，用 SPEC_FILE/REVIEW_FILE 覆盖指向临时 fixture，验证描述组装。
set -u
CREATE_MR="$(cd "$(dirname "$0")/../.." && pwd)/scripts/create-mr.sh"
root=$(mktemp -d)
# Windows 宿主：git-bash 的 /tmp 路径 Windows Python 读不到，转成 C:/... 形式；
# Linux 宿主无 cygpath，保持原生路径。
command -v cygpath >/dev/null 2>&1 && root=$(cygpath -m "$root")
trap 'rm -rf "$root"' EXIT

git -C "$root" init -q repo
git -C "$root/repo" config user.email t@t
git -C "$root/repo" config user.name t
echo "a" > "$root/repo/a.txt"
git -C "$root/repo" add a.txt
git -C "$root/repo" commit -q -m init
git -C "$root/repo" checkout -q -b task/demo/1

mkdir -p "$root/.ai-devflow/demo" "$root/repo/.ai-devflow"
cat > "$root/.ai-devflow/demo/SPEC.md" <<'MD'
# SPEC: demo Demo 需求
## 2. Acceptance Criteria
- AC-01: 有改动
MD
cat > "$root/.ai-devflow/demo/review.md" <<'MD'
# AI Review: demo
review 内容
MD
echo '{"result":"PASS","failures":[]}' > "$root/repo/.ai-devflow/verification.json"

# SPEC_FILE/REVIEW_FILE 覆盖脚本默认 /app 路径，指向临时目录真实 fixture。
export SPEC_FILE="$root/.ai-devflow/demo/SPEC.md"
export REVIEW_FILE="$root/.ai-devflow/demo/review.md"

out=$("$CREATE_MR" "$root/repo" "demo" --dry-run 2>&1 || true)
echo "$out" | grep -q "DRY-RUN" && echo "dry-run banner: OK" || { echo "dry-run banner missing"; exit 1; }
echo "$out" | grep -q "task/demo/1" && echo "branch in preview: OK" || { echo "branch missing"; exit 1; }
echo "$out" | grep -q "AC-01" && echo "AC-01 in description: OK" || { echo "AC-01 missing"; exit 1; }
echo "$out" | grep -q "result=PASS" && echo "verification PASS: OK" || { echo "result=PASS missing"; exit 1; }
echo "$out" | grep -qE -- '--title "[^"]+"' && echo "non-empty title: OK" || { echo "title missing or empty"; exit 1; }
echo "test_create_mr: ALL OK"
