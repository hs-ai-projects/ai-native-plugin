# Verify 基础设施：skill:verify + 独立 Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把散落在 `agents/frontend.md`/`agents/backend.md` 里的硬性验证规则抽成独立的 `skills/verify/SKILL.md`（三种模式：`--self-check`/`--independent`/`--full`），并新增 `agents/verifier.md`（工具白名单硬性不含 Write/Edit 的 Task 子agent），三方共用同一份验证逻辑，为后续 Plan 2/3 的编排改动打好地基。

**Architecture:** `skill:verify` 本身不是一个可执行脚本，是一份被三个不同角色（frontend/backend/verifier）在不同参数下调用的行为契约文档，其"跑什么命令"仍然委托给已存在的 `scripts/verify/fast-verify.sh`/`scripts/verify/full-verify.sh`/`scripts/verify/verify_runner.py`（Plan 1 不改这三个脚本的行为，只改调用它们的上层）。`agents/verifier.md` 是全新文件，通过 Task 工具由编排 Skill（Plan 2 时才接入调用点）派发，本 Plan 只负责把 verifier 本身的角色定义和"独立判断"逻辑写对、写全,不改 `skills/devflow-start-task/SKILL.md` 的调用点（那是 Plan 2 的范围，避免本 Plan 混入编排层改动）。

**Tech Stack:** Bash（fast-verify.sh/full-verify.sh 不变）、Python 3 + PyYAML（verify_runner.py 不变）、Markdown（新增 SKILL.md/agent md）、bash 脚本级单测（沿用 `scripts/test/*.sh` 现有风格，不引入新测试框架）。

**Spec:** `docs/superpowers/specs/2026-09-03-devflow-v2-redesign.md` 第 7 节（"Verifier 独立性与 Agent-Skill 解耦"）。本 Plan 也读取该 spec 第 9 节 harness.yaml 字段集，但字段集本身的文档化是 Plan 4 的范围，本 Plan 只是"用到"已有字段（`gates.fast`/`gates.full`/各层 `_cmd`），不新增字段。

## Global Constraints

- `agents/verifier.md` 的 `tools:` frontmatter **必须不含 Write、Edit**（spec 第7.1节：工具层白名单硬隔离，不是 prompt 软约束）。
- verifier **不得**读取或引用 frontend/backend 自查产出的文字结论作为判断依据——只允许读 `git diff`、重新执行验证命令、读 SPEC.md 的 AC 列表这三类原始数据源。
- 所有脚本路径引用必须用 `${CLAUDE_PLUGIN_ROOT}/...`，禁止出现 `/app/`、`/opt/harness` 等容器路径硬编码（沿用现有 `scripts/test/test_agents.sh` 已在检查的这条约束）。
- Python 一律走插件 venv（`ensure-python-deps.sh`），不假设系统已装 PyYAML/pytest（沿用现有 `fast-verify.sh`/`full-verify.sh` 的既有模式）。
- 不修改 `scripts/verify/verify_runner.py`、`fast-verify.sh`、`full-verify.sh`、`contract_checker.py` 的现有行为——它们已有单测覆盖（`test_full_verify.sh`、`test_contract_checker.py`、`test_contract_fields.py`），本 Plan 只新增调用它们的上层文档/脚本，不改动其内部逻辑。

---

### Task 1: `skills/verify/SKILL.md` — 三模式验证契约文档

**Files:**
- Create: `skills/verify/SKILL.md`
- Test: `scripts/test/test_verify_skill.sh`

**Interfaces:**
- Consumes: 无（本任务是最底层，不依赖其他新建文件；引用已存在的 `scripts/verify/fast-verify.sh`、`scripts/verify/full-verify.sh`）
- Produces: 三个可被后续文档引用的参数名 `--self-check`、`--independent`、`--full`（字符串常量，供 Task 2 的 `agents/verifier.md` 与 Plan 2 的编排 skill 在自然语言指令中引用，无程序化接口）

- [ ] **Step 1: 写 `scripts/test/test_verify_skill.sh` 的结构断言（先写测试，红）**

