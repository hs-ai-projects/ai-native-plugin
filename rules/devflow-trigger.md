# devflow 触发规则

规定「什么时候进入 devflow 流程」以及「产物落在哪」。
流程本身（Intake / 分类 / Gate / 验收）见 `agents/teamlead.md`，此处不重复。

## 什么时候进入

用户提出以下任一类请求时，进入 devflow 流程：

- 新增功能、新页面、新接口，或改变已有行为
- 报告 bug、描述异常行为、口述问题
- 明确指派（「帮我做 xxx」）
- 飞书群消息带任务链接

以下**不**进入，直接回答即可：

- 纯咨询、概念解释（「这个字段什么意思」）
- 只读的代码解释、代码走读
- 闲聊

判定为「进入」后，以 teamlead 身份按 `agents/teamlead.md` 执行完整流程。
派实现 / 验证 agent 用 Agent 工具，`subagent_type` 取 `frontend-developer` /
`backend-developer` / `test-verifier`。

## 产物落盘

每个任务一个独立目录，根路径由 `AI_NATIVE_HOME` 决定（默认 `/root/data/ai-native`）：

    ${AI_NATIVE_HOME:-/root/data/ai-native}/<task-id>/
      intent.md    # FEATURE 任务必建
      spec.md
      plan.md

- **task-id**：消息带飞书任务链接时取链接的 guid；口述、无链接时用
  `<YYYY-MM-DD>-<短slug>`（slug 由需求主题提炼，如 `2026-09-10-login-timeout`）。
- 任务目录在 TASK INTAKE 完成后、写第一份产物前建立。
- 该 task-id 目录已存在 → 视为续做该任务：先读已有产物再继续，不要覆盖重来。

## 与飞书任务分组的关系

任务卡的四个分组（待办 / 进行中 / 待审核 / 待验证）由 feishu-task-reminder
hook 在检测到任务链接时单独注入，与本规则并行生效：进入 devflow 流程即把
任务卡移到「进行中」。
