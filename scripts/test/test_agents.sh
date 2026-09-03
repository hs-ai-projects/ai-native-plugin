#!/bin/bash
# agents/*.md 结构校验：工具白名单 + 两条硬性规则存在 + 无容器硬编码路径。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

for f in frontend backend; do
  FILE="$ROOT/agents/$f.md"
  [ -f "$FILE" ] || { echo "agents/$f.md missing"; exit 1; }
  grep -q '^tools: ' "$FILE" || { echo "$f: no tools line"; exit 1; }
  # 规则1：business_code 改必须同步 test_code
  grep -q 'business_code' "$FILE" || { echo "$f: rule1 missing (business_code)"; exit 1; }
  grep -q 'test_code' "$FILE" || { echo "$f: rule1 missing (test_code)"; exit 1; }
  # 规则2：commit 前调用 skill:verify --self-check 自查（不再直接内嵌 full-verify.sh 调用，
  # 硬性规则已抽到 skills/verify/SKILL.md，agent md 只保留角色定义 + 调用方式）
  grep -q -- '--self-check' "$FILE" || { echo "$f: rule2 missing (--self-check)"; exit 1; }
  grep -qi 'skill:verify\|skills/verify' "$FILE" || { echo "$f: rule2 must reference skill:verify"; exit 1; }
  # 禁止容器硬编码
  grep -q '/opt/harness\|/app/' "$FILE" && { echo "$f: container path leak"; exit 1; }
done
# frontend 专属 model: sonnet（spec 第 5 节）
grep -q 'model: sonnet' "$ROOT/agents/frontend.md" || { echo "frontend: model sonnet missing"; exit 1; }
# 不再有独立 test agent（spec 第 2 节：并入 frontend/backend）
[ -f "$ROOT/agents/test.md" ] && { echo "agents/test.md should not exist"; exit 1; }
echo "test_agents: ALL OK"
