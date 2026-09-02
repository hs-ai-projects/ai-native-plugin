#!/bin/bash
# devflow-start-task Skill 结构校验：9 步齐全 + Defer 分支 + 模板存在 + 无容器硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/devflow-start-task/SKILL.md"
[ -f "$SKILL" ] || { echo "SKILL.md missing"; exit 1; }

# 调用名 frontmatter
grep -q 'argument-hint' "$SKILL" || { echo "argument-hint missing"; exit 1; }

# 9 步关键内容（按 spec 第 6 节）
grep -q 'intent.md' "$SKILL" || { echo "step1 intent missing"; exit 1; }
grep -q 'Decision: Accept/Reject/Defer' "$SKILL" || { echo "step1 Decision missing"; exit 1; }
grep -q 'worktree add' "$SKILL" || { echo "step4 worktree missing"; exit 1; }
grep -q 'full-verify' "$SKILL" || { echo "step6 verify missing"; exit 1; }
grep -q 'attribute.py' "$SKILL" || { echo "step7 attribute missing"; exit 1; }
grep -q 'repair-counter.py' "$SKILL" || { echo "step7 repair-counter missing"; exit 1; }
grep -q 'ai-review.sh' "$SKILL" || { echo "step8 ai-review missing"; exit 1; }
grep -q 'create-mr.sh' "$SKILL" || { echo "step8 create-mr missing"; exit 1; }
grep -q 'finish-task.sh' "$SKILL" || { echo "step9 finish-task missing"; exit 1; }
grep -q 'HUMAN_APPROVED' "$SKILL" || { echo "step9 approval missing"; exit 1; }
# 前置依赖探测
grep -q 'command -v glab' "$SKILL" || { echo "glab probe missing"; exit 1; }
grep -q 'command -v lark-cli' "$SKILL" || { echo "lark-cli probe missing"; exit 1; }
# 所有脚本路径走 CLAUDE_PLUGIN_ROOT，无 /app 硬编码
grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

# 模板存在且结构正确
for t in INTENT-TEMPLATE SPEC-TEMPLATE CLAUDE-SUPPLEMENT; do
  [ -f "$ROOT/skills/devflow-start-task/templates/$t.md" ] || { echo "templates/$t.md missing"; exit 1; }
done
grep -q '^## 问题' "$ROOT/skills/devflow-start-task/templates/INTENT-TEMPLATE.md" || { echo "INTENT template section missing"; exit 1; }
grep -q '^## 0\. 不可违反原则' "$ROOT/skills/devflow-start-task/templates/SPEC-TEMPLATE.md" || { echo "SPEC template section0 missing"; exit 1; }
grep -q '^### Decision' "$ROOT/skills/devflow-start-task/templates/SPEC-TEMPLATE.md" || { echo "SPEC template Decision missing"; exit 1; }
grep -q '^## 验证工作' "$ROOT/skills/devflow-start-task/templates/CLAUDE-SUPPLEMENT.md" || { echo "supplement section missing"; exit 1; }

echo "test_skill: ALL OK"
