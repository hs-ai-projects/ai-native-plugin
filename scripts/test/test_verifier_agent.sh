#!/bin/bash
# agents/verifier.md 结构校验：工具白名单不含Write/Edit + 独立判断规则 +
# 只输出PASS/FAIL、不给修复建议 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="$ROOT/agents/verifier.md"
[ -f "$FILE" ] || { echo "agents/verifier.md missing"; exit 1; }

# tools frontmatter 存在，且不含 Write / Edit
tools_line=$(grep '^tools: ' "$FILE")
[ -n "$tools_line" ] || { echo "no tools line"; exit 1; }
echo "$tools_line" | grep -qw 'Write' && { echo "verifier tools must NOT include Write"; exit 1; }
echo "$tools_line" | grep -qw 'Edit' && { echo "verifier tools must NOT include Edit"; exit 1; }
echo "$tools_line" | grep -qw 'Read' || { echo "verifier tools must include Read"; exit 1; }
echo "$tools_line" | grep -qw 'Bash' || { echo "verifier tools must include Bash"; exit 1; }

# 不信任前面结论的措辞
grep -qi '不信任\|不接受.*转述\|不复用.*自查' "$FILE" || { echo "distrust-prior-conclusion rule missing"; exit 1; }

# 引用 skill:verify --independent
grep -q -- '--independent' "$FILE" || { echo "must reference --independent mode"; exit 1; }

# 只输出PASS/FAIL+EVIDENCE，不给修复建议
grep -q 'EVIDENCE' "$FILE" || { echo "EVIDENCE output format missing"; exit 1; }
grep -qi '不给修复建议\|不提供修复建议\|不给出修复' "$FILE" || { echo "no-fix-advice rule missing"; exit 1; }

# 禁止容器硬编码
grep -q '/opt/harness\|/app/' "$FILE" && { echo "container path leak"; exit 1; }

echo "test_verifier_agent: ALL OK"
