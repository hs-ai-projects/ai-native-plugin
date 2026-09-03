# 主入口重构：devflow-start-task 拆细 + devflow-fix-bug 新增 + review 收编 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉 `devflow-start-task` 的 `argument-hint`，支持"task-id / 直接对话描述"两种输入来源并拆细步骤1；新增 `devflow-fix-bug`（5步简化流程，可选结合观测云）；新增 `skills/review/SKILL.md`（被两条主流程内部调用，同时支持用户手动触发）。

**Architecture:** 两个主入口都不再要求用户手动选择——靠各自 `SKILL.md` frontmatter 的 `description` 特征词描述让 Claude 自动路由。`devflow-start-task` 保留原有9步骨架不变（sandbox/派发/汇总验证/归因回流/建MR/人工确认合并这几步的脚本调用点全部沿用 Plan 1 之前就已存在的 `scripts/**`），本 Plan 只重写步骤1（输入来源+intent+影响面判定的描述方式）和步骤8（改为调用新的 `skill:review` 而不是直接调 `ai-review.sh`）。`devflow-fix-bug` 是全新文件，复用 Plan 1 产出的 `skill:verify`，复用现有 `agents/frontend.md`/`backend.md`，但不复用 SPEC.md/intent.md 模板体系（bug流程不产出这些重工件）。`skills/review/SKILL.md` 包一层在现有 `scripts/review/ai-review.sh` 之上，脚本本身不改。

**Tech Stack:** Markdown（SKILL.md × 3）+ Bash 脚本级单测（沿用 `scripts/test/*.sh` 风格）。不新增业务脚本——本 Plan 全部是编排文档层改动，实际执行仍落到已有的 `scripts/verify/*`、`scripts/review/ai-review.sh`、`scripts/lifecycle/*`。

**Spec:** `docs/superpowers/specs/2026-09-03-devflow-v2-redesign.md` 第3、4、6节。

**依赖:** 本 Plan 假设 `docs/superpowers/plans/2026-09-03-verify-foundation.md`（Plan 1）已执行完毕——`skills/verify/SKILL.md` 与 `agents/verifier.md` 已存在，`agents/frontend.md`/`agents/backend.md` 已改为引用 `skill:verify --self-check`。

## Global Constraints

- 两个主入口的 `SKILL.md` frontmatter **不得包含 `argument-hint`**（spec 决策记录：去掉 argument-hint）。
- 两个主入口都必须在正文里明确写出"输入来源二选一/三选一"的判断逻辑（task-id / 直接对话描述 / 机器人交接——第三种交接来源本 Plan 只需**预留占位描述**，具体协议内容是 Plan 3 的范围，本 Plan 不实现 `[handoff]` 消息解析）。
- `devflow-fix-bug` **不得**引用或生成 `SPEC.md`/`plan.md`/`INTENT-TEMPLATE.md` 这类需求流程模板——bug流程刻意保持轻量。
- `skills/review/SKILL.md` 不改写 `scripts/review/ai-review.sh` 现有行为（该脚本已有 `test_ai_review.sh` 覆盖），只描述"何时调用它、调用后如何判断 verdict"。
- 所有脚本路径引用必须用 `${CLAUDE_PLUGIN_ROOT}/...`，不出现 `/app/`、`/opt/harness` 容器路径硬编码（与现有 `test_skill.sh`/`test_agents.sh` 断言口径一致）。

---

### Task 1: `skills/review/SKILL.md` — review 能力收编为领域 skill

**Files:**
- Create: `skills/review/SKILL.md`
- Test: `scripts/test/test_review_skill.sh`

**Interfaces:**
- Consumes: 现有 `scripts/review/ai-review.sh <sandbox_path> <task_id>`（不改其行为，只描述调用方式与产出的 `review.md`/`review.json` 如何被读取判断）
- Produces: 无程序化接口——供 Task 2（devflow-start-task 步骤8）与 Task 3（devflow-fix-bug 步骤5）在正文里引用调用

- [ ] **Step 1: 写测试（先写测试，红）**

