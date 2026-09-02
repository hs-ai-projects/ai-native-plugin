#!/bin/bash
# ai-review.sh <sandbox_path> <task_id>
# 生成 AI Review 包：diff stat + 改动文件 vs base + SPEC AC 清单 + verification 摘要 +
# policies/REVIEW.md 动态检查清单（人读 review.md）+ 机读 review.json。
# 判断由编排 Skill（Claude）基于 review.md/review.json 完成，本脚本只产出事实。
# Ported from ai-native/scripts/ai-review.sh；默认路径改为仓库相对 .ai-devflow，
# checklist 从硬编码改为动态解析插件自带 policies/REVIEW.md，并产出 review.json。
set -euo pipefail

sandbox_path="${1:?usage: ai-review.sh <sandbox_path> <task_id>}"
task_id="${2:?task_id required}"
[ -d "$sandbox_path/.git" ] || [ -f "$sandbox_path/.git" ] || { echo "ERROR: not a git repo: $sandbox_path" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$("$SCRIPT_DIR/../bootstrap/ensure-python-deps.sh")"

spec="${SPEC_FILE:-$PWD/.ai-devflow/$task_id/SPEC.md}"
review_dir="${REVIEW_DIR:-$PWD/.ai-devflow/$task_id}"
mkdir -p "$review_dir"

# 动态检查清单：解析 policies/REVIEW.md 的 "- [ ]" 行（Critical/Important/Nit 各级）；
# 文件缺失或没有清单行时回退默认清单。
review_policy="${REVIEW_POLICY:-$SCRIPT_DIR/../../policies/REVIEW.md}"
checklist_md=""
if [ -f "$review_policy" ]; then
  checklist_md=$(grep -E '^- \[ \]' "$review_policy" || true)
fi
if [ -z "$checklist_md" ]; then
  checklist_md=$(cat <<'DEFAULT'
- [ ] 改动范围与 SPEC Task 一致，无越界文件
- [ ] 每条 AC 有对应改动或测试
- [ ] 无明显坏味道 / 未处理错误分支
- [ ] verification 结果是真实执行（非全 NOT_RUN 堆叠）
DEFAULT
)
fi

base_ref=$(git -C "$sandbox_path" rev-parse master 2>/dev/null || git -C "$sandbox_path" rev-parse main 2>/dev/null || echo "HEAD~1")
diff_stat=$(git -C "$sandbox_path" diff --stat "$base_ref" 2>/dev/null | tail -20 || echo "(no base diff)")
files=$(git -C "$sandbox_path" diff --name-only "$base_ref" 2>/dev/null || echo "")
ac_list=$(grep -E '^\s*-?\s*AC-[0-9]+' "$spec" 2>/dev/null || echo "(no AC found in SPEC)")

ver_file="$sandbox_path/.ai-devflow/verification.json"
ver_summary="(no verification)"
if [ -f "$ver_file" ]; then
  ver_summary=$("$PYTHON" - "$ver_file" <<'PY' 2>/dev/null || echo "(verification unreadable)"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"result={d.get('result')} tests={ {k: v.get('result') for k, v in d.get('tests', {}).items()} }")
PY
)
fi

cat > "$review_dir/review.md" <<MD
# AI Review: $task_id

## 改动范围（vs $base_ref）
$diff_stat

## 改动文件
$files

## Acceptance Criteria（SPEC 第 2 章）
$ac_list

## Verification 摘要
$ver_summary

## 检查清单（Team Lead 基于以上评估）
$checklist_md
MD

cat > "$review_dir/review.json" <<JSON
{
  "verdict": "PENDING",
  "critical": [],
  "important": [],
  "nits": [],
  "spec_compliance": null
}
JSON

echo "review pack written: $review_dir/review.md + review.json"
