# ai-native-plugin

公司环境适配层，与固定版本的 mattpocock/skills 配合使用。流程由上游 skills 主导，本插件提供飞书事项、文档产物、Git 交付和群协作约定，以及观测云告警入口。

## 使用

使用运行镜像时由 ai-native 安装固定版本。单独使用 Claude Code 插件时，先安装 mattpocock/skills，再安装本插件：

	claude plugin marketplace add https://github.com/hs-ai-projects/ai-native-plugin.git
	claude plugin install ai-native-plugin@ai-native-plugin-marketplace

需要选择流程时显式调用 ask-matt；实际命令名以当前客户端列出的 skill 为准。工程流程保留上游的确认与完成标准。本插件不再提供 devflow、Gate A/B、固定 FE/BE 角色和 test-verifier。

## 适配文档

- [事项跟踪](docs/agents/issue-tracker.md)：清单、父子任务、依赖及进度。
- [分流映射](docs/agents/triage-labels.md)：上游五种角色对应现有飞书状态。
- [文档产物](docs/agents/artifacts.md)：沿用知识库配置，按需创建和续写。
- [领域文档](docs/agents/domain.md)：项目术语和 ADR。
- [Git 交付](docs/agents/git-workflow.md)：独立分支、PR/MR 与人工合入。

需安装 lark-cli、对应 lark skills，以及 git、Python 3、jq 和目标代码托管平台 CLI。飞书读写权限按任务实际使用的身份配置。

## 迁移

升级后使用新会话。旧任务和文档保持原样，按现有链接续做；历史 Intenting 状态不再作为流程入口。移除旧的阶段提醒 hook 及其自动评论写入，群协作的 @ 检查继续保留。

语义效果由团队使用反馈判断。技术检查覆盖插件清单、hook 行为与引用路径，不以文档长度或量化评分代替效果判断。
