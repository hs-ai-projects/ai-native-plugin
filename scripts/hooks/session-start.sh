#!/usr/bin/env bash
# 每次会话开始把 rules/ 目录下所有常驻规则注入上下文（SessionStart hook）。
#
# 注入机制：SessionStart hook exit 0 时，stdout 的 JSON
#   {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}
# 会把 additionalContext 文本作为 system-reminder 注入会话开头、第一条用户
# 消息之前，每次模型请求可读。
#
# 规则来源：${CLAUDE_PLUGIN_ROOT}/rules/*.md，每份套同名 XML 标签
#   <feishu-group-collab> / <dev-workflow> … 作为注入内容的明确边界，模型
#   识别为"插件注入的常驻规则块"。往 rules/ 放一份 .md 即自动注入，无需改
#   本脚本或 hooks.json。
#
# 注意：
#   - additionalContext 是 String，不支持 file 引用；内容用 python3 json.dumps
#     转义（规则文本含换行 / 引号，裸拼会破坏 JSON）。
#   - 成功路径保持 stderr 干净、exit 0。
#   - 内容超 10k 字符会由 Claude Code 自动降级为文件引用（模型自行 Read）；
#     当前规则合计 ~5KB，直接内联安全。
set -u

RULES_DIR="${CLAUDE_PLUGIN_ROOT:-}/rules"
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -d "$RULES_DIR" ]; then
  exit 0  # 插件结构缺失 / 未安装时静默退出，不注入
fi

python3 - "$RULES_DIR" <<'PY'
import json
import os
import sys

rules_dir = sys.argv[1]
blocks = []
for name in sorted(os.listdir(rules_dir)):
    if not name.endswith(".md"):
        continue
    path = os.path.join(rules_dir, name)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        continue
    if not text:
        continue
    tag = name[:-3]  # 去 .md 后缀，如 feishu-group-collab
    blocks.append(f"<{tag}>\n{text}\n</{tag}>")

wrapped = "\n".join(blocks)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": wrapped,
    }
}, ensure_ascii=False))
PY
exit 0