```bash
#!/bin/bash
# skills/review/SKILL.md 结构校验：可被内部调用+支持手动触发+引用现有ai-review.sh。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/review/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/review/SKILL.md missing"; exit 1; }

grep -q '^name: review' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -q '^description:' "$SKILL" || { echo "frontmatter description missing"; exit 1; }

# 手动触发特征词（description里要能让用户"帮我review一下这个MR"命中）
grep -qi 'review.*MR\|review一下\|手动触发\|手动调用' "$SKILL" || { echo "manual-trigger phrasing missing"; exit 1; }

# 引用现有脚本
grep -q 'ai-review.sh' "$SKILL" || { echo "reference to ai-review.sh missing"; exit 1; }
grep -q 'review.json\|review.md' "$SKILL" || { echo "reference to review output files missing"; exit 1; }

# verdict判断逻辑存在
grep -qi 'verdict' "$SKILL" || { echo "verdict handling missing"; exit 1; }

grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

echo "test_review_skill: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_review_skill.sh`
Expected: `skills/review/SKILL.md missing`（exit 1）

- [ ] **Step 3: 写 `skills/review/SKILL.md`**

```markdown
---
name: review
description: >
  代码评审能力。两种触发方式：(1) 被 devflow-start-task/devflow-fix-bug
  内部自动调用（开发完成、验证通过后，建MR前）；(2) 用户直接说"帮我review一下
  这个MR"/"review一下这次改动"时手动单独触发，用于人工评论回修场景的重新评审。
---

# Review Skill

生成 AI Review 包并判断 verdict。内部委托给
`${CLAUDE_PLUGIN_ROOT}/scripts/review/ai-review.sh <sandbox_path> <task_id>`，
本 skill 只描述何时调用、调用后怎么读结果。

## 内部调用（被两条主流程自动触发）

调用时机：`skill:verify` 汇总验证已 PASS，准备建 MR 之前。

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/review/ai-review.sh <sandbox_path> <task_id>
```

脚本产出 `.ai-devflow/<task_id>/review.md`（人读，含diff/AC清单/verification摘要/
policies/REVIEW.md动态清单）与 `review.json`（机读，初始 `verdict: PENDING`）。

**verdict 判断**：基于 `review.md` 的检查清单逐项评估这次改动，把 `review.json`
的 `verdict` 改写为 `PASS` 或 `FAIL`：
- 命中 Critical 级问题（改动范围超出SPEC声明的文件 / AC未被任何测试覆盖）→ `FAIL`
- 命中 Important 级问题（business_code改了test_code没同步 / verification.json有
  NOT_RUN被当PASS处理）→ `FAIL`
- 只有 Nit 级问题（命名/可读性，且不超过 `policies/REVIEW.md` 声明的
  `Maximum Nit Comments`）→ `PASS`，Nit 记录进 `review.json.nits` 供人工MR描述参考
- `FAIL` → 调用方（编排skill）回归归因回流；`PASS` → 调用方继续建MR

## 手动触发（用户直接喊"帮我review一下这个MR"）

适用场景：MR已建好，人工在GitLab上评论过，想让AI重新评审一次当前diff（而非从头
走完整devflow流程）。

1. 确认用户给的是哪个 `task_id`/`sandbox_path`（缺失时问用户，不猜）
2. 同样调用 `ai-review.sh <sandbox_path> <task_id>`，覆盖写入新的 `review.md`/`review.json`
3. 输出 verdict 判断结果给用户看，不自动执行后续建MR/merge动作——手动触发场景下
   由用户自己决定下一步（这跟内部调用不同：内部调用verdict=PASS会自动推进到建MR，
   手动触发只汇报结果，不代替用户做决定）
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_review_skill.sh`
Expected: `test_review_skill: ALL OK`

- [ ] **Step 5: Commit**

```bash
git add skills/review/SKILL.md scripts/test/test_review_skill.sh
git commit -m "feat: add skills/review SKILL.md wrapping ai-review.sh for dual trigger modes"
```

---

### Task 2: `devflow-start-task` 去 argument-hint + 拆细步骤1 + 步骤8改调用skill:review

**Files:**
- Modify: `skills/devflow-start-task/SKILL.md`
- Modify: `scripts/test/test_skill.sh`

**Interfaces:**
- Consumes: Task 1 的 `skills/review/SKILL.md`；Plan 1 的 `skills/verify/SKILL.md`
- Produces: 无新接口，改写现有文件正文

- [ ] **Step 1: 先改测试断言（红）**

现有 `test_skill.sh` 第9行要求 `argument-hint` **存在**：

```bash
grep -q 'argument-hint' "$SKILL" || { echo "argument-hint missing"; exit 1; }
```

改为要求**不存在**（去掉argument-hint是本次决策），并新增对"输入来源二选一"和"自动路由描述词"的断言：

```bash
# argument-hint 已去掉（spec决策：不强制task-id，支持直接对话描述）
grep -q 'argument-hint' "$SKILL" && { echo "argument-hint should be removed"; exit 1; }

