#!/bin/bash
# enforce-at-mention.sh 单测：纯文本 @ 阻止、带 at 标签放行、无 @ 放行、无关命令放行。
set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/scripts/hooks/enforce-at-mention.sh"
command -v jq >/dev/null 2>&1 || { echo "SKIP: need jq"; exit 0; }
[ -f "$HOOK" ] || { echo "enforce-at-mention.sh missing"; exit 1; }

# 纯文本 @ 但没走 at 标签 → 拦
echo '{"tool_input":{"command":"lark-cli im +messages-reply --message-id om_1 --text \"@张三 已处理\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "block plain-text @: OK" || { echo "block plain-text @: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# 纯文本 @名字后接正文（@ 名字 + 空格终止）→ 拦
echo '{"tool_input":{"command":"lark-cli im +messages-send --chat-id oc_1 --text \"已在群线程内 @广告后端 委派后端部分\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "block @name+space: OK" || { echo "block @name+space: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# @名字后无空格（@广告后端委派后端部分，正文粘名字）→ 放行，不算 @ 人
echo '{"tool_input":{"command":"lark-cli im +messages-send --chat-id oc_1 --text \"@广告后端委派后端部分\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow @name+no-space: OK" || { echo "allow @name+no-space: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# 纯文本 @名字 在消息尾（@名字 + 引号终止，无空格）→ 放行
echo '{"tool_input":{"command":"lark-cli im +messages-reply --message-id om_1 --text \"@广告后端\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow @name@end(no-space): OK" || { echo "allow @name@end: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# 带 at 标签的结构化 @ → 放行
echo '{"tool_input":{"command":"lark-cli im +messages-reply --message-id om_1 --msg-type post --content '\''{\"post\":{\"zh_cn\":{\"title\":\"\",\"content\":[[{\"tag\":\"at\",\"user_id\":\"ou_1\"},{\"tag\":\"text\",\"text\":\" 想说的话\"}]]}}}\''\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow at-tag post: OK" || { echo "allow at-tag post: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# 纯文本但没 @ → 放行
echo '{"tool_input":{"command":"lark-cli im +messages-reply --message-id om_1 --text \"好的，已收到\""}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow plain text no-@: OK" || { echo "allow plain text no-@: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# 无关命令 → 放行
echo '{"tool_input":{"command":"ls -la"}}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "allow unrelated command: OK" || { echo "allow unrelated command: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# ---- Stop 路径：回复文本（.last_assistant_message）纯文本 @ ----

# 非 cc-connect 会话（无 CC_SESSION_KEY），文本含 @ 也放行
echo '{"last_assistant_message":"@张三 已处理"}' | env -u CC_SESSION_KEY bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "stop allow non-cc-connect: OK" || { echo "stop allow non-cc-connect: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

export CC_SESSION_KEY=test-session

# cc-connect：回复文本 @名字 + 空格终止 → 拦
echo '{"last_assistant_message":"@张三 已完成，请验收"}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 2 ] && echo "stop block text plain-@: OK" || { echo "stop block text plain-@: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# cc-connect：@名字后无空格（句末/粘正文）→ 放行，不算 @ 人
echo '{"last_assistant_message":"已转给 @广告后端委派后端部分"}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "stop allow @name+no-space: OK" || { echo "stop allow @name+no-space: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

# cc-connect：文本无 @ → 放行
echo '{"last_assistant_message":"任务已完成，附上 MR 链接。"}' | bash "$HOOK" >/tmp/out.log 2>&1
rc=$?
[ "$rc" -eq 0 ] && echo "stop allow no-@ text: OK" || { echo "stop allow no-@ text: FAILED (rc=$rc)"; cat /tmp/out.log; exit 1; }

echo "test_enforce_at_mention_hook: ALL OK"
