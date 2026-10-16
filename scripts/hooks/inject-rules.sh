#!/usr/bin/env bash
# 会话开始只注入适配入口，业务参考按需读取。
set -eu
python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["CLAUDE_PLUGIN_ROOT"])
context = f"公司环境适配：先读取 {root / 'rules/harness.md'}。该文件中的相对路径以 {root} 为根。"
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart", "additionalContext": context
}}, ensure_ascii=False))
PY
