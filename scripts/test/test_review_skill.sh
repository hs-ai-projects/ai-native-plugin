#!/bin/bash
# skills/review/SKILL.md 结构校验：可被内部调用+支持手动触发+引用现有ai-review.sh。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/review/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/review/SKILL.md missing"; exit 1; }

grep -q '^name: review' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -q '^description:' "$SKILL" || { echo "frontmatter description missing"; exit 1; }

# 手动触发特征词（description里要能让用户"帮我review一下这个MR"命中）
grep -qi 'review.*MR\|review一下\|手动触发\|手动调用' "$SKILL" || { echo "manual-trigger phrasing missing"; exit 1; }

# 引用现有脚本
grep -q 'ai-review.sh' "$SKILL" || { echo "reference to ai-review.sh missing"; exit 1; }
grep -q 'review.json\|review.md' "$SKILL" || { echo "reference to review output files missing"; exit 1; }

# verdict判断逻辑存在
grep -qi 'verdict' "$SKILL" || { echo "verdict handling missing"; exit 1; }

grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

echo "test_review_skill: ALL OK"
