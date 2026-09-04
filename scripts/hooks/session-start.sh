#!/usr/bin/env bash
# 每次会话开始把飞书群协作常驻规则注入上下文（SessionStart hook）。
#
# 注入机制：SessionStart hook exit 0 时，stdout 的 JSON
#   {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}
# 会把 additionalContext 文本作为 system-reminder 注入会话开头、第一条用户
# 消息之前，每次模型请求可读。
#
# 注意：
#   - additionalContext 是 String，不支持 file 引用；内容用 python3 json.dumps
#     转义（规则文本含换行 / 引号，裸拼会破坏 JSON）。
#   - 成功路径保持 stderr 干净、exit 0。
#   - 内容超 10k 字符会由 Claude Code 自动降级为文件引用；本规则 ~5KB，直接
#     内联安全。
set -u

RULES_FILE="${CLAUDE_PLUGIN_ROOT:-}/rules/feishu-group-collab.md"
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -f "$RULES_FILE" ]; then
  exit 0  # 插件结构缺失 / 未安装时静默退出，不注入
fi

python3 - "$RULES_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    text = f.read()

# 规则文本外套 XML 标签，作为注入内容的明确边界（模型识别为"插件注入的
# 常驻规则块"，区别于会话里普通文本）。
wrapped = f"<feishu-group-collab>\n{text}\n</feishu-group-collab>"

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": wrapped,
    }
}, ensure_ascii=False))
PY
exit 0