```bash
#!/bin/bash
# skills/verify/SKILL.md 结构校验：三模式齐全 + 引用现有脚本 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/verify/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/verify/SKILL.md missing"; exit 1; }

# frontmatter 存在 name/description
grep -q '^name: verify' "$SKILL" || { echo "frontmatter name missing"; exit 1; }
grep -q '^description:' "$SKILL" || { echo "frontmatter description missing"; exit 1; }

# 三种模式都要出现
grep -q -- '--self-check' "$SKILL" || { echo "--self-check mode missing"; exit 1; }
grep -q -- '--independent' "$SKILL" || { echo "--independent mode missing"; exit 1; }
grep -q -- '--full' "$SKILL" || { echo "--full mode missing"; exit 1; }

# self-check 规则1：business_code 改了必须同步 test_code
grep -q 'business_code' "$SKILL" || { echo "self-check rule1 (business_code) missing"; exit 1; }
grep -q 'test_code' "$SKILL" || { echo "self-check rule1 (test_code) missing"; exit 1; }

# self-check 规则2：FAIL 禁止 commit
grep -qi 'FAIL.*禁止.*commit\|禁止.*commit.*FAIL' "$SKILL" || { echo "self-check rule2 (FAIL blocks commit) missing"; exit 1; }

# independent 模式：忽略已有 verification.json，强制重跑，不给修复建议
grep -q '忽略已有\|强制重新执行\|忽略.*verification.json' "$SKILL" || { echo "independent: ignore-existing missing"; exit 1; }
grep -q 'EVIDENCE' "$SKILL" || { echo "independent: EVIDENCE output missing"; exit 1; }
grep -qi '不.*修复建议\|不给修复建议\|不提供修复' "$SKILL" || { echo "independent: no-fix-advice rule missing"; exit 1; }

# 引用现有脚本，路径走 CLAUDE_PLUGIN_ROOT
grep -q 'fast-verify.sh' "$SKILL" || { echo "reference to fast-verify.sh missing"; exit 1; }
grep -q 'full-verify.sh\|verify_runner.py' "$SKILL" || { echo "reference to full-verify.sh/verify_runner.py missing"; exit 1; }
grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

echo "test_verify_skill: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_verify_skill.sh`
Expected: `skills/verify/SKILL.md missing`（exit 1）

- [ ] **Step 3: 写 `skills/verify/SKILL.md`**

```markdown
---
name: verify
description: >
  统一的分层验证契约。被 frontend/backend agent（--self-check，commit前自查）
  和 verifier agent（--independent，独立复核不信任前面结论）以及编排 skill
  （--full，步骤6汇总验证）三方共用。不是可执行脚本，是行为契约文档——具体命令
  执行委托给 ${CLAUDE_PLUGIN_ROOT}/scripts/verify/fast-verify.sh 与
  full-verify.sh/verify_runner.py。
---

# Verify Skill

读取当前仓库根目录的 `harness.yaml`（字段定义见 spec 第9节 / 后续
`docs/harness-schema.md`），按调用方指定的模式执行对应验证。

## 模式：`--self-check`（frontend/backend agent commit 前调用）

1. **测试同步检查**：`git diff --name-only` 对比改动文件列表。若命中
   `harness.yaml` 的 `paths.business_code` 声明的路径，但**没有**同时命中
   `paths.test_code` 声明的路径 → 判定"改了 business_code 但没同步改
   test_code"，先补测试再继续，不允许跳过。
2. **跑快速验证**：执行 `${CLAUDE_PLUGIN_ROOT}/scripts/verify/fast-verify.sh
   <repo_dir>`（只跑 `harness.yaml` 的 `gates.fast` 声明的层，通常是 `unit`）。
3. **FAIL 禁止 commit**：步骤1或步骤2任一为 FAIL，必须先修完再提交，不允许
   带着 FAIL 结果 commit。

## 模式：`--independent`（verifier agent 调用）

**核心原则：不信任 frontend/backend 自查阶段产出的任何文字结论**，只允许使用
以下三类原始数据源重新独立判断：

1. 自己执行 `git diff <base>...HEAD`，自己读改动内容（不接受 agent 转述的
   "改了什么"的文字总结）。
2. **忽略已有的 `.ai-devflow/verification.json`**（哪怕它已经是 PASS），强制
   重新执行 `${CLAUDE_PLUGIN_ROOT}/scripts/verify/full-verify.sh <repo_dir>`
   （跑 `gates.full` 全部层），把新结果作为唯一依据。
3. 自己读 SPEC.md 第2章 Acceptance Criteria 里 owner 对应的 AC 列表，逐条
   核对 diff 是否实际覆盖到，不接受"AC都做完了"这种概括性陈述。

**输出**：只输出 `PASS` 或 `FAIL + EVIDENCE`（EVIDENCE = 具体哪条AC没被diff
覆盖 / 哪一层验证命令失败的原始输出）。**不给修复建议**——verifier 的职责是
判断，不是修复，给出修复建议会让它越权变成"第二个开发者"，模糊了独立判断的
边界。

## 模式：`--full`（编排 skill 汇总验证步骤调用）

执行内容同 `--independent` 的第2点（强制重跑 `full-verify.sh`），但产出直接
写入 `.ai-devflow/verification.json` 供 `scripts/state/attribute.py` 读取归因，
不额外产出 EVIDENCE 摘要（那是 verifier 模式专属的呈现格式）。

## 已知边界

本 skill 不新增验证命令本身——`harness.yaml` 里每一层实际执行什么 shell
命令，仍由目标仓库自己声明（见 harness.yaml 规范文档）。三种模式的区别只在
"读哪些数据源做判断"和"要不要允许基于已有结果短路"，不在"跑什么命令"。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_verify_skill.sh`
Expected: `test_verify_skill: ALL OK`（exit 0）