# description 需要带"需求特征词"供Claude自动路由（不再要求用户手动选skill）
grep -qi '新增\|新功能\|需求' "$SKILL" || { echo "description missing need-feature keywords for auto-routing"; exit 1; }

# 步骤1需要明确"输入来源二选一/三选一"
grep -q '输入来源' "$SKILL" || { echo "step1 must describe input source options"; exit 1; }
grep -qi '直接对话描述\|对话描述需求' "$SKILL" || { echo "step1 missing direct-description input source"; exit 1; }

# 步骤8改为调用 skill:review（不再直接写 ai-review.sh 判断细节，那部分已收编进review skill）
grep -qi 'skill:review\|skills/review' "$SKILL" || { echo "step8 must reference skill:review"; exit 1; }
```

同时**保留**原有对 `intent.md`/`Decision: Accept/Reject/Defer`/`worktree add`/`full-verify`/`attribute.py`/`repair-counter.py`/`create-mr.sh`/`finish-task.sh`/`HUMAN_APPROVED`/`command -v glab`/`command -v lark-cli`/`CLAUDE_PLUGIN_ROOT` 这些断言不变（9步骨架本身没变，只是步骤1和步骤8的描述方式变了）。

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_skill.sh`
Expected: `argument-hint should be removed`（因为当前文件frontmatter仍有该行）

- [ ] **Step 3: 改写 `skills/devflow-start-task/SKILL.md` frontmatter**

把现有：

```yaml
---
name: devflow-start-task
description: 处理一个飞书任务需求的完整 9 步流程：理解→intent.md→SPEC→sandbox→开发→验证→归因回流→Review/MR→人工确认合并。收到分配给当前仓库的飞书任务时使用。
argument-hint: ["<task-id>"]
---
```

改为：

```yaml
---
name: devflow-start-task
description: >
  处理新需求/新功能开发。触发词：新增XX、想要一个XX功能、优化XX体验、
  改成XX样式、给XX加个入口。飞书任务ID也可触发（先按语义判断任务性质，
  若判定为bug报错类应转由 devflow-fix-bug 处理）。
  走完整9步：理解→intent.md→SPEC→sandbox→开发→验证→归因回流→review→
  人工确认合并。不需要用户手动选择本skill，Claude按对话内容自动路由。
---
```

（去掉 `argument-hint`；`description` 改为需求特征词优先，说明支持自动路由且和 devflow-fix-bug 存在语义分工）

- [ ] **Step 4: 改写步骤1（原文件第39-43行）**

原文本：

```markdown
1. **需求理解 + 写 intent.md**：`lark-cli task tasks get --task-guid <task-id> --as user` 拿全字段；附件图片下载到本地用 sonnet 模型识图（识完切回默认模型）。按 `templates/INTENT-TEMPLATE.md` 写 `.ai-devflow/<task-id>/intent.md`，末尾填 `## Decision: Accept/Reject/Defer + 理由`。**Defer 型任务到此止步**——只飞书知会一句，不进入步骤 2，不产生 sandbox 与 MR。
   - **Accept 时做影响面判定**（3.2）：按需求语义 + 改动预计触及的模块/接口，判断是 **纯本仓库** / **涉及跨仓库 + 接口契约** / **纯对方仓库**。纯对方仓库 → 不接手，飞书回一句"该由 @partner 处理"，终止。
   - 命中"涉及跨仓库 + 接口契约" → intent.md 追加 `## Contract scope` 小节列候选对齐端点；且该仓库 `.ai-devflow/partner.yaml` 的 `collaboration.auto_align: true` 时，执行**阶段 0 对齐**（见下），再进步骤 2。纯本仓库任务不读 partner.yaml、不进阶段 0。
   - **阶段 0 对齐（3.2.3，auto_align 且契约影响面）**：① 把 `## Contract scope` 候选端点组织成对齐请求 @ partner 发到 `partner.yaml` 声明的群；② 等对方回复确认/拒绝（拒绝则修订重发）；③ 对方确认后，用 `${CLAUDE_PLUGIN_ROOT}/scripts/collab/contract-align.py <task-id> --endpoints '<对齐后端点 JSON>' --aligned-with <对方bot> --version 1.0` 写 `.ai-devflow/<task-id>/contract.json` + 状态机置 aligned。①失败不阻塞，回飞书说明让用户处理。
