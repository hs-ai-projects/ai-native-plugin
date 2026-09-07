#!/bin/bash
# PreToolUse hook（matcher: Bash）：强制 feishu-group-collab.md「怎么 @ 人」规则
# （rules/feishu-group-collab.md L74-92）：@ 人必须走带 at 标签的 post 消息，
# 纯文本 @（哪怕文本里写了对方名字）唤不起对方，等同没 @。
#
# 检测粒度与 protect-paths.sh 一致，纯字符串粗匹配，不做 JSON 语义解析：
#   - 非 lark-cli 发消息命令 → 放行
#   - 命令含 "tag":"at"（允许中间有空白）→ 已走结构化 @，放行
#   - 命令含 @ 名字后接空格（如 @广告后端 委派）、却没有 at 标签 → 判定试图
#     纯文本 @ 人，拦截；@ 后无空格（@广告后端委派）不算
#   - 其余（无 @ 意图）→ 放行
# 已知局限：@ 出现在无关位置（如邮箱）可能被误拦，但报错会指向正确用法，
# 改命令即可重试，不会造成静默错误行为。
set -u
cmd=$(jq -r '.tool_input.command // ""')
case "$cmd" in
*+messages-reply* | *+messages-send*)
  # 已带结构化 at 标签 → 放行
  if printf '%s' "$cmd" | grep -qE '"tag"[[:space:]]*:[[:space:]]*"at"'; then
    exit 0
  fi
  # 试图 @ 人（@ + 名字 + 空格终止，如 @广告后端 委派）但没走 at 标签 → 拦。
  # 无终止空格（@广告后端委派后端部分）不算，名字和正文粘一起无法区分，放行。
  if printf '%s' "$cmd" | grep -qE '@[^[:space:]'"'"'"\\]+[[:space:]]'; then
    echo "禁止纯文本 @：@ 人必须用带 at 标签的 post 消息（rules/feishu-group-collab.md 规则）。" >&2
    exit 2
  fi
  ;;
esac
exit 0
