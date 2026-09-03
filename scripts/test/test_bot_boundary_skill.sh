#!/bin/bash
# skills/bot-boundary/SKILL.md 结构校验：仅限bot@bot场景 + 三分支路由完整 +
# 不影响人类用户@机器人场景的措辞存在。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/bot-boundary/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/bot-boundary/SKILL.md missing"; exit 1; }

grep -q '^name: bot-boundary' "$SKILL" || { echo "frontmatter name missing"; exit 1; }

# 触发条件限定：sender是另一个bot
grep -qi 'sender.*bot\|另一个bot\|被.*bot.*@' "$SKILL" || { echo "trigger condition (bot sender) missing"; exit 1; }

# 三分支路由：contract/handoff/无前缀
grep -q '\[contract ' "$SKILL" || { echo "contract branch missing"; exit 1; }
grep -q '\[handoff\]' "$SKILL" || { echo "handoff branch missing"; exit 1; }
grep -qi '不带.*前缀\|无.*前缀' "$SKILL" || { echo "no-prefix branch missing"; exit 1; }

# 无前缀分支：只分析不动手
grep -qi '只输出分析性回复\|不执行任何写操作' "$SKILL" || { echo "analyze-only rule missing"; exit 1; }
grep -qi '不改代码\|不建sandbox\|不建MR\|不merge' "$SKILL" || { echo "no-write-action specifics missing"; exit 1; }

# 明确不影响人类用户场景
grep -qi '人类用户\|与.*人类.*区分\|区分.*人类' "$SKILL" || { echo "human-user distinction missing"; exit 1; }

# 引用两个解析函数
grep -qi 'parse_handoff_message\|handoff.py' "$SKILL" || { echo "handoff.py reference missing"; exit 1; }
grep -qi 'parse_collab_message\|partner.py' "$SKILL" || { echo "partner.py reference missing"; exit 1; }

echo "test_bot_boundary_skill: ALL OK"
