# ai-native-plugin

AI-Native DevFlow 插件：装进任意单个 git 仓库即可跑完整 devflow 流水线。

## 安装

```bash
claude plugin marketplace add <本仓库 URL>
claude plugin install ai-native-plugin@ai-native-plugin-marketplace
```

## 前置依赖（插件不自动装，见 spec 4.2）

| 依赖 | 用途 | 缺失时表现 |
|---|---|---|
| `git` | worktree / MR / 提交 | 无它无法工作 |
| `glab` | 建 MR / 查状态 / merge | `create-mr.sh`/`finish-task.sh` 报错 |
| `lark-cli` | 飞书任务 / 知会 / 协作 | SKILL 步骤 1 探测并提示安装 |
| Python3 | 业务脚本运行 | `ensure-python-deps.sh` 会尝试建 venv |
| `jq` | hook 解析 PreToolUse stdin JSON | protect-paths/approval-gate 两个 hook 静默失效（取不到路径→不拦截） |

Python 包（pyyaml/pytest/httpx）由 `scripts/ensure-python-deps.sh` 首次运行时自动装入
`${CLAUDE_PLUGIN_DATA}/venv`（卸载插件自动清理），不污染目标仓库环境。

## 使用

```bash
/ai-native-plugin:devflow-start-task <task-id>
```

目标仓库需要：`harness.yaml`（声明 stack.type + 分层测试命令）、`CLAUDE.md`（团队组织知识）。