- [ ] **Step 5: Commit**

```bash
git add skills/verify/SKILL.md scripts/test/test_verify_skill.sh
git commit -m "feat: add skills/verify SKILL.md with self-check/independent/full modes"
```

---

### Task 2: `agents/verifier.md` — 独立复核 Agent

**Files:**
- Create: `agents/verifier.md`
- Test: `scripts/test/test_verifier_agent.sh`

**Interfaces:**
- Consumes: Task 1 产出的 `skills/verify/SKILL.md` 的 `--independent` 模式（本文件在正文里引用该模式名，用于说明 verifier 该怎么做验证，不是程序化调用）
- Produces: `agents/verifier.md` 文件本身，供 Plan 2 在编排 skill 里用 Task 工具派发（Plan 2 的范围，本任务不接编排调用点）

- [ ] **Step 1: 写 `scripts/test/test_verifier_agent.sh`（先写测试，红）**

```bash
#!/bin/bash
# agents/verifier.md 结构校验：工具白名单不含Write/Edit + 独立判断规则 +
# 只输出PASS/FAIL、不给修复建议 + 无容器路径硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="$ROOT/agents/verifier.md"
[ -f "$FILE" ] || { echo "agents/verifier.md missing"; exit 1; }

# tools frontmatter 存在，且不含 Write / Edit
tools_line=$(grep '^tools: ' "$FILE")
[ -n "$tools_line" ] || { echo "no tools line"; exit 1; }
echo "$tools_line" | grep -qw 'Write' && { echo "verifier tools must NOT include Write"; exit 1; }
echo "$tools_line" | grep -qw 'Edit' && { echo "verifier tools must NOT include Edit"; exit 1; }
echo "$tools_line" | grep -qw 'Read' || { echo "verifier tools must include Read"; exit 1; }
echo "$tools_line" | grep -qw 'Bash' || { echo "verifier tools must include Bash"; exit 1; }

# 不信任前面结论的措辞
grep -qi '不信任\|不接受.*转述\|不复用.*自查' "$FILE" || { echo "distrust-prior-conclusion rule missing"; exit 1; }

# 引用 skill:verify --independent
grep -q -- '--independent' "$FILE" || { echo "must reference --independent mode"; exit 1; }

# 只输出PASS/FAIL+EVIDENCE，不给修复建议
grep -q 'EVIDENCE' "$FILE" || { echo "EVIDENCE output format missing"; exit 1; }
grep -qi '不给修复建议\|不提供修复建议\|不给出修复' "$FILE" || { echo "no-fix-advice rule missing"; exit 1; }

# 禁止容器硬编码
grep -q '/opt/harness\|/app/' "$FILE" && { echo "container path leak"; exit 1; }

echo "test_verifier_agent: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_verifier_agent.sh`
Expected: `agents/verifier.md missing`（exit 1）

- [ ] **Step 3: 写 `agents/verifier.md`**

