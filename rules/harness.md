# 公司环境适配

开发流程使用已安装的 mattpocock/skills，保留各 skill 的调用方式。用户询问该选哪个流程时提示使用 ask-matt。收到飞书任务链接先读取任务；链接本身不授权启动完整开发流程。

涉及以下事项时，从本插件根目录读取对应文档；项目已配置同名约定时使用项目配置：

- 任务、规格或 tickets 的读写：`docs/agents/issue-tracker.md`。
- triage 分流：`docs/agents/triage-labels.md`。
- 领域术语与架构决策：`docs/agents/domain.md`。
- 分支、worktree、PR/MR：`docs/agents/git-workflow.md`。
- 飞书群内协作：`rules/feishu-group-collab.md`。

编写或修改 skills、AGENTS.md、CLAUDE.md 及其引用文档时，先读取 writing-for-agents。
