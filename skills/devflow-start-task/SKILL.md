---
name: devflow-start-task
description: 处理一个飞书任务需求的完整 9 步流程：理解→intent.md→SPEC→sandbox→开发→验证→归因回流→Review/MR→人工确认合并。收到分配给当前仓库的飞书任务时使用。
argument-hint: ["<task-id>"]
---

# DevFlow Start Task

处理一个需求的完整顺序，按步骤执行不跳过。只处理**当前仓库**的任务（spec 3.1：一仓库一实例）。

## 前置依赖探测（先做，缺了先提示用户装）

```bash
command -v git && command -v glab && command -v lark-cli || echo "缺失依赖请先安装（见插件 README 前置依赖表）"
```

若 `glab` 或 `lark-cli` 缺失：提示用户按 README 安装，不要跑到中途才报错。

## 栈判定（决定 persona 与验证层）

```bash
stack_type=$(python3 -c "import yaml; print(yaml.safe_load(open('harness.yaml'))['project']['stack']['type'])")
```

`frontend` → 用 `agents/frontend.md`，验证层跑 frontend_unit_cmd/e2e；`backend` → 用 `agents/backend.md`，验证层跑 backend_unit_cmd/api。没有 harness.yaml 则停下询问。

## 9 步流程

1. **需求理解 + 写 intent.md**：`lark-cli task tasks get --task-guid <task-id> --as user` 拿全字段；附件图片下载到本地用 sonnet 模型识图（识完切回默认模型）。按 `templates/INTENT-TEMPLATE.md` 写 `.ai-devflow/<task-id>/intent.md`，末尾填 `## Decision: Accept/Reject/Defer + 理由`。**Defer 型任务到此止步**——只飞书知会一句，不进入步骤 2，不产生 sandbox 与 MR。
2. **写 SPEC.md（仅 Accept）**：读取 intent.md，按 `templates/SPEC-TEMPLATE.md` 写 `.ai-devflow/<task-id>/SPEC.md`（首行引用 intent.md 路径）。AC 逐条可映射到测试；Task Breakdown 标注 owner（frontend/backend）。
3. **飞书知会**需求方：SPEC 路径 + 需求摘要（`lark-cli` 失败不阻塞流程）。
4. **建 sandbox**：`git worktree add .ai-devflow/sandboxes/<task-id> -b task/<task-id>/$(date +%s)`（当前仓库内隔离并发任务；worktree add 前先 `git fetch origin && git checkout main/master && git pull --ff-only`，失败即中止）。把当前仓库的 `harness.yaml` 复制进 sandbox 根目录。
5. **派发开发**：用 Task 工具派发给当前仓库对应 persona（`agents/frontend.md` 或 `agents/backend.md`，见栈判定）。传 SPEC 相关章节 + sandbox 路径。该 agent 自己改代码+写测试+commit 前自查（见 agents 硬性规则 2）。
6. **汇总验证**：跑 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh <sandbox_path>`，读 `<sandbox_path>/.ai-devflow/verification.json`。**覆盖率自检**：`git diff --stat <基线>...HEAD` 若改了 business_code 却无 test_code 变化，即使 PASS 也退回步骤 5 补测试。把状态写回 SPEC 第 4 章。
7. **FAIL → 归因回流**：`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/attribute.py <verification.json>` 归因（subtype=timeout/infra_exception 自动归 infra）；按 owner 把 failure 包打回步骤 5 对应 persona 修复；复验后 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/repair-counter.py <task-id> <repo> <PASS|FAIL>` 更新计数，`escalate: true`（连续≥3）→ 飞书通知人工暂停任务。
8. **PASS → Review/建MR**：跑 `${CLAUDE_PLUGIN_ROOT}/scripts/ai-review.sh <sandbox_path> <task-id>` 生成 review 包（清单来自插件 `policies/REVIEW.md`，产出机读 `review.json`）；基于 review 包做 AI 判断，把 `review.json` 的 verdict 改为 PASS/FAIL；FAIL 回步骤 7。PASS 则 `${CLAUDE_PLUGIN_ROOT}/scripts/create-mr.sh <sandbox_path> <task-id>` 建 MR（内部走 `glab mr create`），飞书卡片通知人工。**建完 MR 编排即告一段落**——MR 评论由用户人工在 GitLab 跟进，插件不再自动回修。
9. **等人工确认 → merge**：人工在飞书确认后，先 `touch .ai-devflow/<task-id>/HUMAN_APPROVED` 创建确认标记（`approval-gate.sh` hook 检查此文件，缺失则拦截），再跑 `${CLAUDE_PLUGIN_ROOT}/scripts/finish-task.sh <task-id> <repo> <sandbox_path> <mr-url>`（内部走 `glab mr merge` + worktree 清理 + 埋点）。

## 首次在某仓库运行

检查该仓库 CLAUDE.md 是否含 `CLAUDE-SUPPLEMENT.md` 的三节（验证工作/架构简述/易犯错清单）；没有则询问用户是否追加，可拒绝。

## 输出

`.ai-devflow/<task-id>/intent.md` + `SPEC.md` + sandbox 的 `verification.json` + `review.json` + MR
