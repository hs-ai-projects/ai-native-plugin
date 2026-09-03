#!/bin/bash
# skills/verify/SKILL.md 结构校验：三模式齐全 + 引用现有脚本 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/verify/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/verify/SKILL.md missing"; exit 1; }

# frontmatter 存在 name/description
grep -q '^name: verify' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -q '^description:' "$SKILL" || { echo "frontmatter description missing"; exit 1; }

# 三种模式都要出现
grep -q -- '--self-check' "$SKILL" || { echo "--self-check mode missing"; exit 1; }
grep -q -- '--independent' "$SKILL" || { echo "--independent mode missing"; exit 1; }
grep -q -- '--full' "$SKILL" || { echo "--full mode missing"; exit 1; }

# self-check 规则1：business_code 改了必须同步 test_code
grep -q 'business_code' "$SKILL" || { echo "self-check rule1 (business_code) missing"; exit 1; }
grep -q 'test_code' "$SKILL" || { echo "self-check rule1 (test_code) missing"; exit 1; }

# self-check 规则2：FAIL 禁止 commit
grep -qi 'FAIL.*禁止.*commit\|禁止.*commit.*FAIL' "$SKILL" || { echo "self-check rule2 (FAIL blocks commit) missing"; exit 1; }

# independent 模式：忽略已有 verification.json，强制重跑，不给修复建议
grep -q '忽略已有\|强制重新执行\|忽略.*verification.json' "$SKILL" || { echo "independent: ignore-existing missing"; exit 1; }
grep -q 'EVIDENCE' "$SKILL" || { echo "independent: EVIDENCE output missing"; exit 1; }
grep -qi '不.*修复建议\|不给修复建议\|不提供修复' "$SKILL" || { echo "independent: no-fix-advice rule missing"; exit 1; }

# 引用现有脚本，路径走 CLAUDE_PLUGIN_ROOT
grep -q 'fast-verify.sh' "$SKILL" || { echo "reference to fast-verify.sh missing"; exit 1; }
grep -q 'full-verify.sh\|verify_runner.py' "$SKILL" || { echo "reference to full-verify.sh/verify_runner.py missing"; exit 1; }
grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

echo "test_verify_skill: ALL OK"