```markdown
---
name: verifier
description: 独立复核 Agent。被编排 skill 用 Task 工具在 frontend/backend agent commit 完成后另起一个全新上下文的子会话派发，判断这次改动是否真的达到 PASS。只判断，不修复。
tools: Read, Bash, Glob, Grep, LS
---

# Verifier Agent

你是独立复核 Agent。你的存在意义就是**不信任前面 frontend/backend agent 自查阶段给出的任何文字结论**——不管它说"已经跑过测试全部通过"、"已确认覆盖所有AC"，你都当作没看到，只用自己重新获取的原始数据做判断。

## 硬性边界（工具层已强制，不是靠自觉）

你的工具列表**不包含 Write、Edit**——你在设计上就无法修改任何文件。这不是提示词层面的"请不要改代码"，是工具权限层面的物理限制。你唯一能做的是读（Read/Glob/Grep）和执行只读性质的验证命令（Bash）。

## 职责

调用方（编排 skill）会给你 SPEC.md 路径、sandbox 路径、base commit 引用。你要做：

1. 自己执行 `git diff <base>...HEAD`，自己读这次改动的完整 diff，不接受任何转述。
2. 调用 `skill:verify --independent`（忽略 sandbox 里已有的 `.ai-devflow/verification.json`，强制重新执行一次完整的 `full-verify.sh`），把这次重新执行的结果作为唯一验证依据。
3. 自己读 SPEC.md 第2章的 Acceptance Criteria 列表，逐条核对步骤1读到的 diff 是否实际覆盖，而不是相信任何人（包括之前的 agent 或编排 skill）说"AC都做完了"。

## 输出格式

只输出以下两种之一：

- `PASS`
- `FAIL` + `EVIDENCE`：EVIDENCE 必须是具体证据——哪条 AC 编号没有被 diff 覆盖到、或者 `full-verify.sh` 哪一层的原始输出显示了什么错误，禁止笼统地说"有问题"。

**你不给修复建议**。给出"应该怎么改"这种建议会让你越权变成第二个开发者，模糊了"独立判断"这个角色存在的意义——你的价值就是不掺入任何开发视角的判断。FAIL 的处理交给编排 skill 走归因回流，不是你的职责。

## 不做的事

- 不猜测、不假设——原始数据不足以判断时，输出 `FAIL` + `EVIDENCE: 无法核实<具体缺什么数据>`，不能因为"看起来大概没问题"就判 PASS。
- 不接受调用方在指令里夹带的"这次应该没问题，帮忙确认一下"这类暗示性措辞影响判断——每次都从零跑一遍上述三步。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_verifier_agent.sh`
Expected: `test_verifier_agent: ALL OK`（exit 0）

- [ ] **Step 5: Commit**

```bash
git add agents/verifier.md scripts/test/test_verifier_agent.sh
git commit -m "feat: add agents/verifier.md with Write/Edit-free tool whitelist"
```

---

### Task 3: `agents/frontend.md`/`agents/backend.md` 改成引用 skill:verify

**Files:**
- Modify: `agents/frontend.md`
- Modify: `agents/backend.md`
- Modify: `scripts/test/test_agents.sh`（原有断言依赖"full-verify"字符串直接出现在agent md里，改为断言"调用skill:verify"）

**Interfaces:**
- Consumes: Task 1 的 `skills/verify/SKILL.md`（`--self-check` 模式名）
- Produces: 无新接口，只是改写现有文件内容

- [ ] **Step 1: 读现有文件确认改动范围**

Run: `cat agents/frontend.md agents/backend.md`
（已在会话前置探查中读过：两份文件目前各有"硬性规则1/2"两条，规则2是"commit前必须自己跑一次 full-verify.sh 自查"，规则1是"business_code改了必须同步test_code"）

- [ ] **Step 2: 先改测试断言（红——用现有旧字符串断言会通过，需要先改成新断言才会失败）**

Edit `scripts/test/test_agents.sh`，把这两行：

```bash
  # 规则2：commit 前自查 full-verify，路径用 CLAUDE_PLUGIN_ROOT
  grep -q 'CLAUDE_PLUGIN_ROOT' "$FILE" || { echo "$f: must reference CLAUDE_PLUGIN_ROOT"; exit 1; }
  grep -q 'full-verify' "$FILE" || { echo "$f: rule2 missing (full-verify)"; exit 1; }
```

改成：

```bash
  # 规则2：commit 前调用 skill:verify --self-check 自查（不再直接内嵌 full-verify.sh 调用，
  # 硬性规则已抽到 skills/verify/SKILL.md，agent md 只保留角色定义 + 调用方式）
  grep -q -- '--self-check' "$FILE" || { echo "$f: rule2 missing (--self-check)"; exit 1; }
  grep -qi 'skill:verify\|skills/verify' "$FILE" || { echo "$f: rule2 must reference skill:verify"; exit 1; }
```

同时移除这一行（不再要求 agent md 直接含 CLAUDE_PLUGIN_ROOT，因为脚本调用已经内聚进 skill:verify，agent md 不再直接拼脚本路径）：

