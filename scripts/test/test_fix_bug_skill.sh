#!/bin/bash
# devflow-fix-bug 结构校验：5步齐全 + severity决策树存在 + 不引用SPEC/plan重工件
# + 观测云可选结合 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/devflow-fix-bug/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/devflow-fix-bug/SKILL.md missing"; exit 1; }

grep -q '^name: devflow-fix-bug' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -qi '报错\|坏了\|不对\|复现步骤' "$SKILL" || { echo "description missing bug keywords"; exit 1; }
grep -q 'argument-hint' "$SKILL" && { echo "argument-hint should not exist"; exit 1; }

# 5步齐全
grep -q '1\. \*\*理解' "$SKILL" || { echo "step1 (理解) missing"; exit 1; }
grep -q '2\. \*\*排查' "$SKILL" || { echo "step2 (排查) missing"; exit 1; }
grep -q '3\. \*\*修复方案' "$SKILL" || { echo "step3 (修复方案) missing"; exit 1; }
grep -q '4\. \*\*开发' "$SKILL" || { echo "step4 (开发) missing"; exit 1; }
grep -q '5\. \*\*验证' "$SKILL" || { echo "step5 (验证) missing"; exit 1; }

# 不消费devflow-start-task的重工件模板（允许出现"不生成SPEC.md"这类说明性否定文字，
# 只禁止真的引用模板文件路径，防止bug流程误接需求流程的模板体系）
grep -q 'templates/SPEC-TEMPLATE\|templates/INTENT-TEMPLATE' "$SKILL" && { echo "must NOT reference devflow-start-task's template files"; exit 1; }

# 观测云可选结合
grep -qi 'owl\|观测云' "$SKILL" || { echo "step2 missing observability integration"; exit 1; }
grep -qi '未配置.*跳过\|跳过.*日志辅助' "$SKILL" || { echo "step2 missing graceful skip when not configured"; exit 1; }

# 引用severity决策树 + skill:verify + skill:review
grep -q 'rules/severity.md' "$SKILL" || { echo "must reference rules/severity.md"; exit 1; }
grep -qi 'skill:verify' "$SKILL" || { echo "step5 must reference skill:verify"; exit 1; }
grep -qi 'skill:review' "$SKILL" || { echo "step5 must reference skill:review"; exit 1; }

grep -q 'CLAUDE_PLUGIN_ROOT\|owl' "$SKILL" || { echo "no external tool reference"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

# severity.md 决策树文件存在且含高风险判定
SEV="$ROOT/skills/devflow-fix-bug/rules/severity.md"
[ -f "$SEV" ] || { echo "rules/severity.md missing"; exit 1; }
grep -qi '高风险\|数据库迁移\|支付' "$SEV" || { echo "severity.md missing high-risk criteria"; exit 1; }
grep -qi '只输出排查报告\|止步' "$SEV" || { echo "severity.md missing stop-at-report rule"; exit 1; }

# failure-modes.md 存在（借用pipelit模式）
FM="$ROOT/skills/devflow-fix-bug/failure-modes.md"
[ -f "$FM" ] || { echo "failure-modes.md missing"; exit 1; }

# 调用owl/glab前先查PITFALLS.md
grep -q 'PITFALLS.md' "$SKILL" || { echo "must reference PITFALLS.md read-trigger"; exit 1; }

echo "test_fix_bug_skill: ALL OK"
