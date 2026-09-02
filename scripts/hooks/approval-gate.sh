#!/bin/bash
# PreToolUse hook（matcher: Bash）：finish-task.sh 是把代码合并进 main 分支的唯一
# 入口，对应官方 Playbook「生产部署需要具名的发布授权」——这里的"生产"就是 main
# 分支。没有人工确认标记文件，禁止执行 finish-task.sh。
# 标记文件由编排 Skill 在人工于飞书确认后 touch 创建（SKILL 步骤 9）。
# 默认 APPROVAL_BASE = 当前工作目录的 .ai-devflow（调用方 cwd 为仓库根时即仓库的
# .ai-devflow）；测试通过环境变量覆盖。
set -u
cmd=$(jq -r '.tool_input.command // ""')
case "$cmd" in
  *finish-task.sh*)
    task_id=$(echo "$cmd" | grep -oE 'finish-task\.sh[[:space:]]+[^[:space:]]+' | awk '{print $2}')
    approval_base="${APPROVAL_BASE:-$PWD/.ai-devflow}"
    if [ -z "$task_id" ] || [ ! -f "$approval_base/$task_id/HUMAN_APPROVED" ]; then
      echo "禁止合并：未找到人工确认标记 $approval_base/$task_id/HUMAN_APPROVED。人工在飞书确认合并后，先 touch 该标记文件再执行 finish-task.sh。" >&2
      exit 2
    fi
    ;;
esac
exit 0