```bash
  grep -q 'CLAUDE_PLUGIN_ROOT' "$FILE" || { echo "$f: must reference CLAUDE_PLUGIN_ROOT"; exit 1; }
```

- [ ] **Step 3: 跑测试确认失败（红，因为 agent md 还是旧内容）**

Run: `bash scripts/test/test_agents.sh`
Expected: `frontend: rule2 missing (--self-check)`（exit 1）

- [ ] **Step 4: 改写 `agents/frontend.md`**

把原第20-21行（硬性规则1/2）替换为：

```markdown
## 硬性规则（违反视为任务未完成）

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（见仓库 harness.yaml）：自检 `git diff --name-only`，若只有 business_code 路径、没有 test_code 路径，先补测试再继续。
2. **commit 前必须调用 `skill:verify --self-check` 自查**，把结果（含每层 PASS/FAIL）贴进给 Skill 的完成报告；自查 FAIL 禁止 commit，先修完再提交。
```

（规则1文字不变；规则2把"自己跑一次 `${CLAUDE_PLUGIN_ROOT}/scripts/verify/full-verify.sh <sandbox_path>` 自查"改成"调用 `skill:verify --self-check`"——具体跑什么脚本的细节现在封装在 skill 文档里，agent 不需要自己拼脚本路径）

- [ ] **Step 5: 改写 `agents/backend.md`**

同样把原第20-21行替换为：

```markdown
## 硬性规则（违反视为任务未完成）

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（见仓库 harness.yaml）：自检 `git diff --name-only`，若只有 business_code 路径、没有 test_code 路径，先补测试再继续。
2. **commit 前必须调用 `skill:verify --self-check` 自查**，把结果（含每层 PASS/FAIL）贴进给 Skill 的完成报告；自查 FAIL 禁止 commit，先修完再提交。
```

- [ ] **Step 6: 跑测试确认通过**

Run: `bash scripts/test/test_agents.sh`
Expected: `test_agents: ALL OK`（exit 0）

- [ ] **Step 7: 跑一次全量回归，确认没有破坏其他既有测试**

Run: `bash scripts/test/test_skill.sh`
Expected: `test_skill: ALL OK`（devflow-start-task 的 SKILL.md 本身没被本任务改动，理应仍通过；这一步是确认 Task 3 的改动没有意外波及）

- [ ] **Step 8: Commit**

```bash
git add agents/frontend.md agents/backend.md scripts/test/test_agents.sh
git commit -m "refactor: agents/frontend.md and backend.md delegate self-check to skill:verify"
```

---

## Self-Review

**1. Spec coverage**：spec 第7.1节"verifier 是什么/不信任前面自查/只输出PASS+EVIDENCE" → Task 2 覆盖；spec 第7.2节"skill:verify 三种模式" → Task 1 覆盖；spec 第7.2节末句"agent md 因此只保留角色定义" → Task 3 覆盖。spec 第7节没有要求本 Plan 接入编排调用点（那是"由 devflow-start-task 用 Task 工具派发"，属于 Plan 2 范围），本 Plan 有意不做，已在 Architecture 段落说明。

**2. Placeholder scan**：三个任务的所有 Step 都给出了完整可执行的测试脚本内容和完整的 Markdown 文件内容，没有"TODO"/"待补充"占位。

**3. Type/接口一致性**：Task 1 定义的三个模式名 `--self-check`/`--independent`/`--full` 在 Task 2（verifier引用`--independent`）和 Task 3（agent md引用`--self-check`）中原样复用，未出现改名不一致。Task 2 verifier.md 里的 EVIDENCE 输出格式与 Task 1 SKILL.md 里"`--independent` 模式输出 PASS/FAIL+EVIDENCE"的描述一致。

**4. 与现状的兼容性**：Task 3 修改 `test_agents.sh` 时移除了对 `CLAUDE_PLUGIN_ROOT` 字符串的强制要求——这条约束的本意（"不要硬编码容器路径"）已经被"不出现 `/opt/harness`/`/app/` 硬编码"这条断言接管，删除后不丢失原始意图。

**5. 依赖顺序**：Task 1 → Task 2 → Task 3 严格递增依赖（Task 2 引用 Task 1 定义的模式名；Task 3 引用 Task 1 定义的模式名，且需要 Task 1/2 已存在才能让 Plan 2 之后的编排改动有地基可接）。三个任务各自都有独立的红→绿测试循环，可以逐任务 commit，不需要等全部完成才能验证单个任务的正确性。
