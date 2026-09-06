#!/usr/bin/env bash
# 每次用户输入，把 rules/ 目录下所有常驻规则注入当轮上下文（UserPromptSubmit
# hook）。仅 cc-connect 会话注入（claude 子进程继承 CC_SESSION_KEY 标识）；
# 本地 cli / SDK / agent 等非 cc-connect 会话跳过。
#
# 注入机制：UserPromptSubmit hook exit 0 时，stdout 的 JSON
#   {"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"..."}}
# 会把 additionalContext 作为 system-reminder 注入该次用户输入、模型生成之前。
# 相较 SessionStart 只在会话开头注入一次，本方案每轮输入都带最新规则——rules/
# 改动即时生效，不依赖新开会话。代价是每轮重复注入（~5KB），可接受。
#
# 来源判定：CLAUDE_CODE_ENTRYPOINT 无法区分 cc-connect（桥不设该变量，claude
#   子进程走缺省 cli / sdk-cli，与本地同源）；改用 cc-connect 注入的
#   CC_SESSION_KEY 会话标识做门控，无值即非 cc-connect 会话。UserPromptSubmit
#   无 matcher，无法在 hooks.json 层按来源过滤，只能脚本内门控。
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

# 仅 cc-connect 会话注入（cc-connect 以 CC_SESSION_KEY 环境变量标记会话）；
# 本地 cli / SDK 等其余来源无此变量，直接放行不注入。
if [ -z "${CC_SESSION_KEY:-}" ]; then
  exit 0  # 非 cc-connect 会话，不注入
fi

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
        "hookEventName": "UserPromptSubmit",
        "additionalContext": wrapped,
    }
}, ensure_ascii=False))
PY
exit 0