```

改为（拆开"输入来源""写intent""影响面判定"三层，且第三层"涉及跨仓库+需要对方开发"分支预留占位——具体`[handoff]`协议内容留给 Plan 3）：

```markdown
1. **理解需求**
   1.1 **输入来源二选一**：
       - 传了 task-id → `lark-cli task tasks get --task-guid <task-id> --as user`
         拿全字段；附件图片下载到本地用 sonnet 模型识图（识完切回默认模型）；
         记录触发消息的 sender（飞书事件里@机器人的那个人），供步骤3通知使用。
       - 直接对话描述需求 → 就用这段描述当输入，不产生飞书通知（无消息sender可回）。
   1.2 按 `templates/INTENT-TEMPLATE.md` 写 `.ai-devflow/<task-id>/intent.md`。
   1.3 末尾填 `## Decision: Accept/Reject/Defer + 理由`。**Defer 型任务到此止步**——
       若来源是task-id，@回触发者一句说明；不进入步骤2，不产生sandbox与MR。
   1.4 **Accept 时做影响面判定**：按需求语义 + 改动预计触及的模块/接口，判断：
       - **纯本仓库** → 直接进步骤2，不读partner.yaml
       - **涉及跨仓库·仅需对齐字段** → intent.md追加`## Contract scope`小节列候选
         对齐端点；该仓库`partner.yaml`的`collaboration.auto_align: true`时执行
         **阶段0对齐**（见下），完成后进步骤2
       - **涉及跨仓库·需要对方真正开发** → 触发机器人任务交接协议（见
         `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py`，具体消息格式与
         接收方处理逻辑见插件文档），交接后若本仓库还有剩余工作则继续步骤2，
         若整块转出则到此止步
       - **纯对方仓库** → 不接手，飞书回一句"该由 @partner 处理"，终止
   **阶段0对齐（auto_align且仅需对齐字段时）**：① 把候选端点组织成对齐请求
   @ partner 发到 `partner.yaml` 声明的群；② 等对方回复确认/拒绝（拒绝则修订
   重发）；③ 对方确认后，用
   `${CLAUDE_PLUGIN_ROOT}/scripts/collab/contract-align.py <task-id> --endpoints
   '<对齐后端点 JSON>' --aligned-with <对方bot> --version 1.0` 写
   `.ai-devflow/<task-id>/contract.json` + 状态机置 aligned。①失败不阻塞，
   回飞书说明让用户处理。
```

- [ ] **Step 5: 改写步骤3（飞书知会 → @回触发者）**

原文本第45行：

```markdown
3. **飞书知会**需求方：SPEC 路径 + 需求摘要（`lark-cli` 失败不阻塞流程）。
```

改为：

```markdown
3. **飞书通知**：若步骤1.1的输入来源是task-id，@回触发者（步骤1.1记录的
   sender）：SPEC 路径 + 需求摘要（`lark-cli` 失败不阻塞流程）。若输入来源是
   直接对话描述，跳过本步（无消息上下文可回）。
```

- [ ] **Step 6: 改写步骤8（改为调用skill:review）**

原文本第51行：

```markdown
8. **PASS → Review/建MR**：跑 `${CLAUDE_PLUGIN_ROOT}/scripts/review/ai-review.sh <sandbox_path> <task-id>` 生成 review 包（清单来自插件 `policies/REVIEW.md`，产出机读 `review.json`）；基于 review 包做 AI 判断，把 `review.json` 的 verdict 改为 PASS/FAIL；FAIL 回步骤 7。PASS 则 `${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle/create-mr.sh <sandbox_path> <task-id>` 建 MR（内部走 `glab mr create`），飞书卡片通知人工。**建完 MR 编排即告一段落**——MR 评论由用户人工在 GitLab 跟进，插件不再自动回修。
```

改为：

```markdown
8. **PASS → Review/建MR**：调用 `skill:review`（内部调用模式）生成review包并判断
   verdict；FAIL 回步骤7。PASS 则 `${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle/create-mr.sh
   <sandbox_path> <task-id>` 建 MR（内部走 `glab mr create`），飞书卡片通知人工
   （@回步骤1.1记录的触发者）。**建完 MR 编排即告一段落**——MR 评论由用户人工在
   GitLab 跟进，插件不再自动回修。
