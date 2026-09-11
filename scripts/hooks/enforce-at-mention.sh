#!/bin/bash
# enforce-at-mention.sh：拦截「纯文本 @ 唤人」。同一规则（rules/feishu-group-collab.md
# 『怎么 @ 人』：@ 必须在回复文本里嵌 <at user_id="...">名字</at> 标签，纯文本 @ 唤不起
# 对方）的两个入口合一，检测口径一致：
#
#   - PreToolUse（matcher: Bash），查 .tool_input.command：lark-cli 发消息命令里试图
#     @ 人却没带 <at user_id="..."> 标签 → 拦。命令执行前阻止。
#   - Stop，查 .last_assistant_message：cc-connect 把每轮回复转成飞书群消息，回复文本
#     里纯文本 @ 唤不起对方 → 拦。仅 cc-connect 会话检查（CC_SESSION_KEY，同
#     inject-rules.sh）；本地 cli 回复文本不发群，不拦。
#
# 事件按输入字段存在性分叉（last_assistant_message 仅 Stop 有，tool_input.command 仅
# PreToolUse 有），两事件字段互斥，无需读 hook_event_name。
#
# 退出语义：exit 2 阻断。PreToolUse 下命令被阻止；Stop 下阻止 Claude 停止并续跑，
# stderr 作续跑原因喂给模型（Claude Code 8 次连续续跑上限兜底，不死循环）。
set -u
input=$(cat)

# ---- Stop 路径：回复文本纯文本 @ ----
msg=$(printf '%s' "$input" | jq -r '.last_assistant_message // empty' 2>/dev/null)
if [ -n "$msg" ]; then
  if [ -z "${CC_SESSION_KEY:-}" ]; then
    exit 0  # 非 cc-connect 会话，回复文本不发群，不查
  fi
  # 已带 <at user_id="..."> 标签 → 放行
  if printf '%s' "$msg" | grep -qE '<at[[:space:]]+user_id='; then
    exit 0
  fi
  # @名字后接空格终止才算 @ 意图（@广告后端 委派）；名字正文粘一起不算，放行。
  if printf '%s' "$msg" | grep -qE '@[^[:space:]'"'"'\\]+[[:space:]]'; then
    echo "禁止在回复文本里纯文本 @：cc-connect 会把回复转成飞书群消息，文本里的 @名字 唤不起对方，等同没 @。要 @ 人请在回复文本里改用 <at user_id=\"对方open_id\">对方名字</at> 标签（见 rules/feishu-group-collab.md『怎么 @ 人』）；否则删掉文本里的 @，用文字说明即可。" >&2
    exit 2
  fi
  exit 0
fi

# ---- PreToolUse（matcher: Bash）路径：lark-cli 发消息命令纯文本 @ ----
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
case "$cmd" in
*+messages-reply* | *+messages-send*)
  # 已带 <at user_id="..."> 标签 → 放行
  if printf '%s' "$cmd" | grep -qE '<at[[:space:]]+user_id='; then
    exit 0
  fi
  # 试图 @ 人（@ + 名字 + 空格终止，如 @广告后端 委派）但没走 at 标签 → 拦。
  # 无终止空格（@广告后端委派后端部分）不算，名字和正文粘一起无法区分，放行。
  if printf '%s' "$cmd" | grep -qE '@[^[:space:]'"'"'\\]+[[:space:]]'; then
    echo "禁止纯文本 @：@ 人必须在消息内容里用 <at user_id=\"对方open_id\">对方名字</at> 标签（rules/feishu-group-collab.md 规则）。" >&2
    exit 2
  fi
  ;;
esac
exit 0
