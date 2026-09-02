#!/bin/bash
# PreToolUse hook（matcher: Edit|Write）：阻止 Agent 编辑受保护路径。
# .ai-devflow/ 是脚本产物目录（verification.json/review.json/events），harness.yaml
# 是裁判配置——两者都不该被开发 Agent 手动改掉，尤其是为了让测试"看起来通过"而
# 偷改判定标准。输入 stdin JSON: {"tool_input":{"file_path":"..."}}。
set -u
file_path=$(jq -r '.tool_input.file_path // .tool_input.path // ""')
case "$file_path" in
  */.ai-devflow/*|*harness.yaml)
    echo "受保护路径禁止直接编辑：$file_path（.ai-devflow/ 是脚本产物目录，harness.yaml 是裁判配置，不能被开发任务修改）" >&2
    exit 2
    ;;
esac
exit 0