```

- [ ] **Step 7: 跑测试确认通过**

Run: `bash scripts/test/test_skill.sh`
Expected: `test_skill: ALL OK`

- [ ] **Step 8: Commit**

```bash
git add skills/devflow-start-task/SKILL.md scripts/test/test_skill.sh
git commit -m "refactor: devflow-start-task drops argument-hint, splits step1, delegates review to skill:review"
```

---

### Task 3: 新增 `devflow-fix-bug` — 5步简化流程

**Files:**
- Create: `skills/devflow-fix-bug/SKILL.md`
- Create: `skills/devflow-fix-bug/rules/severity.md`
- Create: `skills/devflow-fix-bug/failure-modes.md`
- Test: `scripts/test/test_fix_bug_skill.sh`

**Interfaces:**
- Consumes: Plan 1 的 `skills/verify/SKILL.md`（`--self-check`模式）；Task 1 的 `skills/review/SKILL.md`（内部调用模式）；现有 `agents/frontend.md`/`agents/backend.md`
- Produces: 无新程序化接口——`rules/severity.md` 的决策树被本skill正文引用；`failure-modes.md` 是文档，不被程序化读取

- [ ] **Step 1: 写测试（先写测试，红）**

```bash
#!/bin/bash
# devflow-fix-bug 结构校验：5步齐全 + severity决策树存在 + 不引用SPEC/plan重工件
# + 观测云可选结合 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/devflow-fix-bug/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/devflow-fix-bug/SKILL.md missing"; exit 1; }

grep -q '^name: devflow-fix-bug' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -qi '报错\|坏了\|不对\|复现步骤' "$SKILL" || { echo "description missing bug keywords"; exit 1; }
grep -q 'argument-hint' "$SKILL" && { echo "argument-hint should not exist"; exit 1; }

# 5步齐全
grep -q '1\. \*\*理解' "$SKILL" || { echo "step1 (理解) missing"; exit 1; }
grep -q '2\. \*\*排查' "$SKILL" || { echo "step2 (排查) missing"; exit 1; }
grep -q '3\. \*\*修复方案' "$SKILL" || { echo "step3 (修复方案) missing"; exit 1; }
grep -q '4\. \*\*开发' "$SKILL" || { echo "step4 (开发) missing"; exit 1; }
grep -q '5\. \*\*验证' "$SKILL" || { echo "step5 (验证) missing"; exit 1; }

# 不生成SPEC/plan重工件
grep -qi 'SPEC.md\|INTENT-TEMPLATE\|plan.md' "$SKILL" && { echo "must NOT reference SPEC.md/INTENT-TEMPLATE/plan.md heavy artifacts"; exit 1; }

# 观测云可选结合
grep -qi 'owl\|观测云' "$SKILL" || { echo "step2 missing observability integration"; exit 1; }
grep -qi '未配置.*跳过\|跳过.*日志辅助' "$SKILL" || { echo "step2 missing graceful skip when not configured"; exit 1; }

# 引用severity决策树 + skill:verify + skill:review
grep -q 'rules/severity.md' "$SKILL" || { echo "must reference rules/severity.md"; exit 1; }
grep -qi 'skill:verify' "$SKILL" || { echo "step5 must reference skill:verify"; exit 1; }
grep -qi 'skill:review' "$SKILL" || { echo "step5 must reference skill:review"; exit 1; }

