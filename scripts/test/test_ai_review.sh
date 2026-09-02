#!/bin/bash
# ai-review.sh 单测：临时 git repo 验证 review.md 组装（含 diff/AC/verification）。
set -u
AI_REVIEW="$(cd "$(dirname "$0")/../.." && pwd)/scripts/ai-review.sh"
root=$(mktemp -d)
# Windows：git-bash 的 /tmp 路径原生 Windows python 读不到，转 C:/... 形式；Linux 无 cygpath 保持原生。
command -v cygpath >/dev/null 2>&1 && root=$(cygpath -m "$root")
trap 'rm -rf "$root"' EXIT

git -C "$root" init -q repo
git -C "$root/repo" config user.email t@t
git -C "$root/repo" config user.name t
echo "a" > "$root/repo/a.txt"
git -C "$root/repo" add a.txt
git -C "$root/repo" commit -q -m init
git -C "$root/repo" checkout -q -b task/demo/1
echo "b" > "$root/repo/b.txt"
git -C "$root/repo" add b.txt
git -C "$root/repo" commit -q -m "add b"

mkdir -p "$root/.ai-devflow/demo" "$root/repo/.ai-devflow"
cat > "$root/.ai-devflow/demo/SPEC.md" <<'MD'
## 2. Acceptance Criteria
- AC-01: 有改动
MD
echo '{"result":"PASS","tests":{"unit":{"result":"PASS"}}}' > "$root/repo/.ai-devflow/verification.json"

if ! SPEC_FILE="$root/.ai-devflow/demo/SPEC.md" REVIEW_DIR="$root/.ai-devflow/demo" \
     bash "$AI_REVIEW" "$root/repo" "demo" >/dev/null 2>&1; then
  echo "ai-review: FAILED"; exit 1
fi
grep -q "AC-01" "$root/.ai-devflow/demo/review.md" && echo "AC in review: OK" || { echo "AC missing"; exit 1; }
grep -q "result=PASS" "$root/.ai-devflow/demo/review.md" && echo "verification in review: OK" || { echo "verification missing"; exit 1; }
grep -q "b.txt" "$root/.ai-devflow/demo/review.md" && echo "diff file in review: OK" || { echo "diff file missing"; exit 1; }

# REVIEW.md 动态清单 + review.json 产出
cat > "$root/policy.md" <<'MD'
# Review Policy
## Critical
- [ ] AC 必须有测试覆盖
MD
mkdir -p "$root/.ai-devflow/demo2"
git -C "$root" init -q repo2
git -C "$root/repo2" config user.email t@t
git -C "$root/repo2" config user.name t
echo "a" > "$root/repo2/a.txt"
git -C "$root/repo2" add a.txt
git -C "$root/repo2" commit -q -m init
mkdir -p "$root/repo2/.ai-devflow"
cat > "$root/.ai-devflow/demo2/SPEC.md" <<'MD'
## 2. Acceptance Criteria
- AC-01: 有改动
MD
echo '{"result":"PASS"}' > "$root/repo2/.ai-devflow/verification.json"
if ! SPEC_FILE="$root/.ai-devflow/demo2/SPEC.md" REVIEW_DIR="$root/.ai-devflow/demo2" \
     REVIEW_POLICY="$root/policy.md" \
     bash "$AI_REVIEW" "$root/repo2" "demo2" >/dev/null 2>&1; then
  echo "REVIEW-policy run: FAILED"; exit 1
fi
grep -q "AC 必须有测试覆盖" "$root/.ai-devflow/demo2/review.md" \
  && echo "policy checklist in review: OK" || { echo "policy checklist missing"; exit 1; }
[ -f "$root/.ai-devflow/demo2/review.json" ] \
  && grep -q '"verdict": "PENDING"' "$root/.ai-devflow/demo2/review.json" \
  && echo "review.json: OK" || { echo "review.json missing or no PENDING verdict"; exit 1; }

echo "test_ai_review: ALL OK"
