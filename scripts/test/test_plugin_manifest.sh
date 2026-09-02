#!/bin/bash
# 插件 manifest 结构校验：能装上是插件化改造的第一验收标准。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# python3 on this machine is a PowerShell wrapper around `py`, which needs a
# Windows-style path (pwd -W) and UTF-8 mode to read non-ASCII JSON content.
ROOT_WIN="$(cd "$ROOT" && pwd -W 2>/dev/null || pwd)"

[ -f "$ROOT/.claude-plugin/plugin.json" ] || { echo "plugin.json missing"; exit 1; }
[ -f "$ROOT/.claude-plugin/marketplace.json" ] || { echo "marketplace.json missing"; exit 1; }
[ -f "$ROOT/scripts/hooks/run-hook.cmd" ] || { echo "scripts/hooks/run-hook.cmd missing"; exit 1; }

# plugin.json 必须有 name
python3 -X utf8 - "$ROOT_WIN/.claude-plugin/plugin.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("name") == "ai-native-plugin", f'name={d.get("name")}'
print("plugin.json name: OK")
PY

# marketplace.json：source 必须是相对路径 "./"，同仓库分发
python3 -X utf8 - "$ROOT_WIN/.claude-plugin/marketplace.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("name") == "ai-native-plugin-marketplace"
p = d["plugins"][0]
assert p["name"] == "ai-native-plugin"
assert p.get("source") == "./", f'source={p.get("source")}'
print("marketplace.json: OK")
PY

echo "test_plugin_manifest: ALL OK"
