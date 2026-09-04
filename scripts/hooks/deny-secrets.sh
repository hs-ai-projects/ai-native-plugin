#!/bin/bash
# PreToolUse hook（matcher: Read）——主动暂缓，未接入 hooks.json（spec 第 2 节/第 9 节）。
#
# 技术方案存档：容器形态下靠 Dockerfile 焊死 settings.json 的 permissions.deny 强制
# 所有任务遵守；插件形态下插件装不进目标仓库的 settings.json，唯一能自动生效的等价
# 方案是插件自带这条 PreToolUse hook，拦截 Read(.env)。本次 brainstorming 中用户明确
# "暂时不考虑"，标记为主动暂缓，不是遗漏。启用时在 hooks/hooks.json 的 PreToolUse
# 加 matcher "Read" 条目指向本脚本即可。
#
# 逻辑：命中 .env/.env.*/**/secrets/**/**/*.pem/**/.git/** 则 exit 2 拦截。
set -u
file_path=$(jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.env|*.env.*|*/secrets/*|*.pem|*/.git/*)
    echo "受保护敏感路径禁止读取：$file_path" >&2
    exit 2
    ;;
esac
exit 0
