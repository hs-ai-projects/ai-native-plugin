#!/bin/bash
# devflow-start-task Skill 结构校验：9 步齐全 + Defer 分支 + 模板存在 + 无容器硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/devflow-start-task/SKILL.md"
[ -f "$SKILL" ] || { echo "SKILL.md missing"; exit 1; }

# argument-hint 已去掉（spec决策：不强制task-id，支持直接对话描述）
grep -q 'argument-hint' "$SKILL" && { echo "argument-hint should be removed"; exit 1; }

# description 需要带"需求特征词"供Claude自动路由（不再要求用户手动选skill）
grep -qi '新增\|新功能\|需求' "$SKILL" || { echo "description missing need-feature keywords for auto-routing"; exit 1; }

# 步骤1需要明确"输入来源二选一/三选一"
grep -q '输入来源' "$SKILL" || { echo "step1 must describe input source options"; exit 1; }
grep -qi '直接对话描述\|对话描述需求' "$SKILL" || { echo "step1 missing direct-description input source"; exit 1; }

# 步骤8改为调用 skill:review（不再直接写 ai-review.sh 判断细节，那部分已收编进review skill）
grep -qi 'skill:review\|skills/review' "$SKILL" || { echo "step8 must reference skill:review"; exit 1; }

# 步骤1.4任务交接分支：必须给出完整可执行描述（不能是占位引用），
# 含发起方发交接消息格式 + 接收方独立判断 + 通知原始发起人的规则
grep -q 'handoff.py' "$SKILL" || { echo "step1.4 must reference handoff.py"; exit 1; }
grep -qi '独立判断Accept/Reject/Defer\|独立走.*Accept/Reject/Defer' "$SKILL" || { echo "step1.4 missing receiver-independent-judgment rule"; exit 1; }
grep -qi '原始发起人' "$SKILL" || { echo "step1.4 missing original-requester notification rule"; exit 1; }

# 协作消息识别前置规则要能路由到bot-boundary
grep -qi 'bot-boundary\|skills/bot-boundary' "$SKILL" || { echo "must reference skills/bot-boundary for collab message routing"; exit 1; }

# harness.yaml缺失时引导用户参照规范文档（不强行猜测）
grep -q 'harness-schema.md' "$SKILL" || { echo "must reference docs/harness-schema.md when harness.yaml missing"; exit 1; }

# 调用lark-cli/glab前先查PITFALLS.md
grep -q 'PITFALLS.md' "$SKILL" || { echo "must reference PITFALLS.md read-trigger"; exit 1; }

# 9 步关键内容（按 spec 第 6 节）
grep -q 'intent.md' "$SKILL" || { echo "step1 intent missing"; exit 1; }
grep -q 'Decision: Accept/Reject/Defer' "$SKILL" || { echo "step1 Decision missing"; exit 1; }
grep -q 'worktree add' "$SKILL" || { echo "step4 worktree missing"; exit 1; }
grep -q 'full-verify' "$SKILL" || { echo "step6 verify missing"; exit 1; }
grep -q 'attribute.py' "$SKILL" || { echo "step7 attribute missing"; exit 1; }
grep -q 'repair-counter.py' "$SKILL" || { echo "step7 repair-counter missing"; exit 1; }
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
