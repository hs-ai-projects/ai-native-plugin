# AI Native Plugin

为 Claude Code 和 Codex 提供飞书任务关联、进度提醒、会话回链和观测云告警排查入口。插件可独立使用。

## 安装

### Claude Code

```bash
claude plugin marketplace add <本仓库 URL>
claude plugin install ai-native-plugin@ai-native-plugin-marketplace
```

本地源码也可通过 `claude --plugin-dir <插件目录>` 加载。两种方式选择一种，避免重复执行 hooks。

### Codex

```bash
codex plugin marketplace add <本仓库 URL或本地目录>
codex plugin add ai-native-plugin@ai-native-plugin-marketplace
```

安装后插件自动启用。首次使用或内容变化后，还需按 Codex 的 hook 信任机制审阅并授权。通过 `codex plugin list` 检查安装及启用状态。

## 使用条件

会话回链需要已配置应用身份的 `lark-cli`，并具有读取来源消息及评论任务的权限。消息接入工具通过 `CC_SESSION_KEY=feishu:<chat_id>:<thread>:<message_id>` 提供来源会话；普通本地会话只关联任务并提醒进展。

告警排查所需工具见 [owl-alert-triage](skills/owl-alert-triage/SKILL.md)。

## 任务关联与回链

输入飞书任务链接后，插件关联当前会话与任务，在首次关联及后续每 10 条消息提醒同步进展。输入新的任务链接会更新当前关联。

飞书会话会自动向任务评论写入来源会话链接。插件通过本地记录防止并发重复写入；结果不确定时保留记录并提示核对，不自动重试评论。

root 用户的记录保存在 `/root/data/feishu-task-state`；其他用户使用 `${XDG_STATE_HOME:-~/.local/state}/ai-native-plugin/feishu-task-state`。15 天未使用的会话状态和已确认回链记录会被清理；未确认写入的记录保留供核对。

## 开发检查

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
claude plugin validate .claude-plugin/plugin.json
```

`docs/legacy/` 为历史资料，不参与运行时加载。
