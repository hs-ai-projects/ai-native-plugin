#!/bin/bash
# docs/harness-schema.md 结构校验：字段集完整 + 与verify_runner.py/contract_checker.py
# 实际读取的字段名一致（防止文档字段名和代码字段名不同步）。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOC="$ROOT/docs/harness-schema.md"
[ -f "$DOC" ] || { echo "docs/harness-schema.md missing"; exit 1; }

# 字段集完整性
for field in "project.stack.type" "paths.business_code" "paths.test_code" \
             "gates.fast" "gates.full"; do
  grep -qF "$field" "$DOC" || { echo "field missing in doc: $field"; exit 1; }
done

# "怎么生效"章节存在（不只是罗列字段，要说明谁在什么时候读它）
grep -qi '生效\|谁在.*读\|栈判定' "$DOC" || { echo "missing 'how it takes effect' section"; exit 1; }

# 明确"不猜测/不探测"原则（呼应spec决策：拒绝探测猜测路线）
grep -qi '不猜\|不探测\|不做.*猜测' "$DOC" || { echo "missing no-guessing principle statement"; exit 1; }

# 交叉核对：文档提到的字段名确实是 verify_runner.py / contract_checker.py 代码里
# 实际读取的字段（防止文档虚构了代码不支持的字段）
RUNNER="$ROOT/scripts/verify/verify_runner.py"
CHECKER="$ROOT/scripts/verify/contract_checker.py"
grep -q 'stack.get("type"' "$RUNNER" 2>/dev/null || grep -q "stack\['type'\]\|stack.get('type'" "$RUNNER" || \
  { echo "verify_runner.py does not actually read stack.type as documented"; exit 1; }
grep -q 'business_code' "$CHECKER" || { echo "contract_checker.py does not actually read paths.business_code as documented"; exit 1; }

echo "test_harness_schema_doc: ALL OK"
