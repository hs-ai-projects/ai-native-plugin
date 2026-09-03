#!/bin/bash
# PITFALLS.md 结构校验：四列表头 + 空表体（骨架阶段无实际踩坑记录）+
# 写入/读取规则说明存在。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="$ROOT/PITFALLS.md"
[ -f "$FILE" ] || { echo "PITFALLS.md missing"; exit 1; }

# 四列表头
grep -qE '\|\s*工具/场景\s*\|\s*已知问题\s*\|\s*规避方法\s*\|\s*发现时间\s*\|' "$FILE" \
  || { echo "table header missing or wrong columns"; exit 1; }

# 写入规则说明：事后确认追加，不自动写
grep -qi '事后确认\|确认.*追加\|用户确认' "$FILE" || { echo "write-trigger rule (confirm-after-task) missing"; exit 1; }
grep -qi '独立.*commit\|单独.*commit' "$FILE" || { echo "independent-commit rule missing"; exit 1; }

# 读取规则说明：调用前先查
grep -qi '调用.*之前.*先\|先查\|提前应用' "$FILE" || { echo "read-trigger rule (check-before-call) missing"; exit 1; }

# 明确不做自动过期检测
grep -qi '不.*自动过期\|不.*定期核查' "$FILE" || { echo "no-auto-expiry statement missing"; exit 1; }

echo "test_pitfalls_doc: ALL OK"