grep -q 'CLAUDE_PLUGIN_ROOT\|owl' "$SKILL" || { echo "no external tool reference"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

# severity.md 决策树文件存在且含高风险判定
SEV="$ROOT/skills/devflow-fix-bug/rules/severity.md"
[ -f "$SEV" ] || { echo "rules/severity.md missing"; exit 1; }
grep -qi '高风险\|数据库迁移\|支付' "$SEV" || { echo "severity.md missing high-risk criteria"; exit 1; }
grep -qi '只输出排查报告\|止步' "$SEV" || { echo "severity.md missing stop-at-report rule"; exit 1; }

# failure-modes.md 存在（借用pipelit模式）
FM="$ROOT/skills/devflow-fix-bug/failure-modes.md"
[ -f "$FM" ] || { echo "failure-modes.md missing"; exit 1; }

echo "test_fix_bug_skill: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_fix_bug_skill.sh`
Expected: `skills/devflow-fix-bug/SKILL.md missing`（exit 1）

- [ ] **Step 3: 写 `skills/devflow-fix-bug/rules/severity.md`**

```markdown
# Bug 风险等级决策树

> 替代散文式判定。按优先级自上而下匹配，命中即返回，不再继续。

| 优先级 | 条件 | 判定 | 处理 |
|---|---|---|---|
| 1 | 描述含"数据库迁移"/"支付"/"资金"/"批量删除" | 高风险 | 只输出排查报告，到此止步，不进入步骤3-5 |
| 2 | 步骤2排查判定为"涉及跨仓库+需要对方开发" | 高风险 | 转入机器人任务交接协议，不在本仓库直接修 |
| 3 | grep候选文件 > 5 | 中风险 | 继续5步，但步骤5验证阶段建议触发verifier独立复核 |
| 4 | 其他 | 普通 | 继续5步，步骤5验证阶段可跳过verifier |

## 说明

- 优先级1/2判定为"高风险"时，输出内容仅限排查发现（问题定位/涉及范围/建议），
  不产生sandbox、不改代码、不建MR——这类任务风险足够高，需要人工先看排查结果
  再决定怎么处理。
- 优先级3的"中风险"不阻断流程，只是提高验证严格度建议，是否真的触发verifier
  由步骤5根据当次改动复杂度自行判断，不强制。
- 判定完成后必须输出一行log：`[severity] 判定：<高风险/中风险/普通>，命中：
  <优先级编号>`，便于事后追溯。
```

- [ ] **Step 4: 写 `skills/devflow-fix-bug/failure-modes.md`**

```markdown
# devflow-fix-bug Failure Modes

| ID | 阶段 | 触发条件 | 兜底行为 | 阻断 |
|----|------|---------|---------|------|
| F01 | 步骤1 | 描述过短且无截图/复现步骤 | AskUserQuestion补问，等待用户输入 | 暂停 |
| F02 | 步骤2 | 目标仓库未配置观测云（owl不在PATH或未声明workspace） | 跳过日志辅助，纯代码grep定位，不报错不阻塞 | 否 |
| F03 | 步骤2 | owl查询返回no_data/error/not_configured | log_summary=null，静默跳过，不展示给用户 | 否 |
| F04 | 步骤2 | severity判定为高风险 | 只输出排查报告，到此止步，不进入步骤3-5 | 是 |
| F05 | 步骤4 | frontend/backend agent自查FAIL | 修完再提交，不允许带FAIL结果commit | 暂停 |
| F06 | 步骤5 | skill:review判verdict=FAIL | 回归归因回流，不直接建MR | 否 |

## 非阻断失败的处理原则

F02/F03：静默跳过，只在内部log行记录原因，不打扰用户看到一堆"未配置"提示。
F06：不是本skill的终态失败，是正常流程分支（回归修复循环）。
```

- [ ] **Step 5: 写 `skills/devflow-fix-bug/SKILL.md`**

```markdown
---
name: devflow-fix-bug
description: >
  处理bug修复。触发词：报错、坏了、不对、显示错误、点了没反应、XX失败、
  复现步骤、截图里的异常。飞书任务ID也可触发（先按语义判断任务性质，
  若判定为新需求应转由 devflow-start-task 处理）。
  走简化5步：理解→排查→修复方案→开发→验证，不生成SPEC/plan重工件。
  不需要用户手动选择本skill，Claude按对话内容自动路由。
---

# DevFlow Fix Bug

处理bug修复的简化流程，只处理**当前仓库**的任务。与 `devflow-start-task` 的
区别：不生成 intent.md/SPEC.md 这类需求流程重工件，判定为高风险时只报告不动手。

## 前置依赖探测

```bash
command -v git && command -v glab || echo "缺失依赖请先安装（见插件README前置依赖表）"
```

## 栈判定

```bash
stack_type=$(python3 -c "import yaml; print(yaml.safe_load(open('harness.yaml'))['project']['stack']['type'])")
```

`frontend` → 用 `agents/frontend.md`；`backend` → 用 `agents/backend.md`。没有
harness.yaml则停下询问。

## 5步流程

1. **理解**：
   - **输入来源二选一**（同devflow-start-task）：
     - 传了task-id → `lark-cli`拉取全字段，记录触发消息sender
     - 直接对话描述bug → 用这段描述当输入，不产生飞书通知
   - 额外识别：复现路径/报错信息/截图（截图优先作为定位依据，含Network面板/
     URL栏/错误信息中的接口路径时直接提取完整路径）

2. **排查**：
   - 代码定位：按截图URL > 任务描述 > grep关键词的优先级定位候选文件
   - **观测云辅助**（可选）：检测目标仓库是否配置了观测云（`owl` cli是否在
     PATH + 项目是否声明观测云workspace）。
     - **配置了** → 按时间窗口推断（P1截图时间戳 > P2描述短语 > P3任务
       创建时间fallback）+ 接口路径过滤，查询错误/全量日志辅助定位
     - **未配置** → 跳过日志辅助，纯代码grep定位，不报错、不阻塞
   - 按 `rules/severity.md` 决策树判定风险等级：
     - **高风险** → 只输出排查报告（问题定位/涉及范围/建议），到此止步，
       不进入步骤3-5
     - **普通/中风险** → 继续

3. **修复方案**：写清楚要改什么/不改什么（轻量文字说明，**不生成**
   SPEC.md/plan.md）

4. **开发**：派给对应agent（frontend/backend.md）直接改代码（bug场景不需要
   Task Breakdown那套结构）

5. **验证**：
   - agent调用`skill:verify --self-check`自查
   - 调用`skill:review`（内部调用模式）生成review包并判断verdict
   - 若步骤2判定为"中风险"，可选触发`agents/verifier.md`独立复核
     （Task工具派发，同devflow-start-task步骤6-7的verifier调用方式）
   - verdict=PASS → 建MR，飞书通知（@回步骤1记录的触发者，若有）
   - verdict=FAIL → 回步骤4修复

## 异常处理

见 `failure-modes.md`。
```

- [ ] **Step 6: 跑测试确认通过**

Run: `bash scripts/test/test_fix_bug_skill.sh`
Expected: `test_fix_bug_skill: ALL OK`

- [ ] **Step 7: Commit**

```bash
git add skills/devflow-fix-bug/ scripts/test/test_fix_bug_skill.sh
git commit -m "feat: add devflow-fix-bug 5-step simplified skill with severity gating"
```

---

## Self-Review

**1. Spec coverage**：spec第3节"两个入口自动路由+去argument-hint" → Task 2 Step 3 + Task 3 Step 5 覆盖；spec第3.2节"三种输入来源" → 两个skill正文均含"输入来源二选一"（第三种机器人交接来源仅占位引用，实现留给Plan 3，已在Global Constraints声明）；spec第4节"步骤1拆细/步骤3通知改@回触发者/步骤8调用skill:review" → Task 2 Step 4-6覆盖；spec第6节"bug 5步+severity决策树+观测云可选" → Task 3全覆盖；spec决策记录"review收编为领域skill+保留手动触发" → Task 1覆盖。

**2. Placeholder scan**：所有测试脚本和SKILL.md正文均为完整内容，无TODO。Task 2 Step 4关于"机器人任务交接"的描述**有意**只给出脚本路径引用和"具体消息格式见插件文档"这种占位式表述——这不是遗漏，是显式声明的跨Plan依赖边界（该协议内容是Plan 3的范围），已在Global Constraints第2条写明这是预留而非需要在本Plan补全的空白。

**3. 类型/接口一致性**：`skill:verify --self-check`（Plan 1定义）在Task 3 Step5中被原样引用；`skill:review`（Task 1定义）在Task 2 Step6和Task 3 Step5中被原样引用，模式名未出现改名不一致。

**4. 依赖顺序**：Task 1（review skill）→ Task 2/Task 3 均依赖它，需先完成；Task 2和Task 3之间无相互依赖，可并行，但本Plan按文档顺序列出供顺序执行者参考。三个任务各自可独立commit验证。
