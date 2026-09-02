# Claude 工作补充（可选追加进当前仓库 CLAUDE.md 的三节）

> devflow-start-task Skill 第一次在某仓库跑起来时，检测该仓库 CLAUDE.md 没有以下三节就询问
> 是否追加；用户可拒绝。不含任何项目专属内容。

## 验证工作（对应当前仓库的 harness.yaml，不要凭感觉猜测试命令）

- 仓库根目录 `harness.yaml` 定义了 unit/api/e2e/contract 各层实际命令，命令是 per-repo 的。
- 快速验证：`${CLAUDE_PLUGIN_ROOT}/scripts/fast-verify.sh <repo_dir>`（只跑 gates.fast）。
- 完整验证：`${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh <repo_dir>`（跑 gates.full 全部层）。
- 结果写入 `<repo_dir>/.ai-devflow/verification.json`：PASS/FAIL；ERROR 表示环境/超时（归 infra）。
- 报告完成前必须真跑过并确认 PASS。

## 架构简述

- `.ai-devflow/<task-id>/` 存放 intent.md / SPEC.md / verification.json / review 产物，不入远端仓库（该目录应加进仓库自己的 `.git/info/exclude`）。
- 任务 sandbox 用 git worktree 隔离（SKILL 步骤 4），独立分支 `task/<task-id>/<ts>` 开发。
- 埋点：`emit-event.py` 写 JSONL → `load-events.py` 灌 SQLite → `analytics.py` 查询。

## Claude 容易犯的错

- 不要只让占位测试跑绿就报 PASS——改了 `paths.business_code` 必须在 `paths.test_code` 同步新增/更新测试。
- 不要自行 push / merge——MR 由 `create-mr.sh` 创建，合并由人工确认后的 `finish-task.sh` 执行。
- 视觉/渲染类 AC 必须真实渲染 + 几何断言 + 负对照。
- contract 类失败不默认归 backend，要看失败侧仓库的 `stack.type`。
