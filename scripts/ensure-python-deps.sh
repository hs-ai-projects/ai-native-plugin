#!/bin/bash
# ensure-python-deps.sh
#
# 返回插件脚本可用的 python3 绝对路径（stdout）。首次运行在 CLAUDE_PLUGIN_DATA 下
# 自建插件专属 venv 并安装 pyyaml/pytest/httpx；卸载插件时该目录随之清理，不污染
# 目标仓库环境。
#
# Windows venv 可执行文件在 Scripts/python.exe，Unix 在 bin/python3 —— 两种布局都检测。
set -u

DATA_DIR="${CLAUDE_PLUGIN_DATA:-${HOME:-/tmp}/.claude/plugin-data/ai-native-plugin}"
VENV_DIR="${DATA_DIR}/venv"

# 已存在则直接返回
if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  echo "$VENV_DIR/Scripts/python.exe"
  exit 0
fi
if [ -x "$VENV_DIR/bin/python3" ]; then
  echo "$VENV_DIR/bin/python3"
  exit 0
fi

# 创建 venv：Windows 的 py 启动器需要 Windows 形式路径（cygpath 转换）
if command -v cygpath >/dev/null 2>&1; then
  VENV_ARG="$(cygpath -w "$VENV_DIR")"
else
  VENV_ARG="$VENV_DIR"
fi
mkdir -p "$DATA_DIR"
if ! python3 -m venv "$VENV_ARG"; then
  echo "ensure-python-deps: venv 创建失败: $VENV_DIR" >&2
  exit 1
fi

if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  PY="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/bin/python3" ]; then
  PY="$VENV_DIR/bin/python3"
else
  echo "ensure-python-deps: venv 布局无法识别: $VENV_DIR" >&2
  exit 1
fi

if ! "$PY" -m pip install -q pyyaml pytest httpx; then
  echo "ensure-python-deps: pip install pyyaml pytest httpx 失败" >&2
  exit 1
fi

echo "$PY"
exit 0
