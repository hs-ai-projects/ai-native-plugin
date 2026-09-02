# AI-Native DevFlow 插件化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ai-native` 仓库跑在 Docker 容器里的 devflow 流水线，改造为标准 Claude Code 插件 `ai-native-plugin`，装进任意单个仓库即可用，完整保留 SPEC 工件化 / 验证 / 归因回流 / AI Review / MR / 人工确认合并 / 埋点能力。

**Architecture:** 插件仓库本身同时是自己的 marketplace。五个部分按依赖顺序落地：(1) `.claude-plugin/`（plugin.json + marketplace.json）让插件可被 `claude plugin install`；(2) `agents/` 两个 persona；(3) `skills/devflow-start-task/` 9 步编排 + 三个模板；(4) `scripts/` 从 ai-native 移植全部业务脚本，硬编码 `/app` 路径改为 `${CLAUDE_PLUGIN_ROOT}`（插件脚本）与仓库相对 `.ai-devflow/`（运行时产物），GitLab 全部走 `glab`；(5) `hooks/` + `policies/REVIEW.md`。**Windows 注意**：hooks 命令不能直接写 `.sh` 路径（win32 下 hook 走 CMD/PowerShell，解析不了），必须用 superpowers 插件验证过的 polyglot dispatcher 模式（`hooks/run-hook.cmd` + 无扩展名脚本）。

**Tech Stack:** Bash（脚本/hook + `.sh` 测试）、Python 3 + PyYAML/pytest/httpx（`verify_runner.py`/`contract_checker.py`/`check-bands.py`/埋点）、Claude Code 插件规范（`.claude-plugin/`、skills frontmatter、hooks.json）、`glab` CLI（GitLab MR）。

**Spec:** [docs/superpowers/specs/2026-09-01-devflow-plugin-architecture-design.md](../specs/2026-09-01-devflow-plugin-architecture-design.md)（第 4-7 节）。实现从这份 spec 论证，执行者需同时读 spec 与本文档。

**移植源**：`c:\Users\otsan.li\Desktop\work\ai-native\`（只读，不修改；每个脚本标注源文件路径，逐行对照移植）。

## Global Constraints

- **不自动 commit**：每个 Task 完成后由用户决定是否提交（用户全局规则）。
- **不修改源仓库**：只从 `ai-native/` 读取复制，不在里面写任何东西。
- **路径约定**（贯穿所有任务）：
  - 插件内脚本一律用 `${CLAUDE_PLUGIN_ROOT}/scripts/...` 引用（插件被装进哪台机器都成立）。
  - 运行时产物一律仓库相对路径 `.ai-devflow/`（verification.json、events、repair-state、review.json、bands-alerts、HUMAN_APPROVED），**不再有任何 `/app/...` 硬编码**。各脚本默认值改为 `os.getcwd()`/`$PWD` 下的 `.ai-devflow`。
  - Python 解释器一律由 `${CLAUDE_PLUGIN_ROOT}/scripts/ensure-python-deps.sh` 输出（自建 venv 到 `${CLAUDE_PLUGIN_DATA}/venv`），不假设系统已装 PyYAML/pytest/httpx。
- **GitLab 只走 `glab` CLI**：建 MR=`glab mr create`，查状态=`glab mr view`/`glab mr note list`，合并=`glab mr merge`。任何脚本不允许直接拼 GitLab REST API。
- **去掉 `make-sandbox.sh`**：worktree 隔离由 SKILL 步骤 4 直接执行 `git worktree add`，不移植该脚本（spec 第 2 节决策）。
- **去掉评审回路**：MR 建开后插件不再自动回修评论（spec 第 2 节决策）；`finish-task.sh` 不调用 `glab mr note list` 检查未解决评论。
- **9 步编排**：spec 第 6 节（不是旧 10 步）；Defer 型任务到 intent.md 止步，不产生 sandbox 与 MR。
- **`.env`/secrets deny 暂缓**：`deny-secrets.sh` 只落文件（`scripts/hooks/deny-secrets.sh`），**不接进 hooks.json**（spec 第 2 节 + 第 9 节）。
- **插件命名**：插件名 `ai-native-plugin`，marketplace 名 `ai-native-plugin-marketplace`，Skill 调用名 `/ai-native-plugin:devflow-start-task`（spec 第 4 节调用名订正）。
- **栈判定**：读当前仓库 `harness.yaml` 的 `project.stack.type`（frontend/backend）决定 persona 与验证层（spec 3.1，不新增配置）。

---

## 任务总览与依赖

| Phase | Task | 交付物 | 依赖 |
|---|---|---|---|
| A 骨架 | Task 1 | `.claude-plugin/` + README + polyglot hooks 基础设施 | 无 |
| B agents | Task 2 | `agents/frontend.md` + `agents/backend.md` | Task 1 |
| C 编排 | Task 3 | 3 个模板 + `skills/devflow-start-task/SKILL.md` | Task 1, 2 |
| D 脚本 | Task 4 | `ensure-python-deps.sh` + `verify_runner.py`（四态化） | Task 1 |
| D 脚本 | Task 5 | `attribute.py`（subtype 直判）+ `repair-counter.py` | Task 4 |
| D 脚本 | Task 6 | `ai-review.sh`（REVIEW.md 动态）+ `policies/REVIEW.md` | Task 4 |
| D 脚本 | Task 7 | `contract_checker.py` + `check-bands.py` | Task 4 |
| D 脚本 | Task 8 | `create-mr.sh` / `finish-task.sh`（glab）/ 埋点 4 件套 | Task 4 |
| E hooks | Task 9 | `protect-paths.sh` + `approval-gate.sh` + `hooks/hooks.json` | Task 1 |

---

## Phase A — 插件骨架

### Task 1: `.claude-plugin/` + marketplace + hooks 基础设施

让插件可安装 + Windows/Linux 双平台 hooks 可跑。

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `README.md`
- Create: `hooks/run-hook.cmd`（Windows polyglot dispatcher）
- Create: `hooks/hooks.json`
- Create: `scripts/hooks/.gitkeep`（占位，后续 Task 9 放 hook 脚本）
- Create: `agents/.gitkeep`、`skills/.gitkeep`、`policies/.gitkeep`、`scripts/test/.gitkeep`
- Test: `scripts/test/test_plugin_manifest.sh`

**Interfaces:**
- Produces: `plugin.json`（name 必填）、`marketplace.json`（`name`/`owner.name`/`plugins[0].source`）、`hooks/hooks.json`（事件挂载点，Task 9 往里填 command）、`hooks/run-hook.cmd`（被 hooks.json 引用的跨平台 dispatcher，Task 9 的 hook 脚本经它调用）。

- [ ] **Step 1: 写失败测试 `scripts/test/test_plugin_manifest.sh`**

```bash
#!/bin/bash
# 插件 manifest 结构校验：能装上是插件化改造的第一验收标准。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

[ -f "$ROOT/.claude-plugin/plugin.json" ] || { echo "plugin.json missing"; exit 1; }
[ -f "$ROOT/.claude-plugin/marketplace.json" ] || { echo "marketplace.json missing"; exit 1; }
[ -f "$ROOT/hooks/run-hook.cmd" ] || { echo "hooks/run-hook.cmd missing"; exit 1; }

# plugin.json 必须有 name
python3 - "$ROOT/.claude-plugin/plugin.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("name") == "ai-native-plugin", f'name={d.get("name")}'
print("plugin.json name: OK")
PY

# marketplace.json：source 必须是相对路径 "./"，同仓库分发
python3 - "$ROOT/.claude-plugin/marketplace.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("name") == "ai-native-plugin-marketplace"
p = d["plugins"][0]
assert p["name"] == "ai-native-plugin"
assert p.get("source") == "./", f'source={p.get("source")}'
print("marketplace.json: OK")
PY

echo "test_plugin_manifest: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/test/test_plugin_manifest.sh`
Expected: `plugin.json missing`（文件还不存在）。

- [ ] **Step 3: 创建 `.claude-plugin/plugin.json`**

```json
{
  "name": "ai-native-plugin",
  "version": "0.1.0",
  "description": "AI-Native DevFlow：装进任意仓库即可跑通 SPEC→验证→归因→Review→MR→人工合并→埋点全流程",
  "author": {
    "name": "otsan"
  }
}
```

- [ ] **Step 4: 创建 `.claude-plugin/marketplace.json`**

```json
{
  "name": "ai-native-plugin-marketplace",
  "owner": {
    "name": "otsan"
  },
  "plugins": [
    {
      "name": "ai-native-plugin",
      "version": "0.1.0",
      "source": "./"
    }
  ]
}
```

- [ ] **Step 5: 创建 `hooks/run-hook.cmd`（Windows polyglot dispatcher）**

直接照搬已验证的 superpowers 插件 dispatcher 模式（`docs/windows/polyglot-hooks.md` 的 canonical 实现，见 `C:\Users\otsan.li\.claude\plugins\cache\claude-plugins-official\superpowers\6.3.0\hooks\run-hook.cmd`），逐行对照复制并保持文件一致：

```cmd
@echo off
rem Cross-platform hook dispatcher: Windows uses CMD batch block below,
rem Unix shells treat it as a no-op heredoc and exec the named script.
2>NUL & goto :EOF
:<<'CMDBLOCK'
setlocal
set "HOOK_NAME=%~1"
if "%HOOK_NAME%"=="" exit /b 0
set "HOOK_DIR=%~dp0"
for %%P in ("%ProgramFiles%\Git\bin\bash.exe" "%ProgramFiles(x86)%\Git\bin\bash.exe") do if exist %%P (
  "%%P" "%HOOK_DIR%%HOOK_NAME%"
  exit /b %ERRORLEVEL%
)
where bash >nul 2>nul && (
  bash "%HOOK_DIR%%HOOK_NAME%"
  exit /b %ERRORLEVEL%
)
exit /b 0
CMDBLOCK
#!/bin/bash
set -u
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_NAME="$1"
[ -n "$HOOK_NAME" ] || exit 0
exec bash "$HOOK_DIR/$HOOK_NAME"
```

> 注意：上面的 bat/bash 混合块必须按 superpowers 原文件逐字节对照，`2>NUL & goto :EOF` 第一行是关键（CMD 吞掉后续 bash 段）。执行时以复制 superpowers 原文件 + 校验行为一致为准，不手写变体。

- [ ] **Step 6: 创建 `hooks/hooks.json`（先挂 PostToolUse，Task 9 补 PreToolUse）**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\"",
            "shell": "bash",
            "async": false
          }
        ]
      }
    ]
  }
}
```

> 说明：spec 第 4 节直接写 `${CLAUDE_PLUGIN_ROOT}/scripts/hooks/protect-paths.sh` 在 Linux 容器成立，但在 win32 下 hook 经 CMD/PowerShell 调用解析不了。这里统一走 `run-hook.cmd` dispatcher（Task 9 在 `run-hook.cmd` 内部按 hook 名分发到对应无扩展名脚本），路径带引号（`CLAUDE_PLUGIN_ROOT` 可能含空格）。

- [ ] **Step 7: 创建占位目录文件**

```bash
mkdir -p agents skills policies scripts/hooks scripts/test
touch agents/.gitkeep skills/.gitkeep policies/.gitkeep scripts/hooks/.gitkeep scripts/test/.gitkeep
```

- [ ] **Step 8: 创建 `README.md`（前置依赖声明）**

```markdown
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

Python 包（pyyaml/pytest/httpx）由 `scripts/ensure-python-deps.sh` 首次运行时自动装入
`${CLAUDE_PLUGIN_DATA}/venv`（卸载插件自动清理），不污染目标仓库环境。

## 使用

```bash
/ai-native-plugin:devflow-start-task <task-id>
```

目标仓库需要：`harness.yaml`（声明 stack.type + 分层测试命令）、`CLAUDE.md`（团队组织知识）。
```

- [ ] **Step 9: 跑测试确认全绿**

Run: `bash scripts/test/test_plugin_manifest.sh`
Expected: `test_plugin_manifest: ALL OK`。

- [ ] **Step 10: 提交（需用户确认）**

```bash
git add .claude-plugin hooks README.md scripts/test/test_plugin_manifest.sh
git commit -m "feat(plugin): 插件骨架——.claude-plugin 清单 + marketplace + 跨平台 hooks 基础设施"
```

---

## Phase B — Agent 定义

### Task 2: `agents/frontend.md` + `agents/backend.md`

从 `ai-native/devflow/agents/frontend.md`、`backend.md`、`test.md` 移植，并入 test/verifier 职责（spec 第 5 节），路径全部改 `${CLAUDE_PLUGIN_ROOT}`。

**Files:**
- Create: `agents/frontend.md`
- Create: `agents/backend.md`
- Test: `scripts/test/test_agents.sh`

**Interfaces:**
- Produces: 两个 persona 文件，供 SKILL 步骤 5 派发开发时引用。规则 2（自查 full-verify）被 SKILL 步骤 6 复核为"完成报告必含自查结果"。
- Consumes: `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh`（Task 4 才建，先写文件不执行）。

- [ ] **Step 1: 写失败测试 `scripts/test/test_agents.sh`**

```bash
#!/bin/bash
# agents/*.md 结构校验：工具白名单 + 两条硬性规则存在 + 无容器硬编码路径。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

for f in frontend backend; do
  FILE="$ROOT/agents/$f.md"
  [ -f "$FILE" ] || { echo "agents/$f.md missing"; exit 1; }
  grep -q '^tools: ' "$FILE" || { echo "$f: no tools line"; exit 1; }
  # 规则1：business_code 改必须同步 test_code
  grep -q 'business_code' "$FILE" || { echo "$f: rule1 missing (business_code)"; exit 1; }
  grep -q 'test_code' "$FILE" || { echo "$f: rule1 missing (test_code)"; exit 1; }
  # 规则2：commit 前自查 full-verify，路径用 CLAUDE_PLUGIN_ROOT
  grep -q 'CLAUDE_PLUGIN_ROOT' "$FILE" || { echo "$f: must reference CLAUDE_PLUGIN_ROOT"; exit 1; }
  grep -q 'full-verify' "$FILE" || { echo "$f: rule2 missing (full-verify)"; exit 1; }
  # 禁止容器硬编码
  grep -q '/opt/harness\|/app/' "$FILE" && { echo "$f: container path leak"; exit 1; }
done
# frontend 专属 model: sonnet（spec 第 5 节）
grep -q 'model: sonnet' "$ROOT/agents/frontend.md" || { echo "frontend: model sonnet missing"; exit 1; }
# 不再有独立 test agent（spec 第 2 节：并入 frontend/backend）
[ -f "$ROOT/agents/test.md" ] && { echo "agents/test.md should not exist"; exit 1; }
echo "test_agents: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/test/test_agents.sh`
Expected: `agents/frontend.md missing`。

- [ ] **Step 3: 创建 `agents/frontend.md`**

```markdown
---
name: frontend
description: 前端开发 Agent。被 devflow-start-task Skill 分配 SPEC 中 owner: frontend 的 Task 时使用。独立负责改代码+写测试+commit 前自查。
tools: Read, Write, Edit, Bash, Glob, Grep, LS
model: sonnet
---

# Frontend Agent

你是前端开发 Agent。只按 SPEC.md 中 owner: frontend 的 AC 和 Task 项工作，不接收口头需求变更，不修改不属于你的文件。

## 职责

- 在 Skill 分配的 sandbox worktree 内改代码（路径由 Skill 告知）。
- 跑 `${CLAUDE_PLUGIN_ROOT}/scripts/fast-verify.sh <sandbox_path>` 确认前端单元测试通过。
- 在沙箱分支内自行 commit（首行 `feat:` 或 `fix:`，空行后 `Feishu Task: <task-id>`）；不 push、不 merge。

## 硬性规则（违反视为任务未完成）

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（见仓库 harness.yaml）：自检 `git diff --name-only`，若只有 business_code 路径、没有 test_code 路径，先补测试再继续。
2. **commit 前必须自己跑一次 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh <sandbox_path>` 自查**，把 verification 结果（含每层 PASS/FAIL）贴进给 Skill 的完成报告；自查 FAIL 禁止 commit，先修完再提交。

## 视觉/渲染类 AC

AC 涉及布局、重叠、遮挡、对齐时，只断言 computed 属性/对象结构的测试不算完成——必须真实渲染 + DOM/SVG 几何坐标断言（`getBoundingClientRect` 相交判断）+ 负对照（还原 bug 版本确认测试会失败）。截图存 `<sandbox_path>/.ai-devflow/artifacts/` 供人工审阅。
```

- [ ] **Step 4: 创建 `agents/backend.md`**

```markdown
---
name: backend
description: 后端开发 Agent。被 devflow-start-task Skill 分配 SPEC 中 owner: backend 的 Task 时使用。独立负责改代码+写测试+commit 前自查。
tools: Read, Write, Edit, Bash, Glob, Grep, LS
---

# Backend Agent

你是后端开发 Agent。只按 SPEC.md 中 owner: backend 的 AC 和 Task 项工作，不接收口头需求变更，不修改不属于你的文件。

## 职责

- 在 Skill 分配的 sandbox worktree 内改代码（路径由 Skill 告知）。
- 跑 `${CLAUDE_PLUGIN_ROOT}/scripts/fast-verify.sh <sandbox_path>` 确认后端单元测试通过。
- 在沙箱分支内自行 commit（首行 `feat:` 或 `fix:`，空行后 `Feishu Task: <task-id>`）；不 push、不 merge。

## 硬性规则（违反视为任务未完成）

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（见仓库 harness.yaml）：自检 `git diff --name-only`，若只有 business_code 路径、没有 test_code 路径，先补测试再继续。
2. **commit 前必须自己跑一次 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh <sandbox_path>` 自查**，把 verification 结果（含每层 PASS/FAIL）贴进给 Skill 的完成报告；自查 FAIL 禁止 commit，先修完再提交。
```

- [ ] **Step 5: 跑测试确认全绿**

Run: `bash scripts/test/test_agents.sh`
Expected: `test_agents: ALL OK`。

- [ ] **Step 6: 提交（需用户确认）**

```bash
git add agents scripts/test/test_agents.sh
git commit -m "feat(agents): frontend/backend persona 并入 test+verifier 自查职责"
```

---

## Phase C — 编排 Skill 与模板

### Task 3: `skills/devflow-start-task/` 9 步编排 + 3 个模板

**Files:**
- Create: `skills/devflow-start-task/templates/INTENT-TEMPLATE.md`
- Create: `skills/devflow-start-task/templates/SPEC-TEMPLATE.md`
- Create: `skills/devflow-start-task/templates/CLAUDE-SUPPLEMENT.md`
- Create: `skills/devflow-start-task/SKILL.md`
- Test: `scripts/test/test_skill.sh`

**Interfaces:**
- Produces: Skill 调用名 `/ai-native-plugin:devflow-start-task <task-id>`（`argument-hint` 声明参数）；步骤 4 建 sandbox 用 `git worktree add .ai-devflow/sandboxes/<task-id> -b task/<task-id>/<ts>`（spec 6 步骤 4）；步骤 1 探测 `command -v glab && command -v lark-cli`（spec 4.2）。
- Consumes: `agents/frontend.md`/`backend.md`（Task 2）；`${CLAUDE_PLUGIN_ROOT}/scripts/*`（Task 4-8，先写引用后建脚本）。

- [ ] **Step 1: 写失败测试 `scripts/test/test_skill.sh`**

```bash
#!/bin/bash
# devflow-start-task Skill 结构校验：9 步齐全 + Defer 分支 + 模板存在 + 无容器硬编码。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/devflow-start-task/SKILL.md"
[ -f "$SKILL" ] || { echo "SKILL.md missing"; exit 1; }

# 调用名 frontmatter
grep -q 'argument-hint' "$SKILL" || { echo "argument-hint missing"; exit 1; }

# 9 步关键内容（按 spec 第 6 节）
grep -q 'intent.md' "$SKILL" || { echo "step1 intent missing"; exit 1; }
grep -q 'Decision: Accept/Reject/Defer' "$SKILL" || { echo "step1 Decision missing"; exit 1; }
grep -q 'worktree add' "$SKILL" || { echo "step4 worktree missing"; exit 1; }
grep -q 'full-verify' "$SKILL" || { echo "step6 verify missing"; exit 1; }
grep -q 'attribute.py' "$SKILL" || { echo "step7 attribute missing"; exit 1; }
grep -q 'repair-counter.py' "$SKILL" || { echo "step7 repair-counter missing"; exit 1; }
grep -q 'ai-review.sh' "$SKILL" || { echo "step8 ai-review missing"; exit 1; }
grep -q 'create-mr.sh' "$SKILL" || { echo "step8 create-mr missing"; exit 1; }
grep -q 'finish-task.sh' "$SKILL" || { echo "step9 finish-task missing"; exit 1; }
grep -q 'HUMAN_APPROVED' "$SKILL" || { echo "step9 approval missing"; exit 1; }
# 前置依赖探测
grep -q 'command -v glab' "$SKILL" || { echo "glab probe missing"; exit 1; }
grep -q 'command -v lark-cli' "$SKILL" || { echo "lark-cli probe missing"; exit 1; }
# 所有脚本路径走 CLAUDE_PLUGIN_ROOT，无 /app 硬编码
grep -q 'CLAUDE_PLUGIN_ROOT' "$SKILL" || { echo "CLAUDE_PLUGIN_ROOT missing"; exit 1; }
grep -q '/opt/harness\|/app/' "$SKILL" && { echo "container path leak"; exit 1; }

# 模板存在且结构正确
for t in INTENT-TEMPLATE SPEC-TEMPLATE CLAUDE-SUPPLEMENT; do
  [ -f "$ROOT/skills/devflow-start-task/templates/$t.md" ] || { echo "templates/$t.md missing"; exit 1; }
done
grep -q '^## 问题' "$ROOT/skills/devflow-start-task/templates/INTENT-TEMPLATE.md" || { echo "INTENT template section missing"; exit 1; }
grep -q '^## 0\. 不可违反原则' "$ROOT/skills/devflow-start-task/templates/SPEC-TEMPLATE.md" || { echo "SPEC template section0 missing"; exit 1; }
grep -q '^### Decision' "$ROOT/skills/devflow-start-task/templates/SPEC-TEMPLATE.md" || { echo "SPEC template Decision missing"; exit 1; }
grep -q '^## 验证工作' "$ROOT/skills/devflow-start-task/templates/CLAUDE-SUPPLEMENT.md" || { echo "supplement section missing"; exit 1; }

echo "test_skill: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/test/test_skill.sh`
Expected: `SKILL.md missing`。

- [ ] **Step 3: 创建 `skills/devflow-start-task/templates/INTENT-TEMPLATE.md`**

从 `ai-native` 已验证的 intent 模板移植，补 spec 7.7 要求的 `Decision` 段：

```markdown
# 意图：<task-id> <一句话标题>

作者：<飞书任务发起人>。状态：draft | accepted | superseded。

## 问题
<客户/业务侧遇到的实际问题，用发起人自己的语言，不要工程化改写>

## 预期成果
<期望达成的效果，人类可读的验收描述>

## 受影响的用户和系统
<哪些角色、哪些 repo/模块会受影响>

## 约束
<不能做什么、边界在哪里>

## 待确认问题
<需求信息不全时列出，不要猜>

## Decision
Accept / Reject / Defer + 理由
<Skill 步骤 1 填写：Accept 才进入 SPEC 流程；Defer 止步于此，只飞书知会，不建 sandbox/MR>
```

- [ ] **Step 4: 创建 `skills/devflow-start-task/templates/SPEC-TEMPLATE.md`**

从 `ai-native/devflow/SPEC-TEMPLATE.md` + 已验证的 SPEC 增强（Task 4 的 Decision 留痕）合并，路径改为仓库相对：

```markdown
# SPEC: <task-id> <一句话标题>

## 0. 不可违反原则
<列出这个任务不能碰的边界；引用当前仓库 CLAUDE.md 的核心规则，不重复抄写>

### Decision（Skill 维护）
status: accepted   # accepted | deferred | rejected
actor: <决策人>
timestamp: <YYYY-MM-DDTHH:MM:SSZ>

## 1. Requirement（需求理解）
- 背景 / 目的（从 intent.md 提炼，不脱离 intent 重新理解需求；首行引用 intent.md 路径）
- 影响范围（涉及哪些 repo / 模块）
- 安全与边界（不做什么）
- 假设清单（需求信息不全时列出）

## 2. Acceptance Criteria（验收标准）
- AC-01: <可验证的单条标准>
- AC-02: ...
（每条 AC 需能映射到 verification.json 里的某个 test case）

## 3. Task Breakdown（任务拆分）
- Task-1 [owner: frontend] 描述 / 依赖: 无
- Task-2 [owner: backend] 描述 / 依赖: 无
（标注串并行关系，供编排读取）

## 4. Status（Skill 维护，运行时更新）
- 当前阶段 / 各 Task 状态 / 最近一次 verification 结果链接 / 最近一次埋点 event_id
```

- [ ] **Step 5: 创建 `skills/devflow-start-task/templates/CLAUDE-SUPPLEMENT.md`**

从 `ai-native/CLAUDE.docker.md` 详细化后的内容去 ads 化（spec 7.6，不焊死、可拒绝追加）：

```markdown
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
```

- [ ] **Step 6: 创建 `skills/devflow-start-task/SKILL.md`**

```markdown
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
```

- [ ] **Step 7: 跑测试确认全绿**

Run: `bash scripts/test/test_skill.sh`
Expected: `test_skill: ALL OK`。

- [ ] **Step 8: 提交（需用户确认）**

```bash
git add skills scripts/test/test_skill.sh
git commit -m "feat(skill): devflow-start-task 9 步编排 + intent/spec/supplement 模板"
```

---

## Phase D — scripts 移植

> 移植通则：所有 `/opt/harness` 引用改 `${CLAUDE_PLUGIN_ROOT}`；所有 `/app/.ai-devflow` 运行时产物路径改仓库相对 `.ai-devflow/`（Python 脚本用 `os.path.join(os.getcwd(), ".ai-devflow")`，bash 脚本用 `${PWD:-$(pwd)}`）。环境变量默认值逐个改（保留可覆盖）。

### Task 4: `ensure-python-deps.sh` + `verify_runner.py`（四态化）

**Files:**
- Create: `scripts/ensure-python-deps.sh`
- Create: `scripts/verify_runner.py`（移植 `ai-native/test-harness/lib/verify_runner.py`）
- Create: `scripts/fast-verify.sh`（移植 `ai-native/test-harness/bin/fast-verify.sh`）
- Create: `scripts/full-verify.sh`（移植 `ai-native/test-harness/bin/full-verify.sh`）
- Create: `scripts/test/test_full_verify.sh`（移植 + 加超时用例）

**Interfaces:**
- Produces: `ensure-python-deps.sh` → stdout 输出 venv python 路径；`full-verify.sh <repo_dir>` → 写 `<repo_dir>/.ai-devflow/verification.json` 并 exit 0/1；`fast-verify.sh <repo_dir>` → 跑 gates.fast。
- Consumes: 目标仓库 `harness.yaml`；`${CLAUDE_PLUGIN_DATA}`（venv 位置）。

- [ ] **Step 1: 创建 `scripts/ensure-python-deps.sh`**

```bash
#!/bin/bash
# 插件专属 venv，装在 CLAUDE_PLUGIN_DATA 下（卸载插件自动清理，不污染目标仓库环境）。
# 输出 venv 的 python3 绝对路径，供其他脚本 shebang 或调用处使用。
set -u
VENV_DIR="${CLAUDE_PLUGIN_DATA:-${HOME}/.claude/plugin-data/ai-native-plugin}/venv"
PYTHON="${VENV_DIR}/bin/python3"
if [ ! -x "$PYTHON" ]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q pyyaml pytest httpx
fi
echo "$PYTHON"
```

> 说明：`CLAUDE_PLUGIN_DATA` 由插件运行时注入；本地测试无该变量时回退到 HOME 下。spec 4.2 的原文只装 pyyaml/pytest/httpx 三件，保持一致。

- [ ] **Step 2: 写失败测试 `scripts/test/test_full_verify.sh`（移植 + 新增 timeout 用例）**

从 `ai-native/scripts/test/test_full_verify.sh` 整份复制，做两处修改：
1. 顶部 `RUNNER=` 改为 `"$(cd "$(dirname "$0")/../.." && pwd)/scripts/verify_runner.py"`；`python3 -c "import yaml"` 守卫改为 `[ -x "$("$(cd "$(dirname "$0")/../.." && pwd)/scripts/ensure-python-deps.sh")" ]` 或保留原守卫（执行时按源文件逐行改）。
2. 末尾追加第 5 个 timeout 用例（来自已验证 plan Task 1 Step 1）：

```bash
# 5) timeout：VERIFY_TIMEOUT_SECONDS=1 + sleep 5 → result=ERROR, subtype=timeout
mkdir -p "$root/slow"
cat > "$root/slow/harness.yaml" <<'YAML'
project:
  name: slow
  stack:
    type: backend
    backend_unit_cmd: "sleep 5"
gates:
  full: [unit]
YAML
VERIFY_TIMEOUT_SECONDS=1 python3 "$RUNNER" "$root/slow" >/dev/null 2>&1
python3 - "$root/slow/.ai-devflow/verification.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
u = d['tests']['unit']
assert u['result'] == 'ERROR', f"expected ERROR, got {u['result']}"
assert u['subtype'] == 'timeout', f"expected timeout, got {u.get('subtype')}"
print("TIMEOUT-layer: OK")
PY
[ $? -eq 0 ] || { echo "TIMEOUT-layer: FAILED"; exit 1; }
```

- [ ] **Step 3: 跑测试确认失败**

Run: `bash scripts/test/test_full_verify.sh`
Expected: 前 4 用例 OK（或脚本不存在报错），第 5 用例 `TIMEOUT-layer: FAILED`。

- [ ] **Step 4: 创建 `scripts/verify_runner.py`（四态化）**

从 `ai-native/test-harness/lib/verify_runner.py` 逐行移植，做两处修改：
1. `run_layer()` 换成已验证的四态化实现（spec 7.3 + 已验证 plan Task 1 Step 3）：

```python
def run_layer(repo_dir, layer, cmd):
    timeout = int(os.environ.get("VERIFY_TIMEOUT_SECONDS", "600"))
    start = time.time()
    if not cmd:
        return {"result": "NOT_RUN", "reason": f"{layer}_cmd not configured", "duration_ms": 0}
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=repo_dir,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"result": "ERROR", "subtype": "timeout",
                "reason": f"exceeded {timeout}s",
                "duration_ms": int((time.time() - start) * 1000)}
    except Exception as e:
        return {"result": "ERROR", "subtype": "infra_exception",
                "reason": f"{type(e).__name__}: {e}",
                "duration_ms": int((time.time() - start) * 1000)}
    dur = int((time.time() - start) * 1000)
    return {
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "subtype": "success" if proc.returncode == 0 else "assertion_failed",
        "returncode": proc.returncode,
        "duration_ms": dur,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
```

2. `main()` 里 failures 组装：`if info["result"] in ("FAIL", "ERROR"):`，且 failure 对象带 `"subtype": info.get("subtype")`（其余字段照抄源文件）。
3. 其余（`read_harness`/`layer_command`/`guess_owner`/`git_commit`）逐行照抄，`guess_owner` 的注释保留（contract 按本 repo stack.type 归因是本插件的关键语义）。

- [ ] **Step 5: 创建 `scripts/fast-verify.sh` 与 `scripts/full-verify.sh`**

从 `ai-native/test-harness/bin/` 对应文件逐行移植，修改：
- `full-verify.sh` 的 `exec python3 /opt/harness/lib/verify_runner.py` 改为：

```bash
#!/bin/bash
# full-verify.sh <repo_dir>：跑 harness.yaml 的 gates.full 各层，写 .ai-devflow/verification.json。
# PASS=退出0，FAIL=退出1。
set -u
repo_dir="${1:?usage: full-verify.sh <repo_dir>}"
PYTHON="$(cd "$(dirname "$0")" && pwd)/ensure-python-deps.sh"
exec "$("$PYTHON")" "$(cd "$(dirname "$0")" && pwd)/verify_runner.py" "$repo_dir"
```

- `fast-verify.sh` 源文件里 3 处 `python3 -c "import yaml"` 改成 `"$("$(cd "$(dirname "$0")" && pwd)/ensure-python-deps.sh")" -c ...`（执行时把源文件的 python3 全部替换为 `PYTHON` 变量，并在脚本顶部取一次 PYTHON）。

- [ ] **Step 6: 跑测试确认全绿**

Run: `bash scripts/test/test_full_verify.sh`
Expected: 5 个用例全 OK（`test_full_verify: ALL OK`）。

- [ ] **Step 7: 提交（需用户确认）**

```bash
git add scripts/ensure-python-deps.sh scripts/verify_runner.py scripts/fast-verify.sh scripts/full-verify.sh scripts/test/test_full_verify.sh
git commit -m "feat(scripts): venv 自装依赖 + verification 四态化（ERROR/subtype）"
```

---

### Task 5: `attribute.py`（subtype 直判）+ `repair-counter.py`

**Files:**
- Create: `scripts/attribute.py`（移植 + subtype 直判）
- Create: `scripts/repair-counter.py`（移植 + 仓库相对路径）
- Create: `scripts/test/test_attribute.py`（移植 + 加 subtype 用例）
- Create: `scripts/test/test_repair_counter.py`（移植）

**Interfaces:**
- `attribute.py <verification.json>` → 输出归因 JSON，exit 0/1（有失败归因则 1）。
- `repair-counter.py <task_id> <repo> <PASS|FAIL>` → 更新 `${REPAIR_STATE_BASE:-<repo>/.ai-devflow}/<task_id>/repair-state.json`，输出 `{consecutive_failures, escalate}`。

- [ ] **Step 1: 复制测试 `test_attribute.py` / `test_repair_counter.py`**

从 `ai-native/scripts/test/test_attribute.py`、`test_repair_counter.py` 原样复制到 `scripts/test/`，**追加**一条 subtype→infra 用例（已验证 plan Task 1 Step 5）：

```python
def test_subtype_error_maps_to_infra_even_with_owner_hint(tmp_path):
    r = run(tmp_path, [{"owner_hint": "frontend", "criteria": "unit gate failed", "subtype": "timeout"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "infra"
```

`test_repair_counter.py` 的 `run()` 里 `env["REPAIR_STATE_BASE"]` 保持不变（测试显式注入路径）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest scripts/test/test_attribute.py -v`
Expected: 新增 `test_subtype_error_maps_to_infra_even_with_owner_hint` FAIL（当前 `owner_of` 优先 owner_hint 返回 frontend）；其余用例 PASS（因为脚本还没建，首次会是 FileNotFoundError，创建脚本后重跑本步确认该用例先红）。

- [ ] **Step 3: 创建 `scripts/attribute.py`**

从 `ai-native/scripts/attribute.py` 逐行移植，`owner_of` 最前面插入 subtype 直判（已验证实现）：

```python
def owner_of(failure):
    # 环境/基础设施类失败（超时、子进程异常）优先于 owner_hint 直接归 infra，
    # 不再依赖 INFRA_KEYWORDS 关键词猜测——verify_runner 已用 subtype 显式标注。
    if failure.get("subtype") in ("timeout", "infra_exception"):
        return "infra"
    hint = failure.get("owner_hint", "")
    # ... 其余照抄源文件
```

- [ ] **Step 4: 创建 `scripts/repair-counter.py`**

从 `ai-native/scripts/repair-counter.py` 移植，仅改默认路径：

```python
# STATE_BASE 默认从 /app/.ai-devflow 改为当前工作目录下的 .ai-devflow
STATE_BASE = os.environ.get("REPAIR_STATE_BASE", os.path.join(os.getcwd(), ".ai-devflow"))
```

其余（计数逻辑/输出 JSON/ESCALATE_THRESHOLD=3）逐行照抄。

- [ ] **Step 5: 跑测试确认全绿**

Run: `python3 -m pytest scripts/test/test_attribute.py scripts/test/test_repair_counter.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交（需用户确认）**

```bash
git add scripts/attribute.py scripts/repair-counter.py scripts/test/test_attribute.py scripts/test/test_repair_counter.py
git commit -m "feat(scripts): 归因 subtype 直判 infra + repair-counter 仓库相对路径"
```

---

### Task 6: `policies/REVIEW.md` + `ai-review.sh`（动态清单 + review.json）

**Files:**
- Create: `policies/REVIEW.md`
- Create: `scripts/ai-review.sh`（移植 + REVIEW_POLICY 动态 + review.json）
- Create: `scripts/test/test_ai_review.sh`（移植 + 追加 REVIEW_POLICY 断言）

**Interfaces:**
- `ai-review.sh <sandbox_path> <task_id>` → 写 `<repo>/.ai-devflow/<task_id>/review.md`（清单来自 policies/REVIEW.md）+ `review.json`（`{verdict:"PENDING", critical[], important[], nits[], spec_compliance}`）。
- 环境变量 `REVIEW_POLICY`（默认 `${CLAUDE_PLUGIN_ROOT}/policies/REVIEW.md`）、`REVIEW_DIR`（默认 `<repo>/.ai-devflow/<task_id>`）。

- [ ] **Step 1: 创建 `policies/REVIEW.md`**

```markdown
# Review Policy

AI Review 分级标准。`ai-review.sh` 读取本文件的 `- [ ]` 清单拼进 review.md。

## Critical
- [ ] 改动范围超出 SPEC Task 声明的文件
- [ ] AC 未被任何测试覆盖

## Important
- [ ] business_code 改了但 test_code 没同步改
- [ ] verification.json 存在 NOT_RUN 但被当 PASS 处理

## Nit
- [ ] 命名 / 可读性

Maximum Nit Comments: 5

## 不需要报告
生成文件；CI 已强制的内容（lint/format）。
```

- [ ] **Step 2: 复制 `test_ai_review.sh` 并追加断言**

从 `ai-native/scripts/test/test_ai_review.sh` 复制，`AI_REVIEW=` 改为 `"$(cd "$(dirname "$0")/../.." && pwd)/scripts/ai-review.sh"`，末尾追加（已验证 plan Task 2 Step 2）：

```bash
# REVIEW.md 动态清单 + review.json 产出
cat > "$root/policy.md" <<'MD'
# Review Policy
## Critical
- [ ] AC 必须有测试覆盖
MD
mkdir -p "$root/.ai-devflow/demo2" "$root/repo2/.ai-devflow"
cat > "$root/.ai-devflow/demo2/SPEC.md" <<'MD'
## 2. Acceptance Criteria
- AC-01: 有改动
MD
echo '{"result":"PASS"}' > "$root/repo2/.ai-devflow/verification.json"
if ! SPEC_FILE="$root/.ai-devflow/demo2/SPEC.md" REVIEW_DIR="$root/.ai-devflow/demo2" \
     REVIEW_POLICY="$root/policy.md" \
     bash "$AI_REVIEW" "$root/repo2" "demo2" >/dev/null 2>&1; then
  echo "REVIEW-policy run: FAILED"; exit 1
fi
grep -q "AC 必须有测试覆盖" "$root/.ai-devflow/demo2/review.md" \
  && echo "policy checklist in review: OK" || { echo "policy checklist missing"; exit 1; }
[ -f "$root/.ai-devflow/demo2/review.json" ] \
  && grep -q '"verdict": "PENDING"' "$root/.ai-devflow/demo2/review.json" \
  && echo "review.json: OK" || { echo "review.json missing or no PENDING verdict"; exit 1; }
```

- [ ] **Step 3: 跑测试确认失败**

Run: `bash scripts/test/test_ai_review.sh`
Expected: 新增 `REVIEW-policy run: FAILED`。

- [ ] **Step 4: 创建 `scripts/ai-review.sh`（动态清单 + review.json）**

从 `ai-native/scripts/ai-review.sh` 移植，改 4 处：

1. 默认路径（`:11-12`）：
```bash
spec="${SPEC_FILE:-$PWD/.ai-devflow/$task_id/SPEC.md}"
review_dir="${REVIEW_DIR:-$PWD/.ai-devflow/$task_id}"
```
2. 动态 checklist（`spec`/`review_dir` 定义后插入）：
```bash
review_policy="${REVIEW_POLICY:-$(cd "$(dirname "$0")" && pwd)/../policies/REVIEW.md}"
checklist_md=""
if [ -f "$review_policy" ]; then
  checklist_md=$(grep -E '^- \[ \]' "$review_policy" || true)
fi
if [ -z "$checklist_md" ]; then
  checklist_md=$(cat <<'DEFAULT'
- [ ] 改动范围与 SPEC Task 一致，无越界文件
- [ ] 每条 AC 有对应改动或测试
- [ ] 无明显坏味道 / 未处理错误分支
- [ ] verification 结果是真实执行（非全 NOT_RUN 堆叠）
DEFAULT
)
fi
```
3. review.md heredoc 的「## 检查清单」段改为引用 `$checklist_md`（用 `printf '%s\n' "$checklist_md"` 展开）。
4. heredoc 后追加 review.json：
```bash
cat > "$review_dir/review.json" <<JSON
{
  "verdict": "PENDING",
  "critical": [],
  "important": [],
  "nits": [],
  "spec_compliance": null
}
JSON
echo "review pack written: $review_dir/review.md + review.json"
```

其余（diff stat/文件清单/AC 提取/verification 摘要）照抄。

- [ ] **Step 5: 跑测试确认全绿**

Run: `bash scripts/test/test_ai_review.sh`
Expected: `test_ai_review: ALL OK`（含新增断言）。

- [ ] **Step 6: 提交（需用户确认）**

```bash
git add policies/REVIEW.md scripts/ai-review.sh scripts/test/test_ai_review.sh
git commit -m "feat(review): Review 清单可配置化 + 机读 review.json"
```

---

### Task 7: `contract_checker.py` + `check-bands.py`

**Files:**
- Create: `scripts/contract_checker.py`（原样移植，路径已仓库相对）
- Create: `scripts/check-bands.py`（移植已验证实现，读 events 表算 z-score）
- Create: `scripts/test/test_contract_checker.py`（原样复制）
- Create: `scripts/test/test_check_bands.py`（原样复制已验证测试）

**Interfaces:**
- `contract_checker.py <contract_file> [repo_dir]`：结构校验 + 用法交叉核对（本仓库 business_code 是否引用契约端点），exit 0/1。spec 3.2 契约漂移兜底依赖此脚本。
- `check-bands.py <db_path> [bands_yaml]`：输出 `{metric,today,today_value,baseline_mean,baseline_stdev,z_score,tier,action}`；3σ 落 `${BANDS_ALERT_DIR:-$PWD/.ai-devflow/bands-alerts}/<today>.md`，只读不写事件（spec 7.10）。

- [ ] **Step 1: 复制测试**

从 `ai-native/scripts/test/test_contract_checker.py` 原样复制到 `scripts/test/`；从 `ai-native/docs/superpowers/plans/2026-08-28-anthropic-playbook-adoption.md` Task 5 的 `test_check_bands.py`（已验证实现）原样复制到 `scripts/test/test_check_bands.py`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest scripts/test/test_contract_checker.py scripts/test/test_check_bands.py -v`
Expected: `FileNotFoundError`（脚本还没建）。

- [ ] **Step 3: 创建 `scripts/contract_checker.py`**

从 `ai-native/scripts/contract_checker.py` **原样逐行复制**（该脚本已用仓库相对路径 `harness.yaml`/`contract.json`，无 `/app` 硬编码，不需要改路径）。保留模块 docstring 里的契约漂移语义说明。

- [ ] **Step 4: 创建 `scripts/check-bands.py`**

从已验证实现（`ai-native/docs/superpowers/plans/2026-08-28-anthropic-playbook-adoption.md` Task 5 Step 4）复制完整 `check-bands.py`，仅改默认路径一处：

```python
notify_dir = os.environ.get("BANDS_ALERT_DIR", os.path.join(os.getcwd(), ".ai-devflow", "bands-alerts"))
```

（其余逻辑照抄：METRIC_QUERIES/rolling baseline/pstdev/z-score/tier 判定/3σ 通知文件。）

- [ ] **Step 5: 跑测试确认全绿**

Run: `python3 -m pytest scripts/test/test_contract_checker.py scripts/test/test_check_bands.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交（需用户确认）**

```bash
git add scripts/contract_checker.py scripts/check-bands.py scripts/test/test_contract_checker.py scripts/test/test_check_bands.py
git commit -m "feat(scripts): contract_checker + check-bands（契约漂移兜底 + bands 监控闭环）"
```

---

### Task 8: MR/收尾脚本（glab）+ 埋点 4 件套

**Files:**
- Create: `scripts/create-mr.sh`（移植，glab）
- Create: `scripts/finish-task.sh`（移植，glab，去掉评审回路）
- Create: `scripts/emit-event.py`（移植 + parent_event_id）
- Create: `scripts/load-events.py`、`scripts/analytics.py`、`scripts/session-usage.py`（原样移植）
- Create: `docs/telemetry-schema.json`（同步 enum）
- Create: `scripts/test/test_create_mr.sh`、`scripts/test/test_telemetry.py`、`scripts/test/test_session_usage.py`（原样复制/适配）

**Interfaces:**
- `create-mr.sh <sandbox_path> <task_id> [--dry-run]`：push 分支 + `glab mr create`，stdout 输出 `MR_URL=`（spec 4.3）。
- `finish-task.sh <task_id> <repo> <sandbox_path> <mr_url>`：`glab mr merge --yes --remove-source-branch` + worktree 清理 + 埋点（mr_merged/state_change:done/cost）。**不调用 `glab mr note list`**（spec 第 2 节去掉评审回路）。
- `emit-event.py <event_type> --task-id X [--repo Y] [--data '{}'] [--parent-event-id Z]`：写 `${EVENTS_BASE:-$PWD/.ai-devflow/events}/<day>.jsonl`，stdout 打印 event_id。
- `analytics.py <db_path> [query]`：增加 `chain` 查询（按 parent_event_id 递归重建链路，spec 7.11 验收）。

- [ ] **Step 1: 复制测试并适配路径**

从 `ai-native/scripts/test/` 复制 `test_create_mr.sh`、`test_telemetry.py`、`test_session_usage.py` 到 `scripts/test/`：
- `test_create_mr.sh`：`CREATE_MR=` 改为 `"$(cd "$(dirname "$0")/../.." && pwd)/scripts/create-mr.sh"`，其余照抄（dry-run 不真 push/mr）。
- `test_telemetry.py`：照抄；其中 `test_schema_enum_matches_emit` 读 `docs/telemetry-schema.json`，插件需自带该文件（本 Task Step 4）。
- `test_session_usage.py`：`SCRIPT=` 已相对，照抄。

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/test/test_create_mr.sh && python3 -m pytest scripts/test/test_telemetry.py scripts/test/test_session_usage.py -v`
Expected: 脚本缺失报错。

- [ ] **Step 3: 创建 `scripts/create-mr.sh`**

从 `ai-native/scripts/create-mr.sh` 逐行移植，改 3 处默认路径（`spec`/`review`/`ver_file` 的 `/app/.ai-devflow` → `${PWD}/.ai-devflow`）。**glab 约束已满足**：源文件内部就是 `git push` + `glab mr create --source-branch --target-branch --title --description -y`，无 REST API 调用，保持原样。

- [ ] **Step 4: 创建 `scripts/finish-task.sh`**

从 `ai-native/scripts/finish-task.sh` 移植，改 3 处：
1. `HARNESS_SCRIPTS` 默认值 `/opt/harness/scripts` → `${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}`（脚本自己所在目录）。
2. `emit-event.py`/`session-usage.py` 调用改 `${HARNESS_SCRIPTS}/...`。
3. **去掉源文件里任何 `glab mr note list` 逻辑**（源文件当前没有，但确认不新增）；`glab mr merge "$mr_url" --yes --remove-source-branch` 保留（已满足 glab 约束）。

保留：merge → worktree 清理（`git worktree remove --force`）→ 埋点 mr_merged/state_change:done/cost。`emit-event.py` 各调用加 `--repo "$repo"`（源文件已有）。

- [ ] **Step 5: 创建 `scripts/emit-event.py`（+ parent_event_id）**

从 `ai-native/scripts/emit-event.py` 移植，改 2 处（spec 7.11）：
1. 默认路径 `EVENTS_BASE` 改为 `os.path.join(os.getcwd(), ".ai-devflow", "events")`。
2. 加 `--parent-event-id` 参数 + event 里加 `parent_event_id` 字段 + stdout 打印 `event_id`：

```python
p.add_argument("--parent-event-id", default="")
# ...
event = {
    "type": args.event_type,
    "event_id": str(uuid.uuid4()),
    "parent_event_id": args.parent_event_id or None,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "task_id": args.task_id,
    "repo": args.repo,
    **data,
}
# ... 写入后：
print(json.dumps({"event_id": event["event_id"], "parent_event_id": event["parent_event_id"]}))
```

顶部加 `import uuid`；`EVENT_TYPES` 不变（不新增事件类型，spec 7.11 说"如果新增"才要同步 enum——本计划不新增）。

- [ ] **Step 6: 创建 `scripts/load-events.py` 与 `scripts/analytics.py`**

- `load-events.py`：从源文件逐行移植，无需改路径（参数传入）。**注意**：`parent_event_id` 已作为 payload 字段进入 events 表 payload JSON。
- `analytics.py`：从源文件移植，`QUERIES` 增加 `chain` 查询（spec 7.11 验收：能重建 task→verification→review→merge 链路）：

```python
QUERIES = {
    # ...源文件原查询照抄...
    "chain": (
        "WITH RECURSIVE chain(event_id, parent_event_id, type, depth) AS ("
        "  SELECT json_extract(payload, '$.event_id'), json_extract(payload, '$.parent_event_id'), type, 0 "
        "  FROM events "
        "  UNION ALL "
        "  SELECT json_extract(e.payload, '$.event_id'), json_extract(e.payload, '$.parent_event_id'), e.type, c.depth + 1 "
        "  FROM events e JOIN chain c ON json_extract(e.payload, '$.parent_event_id') = c.event_id "
        ") SELECT * FROM chain ORDER BY depth"),
}
```

- [ ] **Step 7: 创建 `docs/telemetry-schema.json`**

从 `ai-native/docs/telemetry-schema.json` 复制，`type.enum` 保持与 `emit-event.py` 的 `EVENT_TYPES` 一致（不新增），`properties` 增加 `parent_event_id` 字段说明：

```json
"parent_event_id": { "type": ["string", "null"] }
```

- [ ] **Step 8: 创建 `scripts/session-usage.py`**

从 `ai-native/scripts/session-usage.py` 逐行移植，仅改默认路径：

```python
STATE_BASE = os.environ.get("STATE_BASE", os.path.join(os.getcwd(), ".ai-devflow"))
```

（其余照抄：读 `~/.claude/projects/*/*.jsonl` 统计 token delta，写 session-transcript.jsonl，输出 cost JSON。）

- [ ] **Step 9: 跑测试确认全绿**

Run: `bash scripts/test/test_create_mr.sh && python3 -m pytest scripts/test/test_telemetry.py scripts/test/test_session_usage.py -v`
Expected: 全部 PASS。

- [ ] **Step 10: 提交（需用户确认）**

```bash
git add scripts/create-mr.sh scripts/finish-task.sh scripts/emit-event.py scripts/load-events.py scripts/analytics.py scripts/session-usage.py docs/telemetry-schema.json scripts/test/test_create_mr.sh scripts/test/test_telemetry.py scripts/test/test_session_usage.py
git commit -m "feat(scripts): MR/收尾走 glab + 埋点 parent_event_id 链路"
```

---

## Phase E — hooks + policies 收尾

### Task 9: `protect-paths.sh` + `approval-gate.sh` + `hooks/hooks.json`

**Files:**
- Create: `scripts/hooks/protect-paths.sh`
- Create: `scripts/hooks/approval-gate.sh`
- Create: `scripts/hooks/deny-secrets.sh`（落文件，**不接进 hooks.json**，spec 7.1 暂缓）
- Create: `scripts/test/test_protect_paths_hook.sh`、`scripts/test/test_approval_gate_hook.sh`
- Modify: `hooks/hooks.json`（把 Task 9 的 hook 接入；当前是空 PostToolUse，改为真实挂载）

**Interfaces:**
- Hook 输入：stdin JSON（PreToolUse: `{"tool_input":{...}}`）。
- Hook 输出：`exit 2` + stderr = 阻止；`exit 0` = 放行。
- `run-hook.cmd <hook-name>`（Task 1）→ 执行 `scripts/hooks/<hook-name>`（无扩展名）。hooks.json 的 command 是 `"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" <name>`。

- [ ] **Step 1: 复制测试 `test_protect_paths_hook.sh` / `test_approval_gate_hook.sh`**

从 `ai-native/docs/superpowers/plans/2026-08-28-anthropic-playbook-adoption.md` Task 3/4 复制已验证测试到 `scripts/test/`，改 `HOOK=` 路径指向 `scripts/hooks/`：
- `test_protect_paths_hook.sh`：`HOOK="$(cd "$(dirname "$0")/../.." && pwd)/scripts/hooks/protect-paths.sh"`。
- `test_approval_gate_hook.sh`：`HOOK="$(cd "$(dirname "$0")/../.." && pwd)/scripts/hooks/approval-gate.sh"`；`export APPROVAL_BASE="$root"` 保留。

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/test/test_protect_paths_hook.sh; bash scripts/test/test_approval_gate_hook.sh`
Expected: `protect-paths.sh missing` / `approval-gate.sh missing`。

- [ ] **Step 3: 创建 `scripts/hooks/protect-paths.sh`**

从已验证实现复制（`ai-native/docs/superpowers/plans/2026-08-28-anthropic-playbook-adoption.md` Task 3 Step 3），**无修改**：

```bash
#!/bin/bash
# PreToolUse hook（matcher: Edit|Write）：阻止 Agent 编辑受保护路径。
# .ai-devflow/ 是脚本产物目录，harness.yaml 是裁判配置——两者都不该被开发 Agent 手动改。
set -u
file_path=$(jq -r '.tool_input.file_path // .tool_input.path // ""')
case "$file_path" in
  */.ai-devflow/*|*harness.yaml)
    echo "受保护路径禁止直接编辑：$file_path" >&2
    exit 2
    ;;
esac
exit 0
```

- [ ] **Step 4: 创建 `scripts/hooks/approval-gate.sh`**

从已验证实现复制（Task 4 Step 3），`APPROVAL_BASE` 默认 `/app/.ai-devflow` → 当前工作目录下 `.ai-devflow`：

```bash
#!/bin/bash
# PreToolUse hook（matcher: Bash）：finish-task.sh 是合并进 main 的唯一入口。
# 没有人工确认标记文件，禁止执行。标记由人工飞书确认后 touch 创建（SKILL 步骤 9）。
set -u
cmd=$(jq -r '.tool_input.command // ""')
case "$cmd" in
  *finish-task.sh*)
    task_id=$(echo "$cmd" | grep -oE 'finish-task\.sh[[:space:]]+[^[:space:]]+' | awk '{print $2}')
    approval_base="${APPROVAL_BASE:-$PWD/.ai-devflow}"
    if [ -z "$task_id" ] || [ ! -f "$approval_base/$task_id/HUMAN_APPROVED" ]; then
      echo "禁止合并：未找到人工确认标记 $approval_base/$task_id/HUMAN_APPROVED" >&2
      exit 2
    fi
    ;;
esac
exit 0
```

> 注：hook 以仓库根目录为 cwd 运行时 `$PWD` 即仓库根目录；若 cwd 不在仓库根，用 `git rev-parse --show-toplevel` 兜底（执行时按测试环境确认）。

- [ ] **Step 5: 创建 `scripts/hooks/deny-secrets.sh`（暂缓，仅落文件）**

spec 7.1 技术方案存档（不接 hooks.json）：

```bash
#!/bin/bash
# PreToolUse hook（matcher: Read）——主动暂缓，未接入 hooks.json（spec 第 2 节/第 9 节）。
# 逻辑留档：命中 .env/.env.*/**/secrets/**/**/*.pem/**/.git/** 则 exit 2 拦截。
set -u
file_path=$(jq -r '.tool_input.file_path // ""')
case "$file_path" in
  *.env|*.env.*|*/secrets/*|*.pem|*/.git/*)
    echo "受保护敏感路径禁止读取：$file_path" >&2
    exit 2
    ;;
esac
exit 0
```

- [ ] **Step 6: 跑 hook 测试确认全绿**

Run: `bash scripts/test/test_protect_paths_hook.sh; bash scripts/test/test_approval_gate_hook.sh`
Expected: 两者均 `ALL OK`（无 jq 会 SKIP，需本机装 jq 验证；Windows 下可用 `winget install jqlang.jq`）。

- [ ] **Step 7: 更新 `hooks/hooks.json`（接入真实 hook）**

将 Task 1 的空 PostToolUse 替换为完整配置：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" protect-paths",
            "shell": "bash",
            "timeout": 10
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" approval-gate",
            "shell": "bash",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

> `run-hook.cmd` 需要能把 `protect-paths` 映射到 `scripts/hooks/protect-paths`（无扩展名）或直接执行 `scripts/hooks/protect-paths.sh`。执行时按 Task 1 的 dispatcher 实现确认映射（Task 1 的 `run-hook.cmd` 用 `HOOK_DIR` 指向自身目录，若 hooks 脚本放 `scripts/hooks/`，则 Task 1 的 dispatcher 需改为 `HOOK_DIR` 指向 `scripts/hooks/`，`HOOK_NAME` 传无扩展名文件名——**执行时统一：hooks 脚本放 `scripts/hooks/`，`run-hook.cmd` 的 `HOOK_DIR` 指向 `${CLAUDE_PLUGIN_ROOT}/scripts/hooks`，两个 hook 脚本同时提供 `.sh` 版本供单测直调、无扩展名版本供 dispatcher 调用，或用软链**。简化：直接让 `run-hook.cmd` 接受 `protect-paths` 并执行 `"$HOOK_DIR/protect-paths.sh"`，测试直调 `.sh`，hooks.json 传无扩展名。）

- [ ] **Step 8: 提交（需用户确认）**

```bash
git add scripts/hooks hooks/hooks.json scripts/test/test_protect_paths_hook.sh scripts/test/test_approval_gate_hook.sh
git commit -m "feat(hooks): protect-paths + approval-gate 护栏接入 hooks.json（deny-secrets 留档暂缓）"
```

---

## Self-Review

**1. Spec coverage（spec 第 4-7 节 → Task 映射）**

| spec 条目 | Task | 说明 |
|---|---|---|
| 4.1 marketplace.json + 验收 | Task 1 | `claude plugin validate` 验收留到集成阶段 |
| 4.2 外部依赖声明 / ensure-python-deps.sh | Task 4 | venv 到 CLAUDE_PLUGIN_DATA |
| 4.3 GitLab 只走 glab | Task 8 | create-mr/finish-task 均为 glab，无 REST API |
| 4 结构去 commands/、调用名订正 | Task 3 | `/ai-native-plugin:devflow-start-task` |
| 5 Agent 设计（两条规则） | Task 2 | business_code/test_code 同步 + commit 前 full-verify 自查 |
| 6 编排 9 步 + Defer 分支 | Task 3 | intent.md Decision 分支、worktree 直接建、去评审回路 |
| 7.1 secrets deny | Task 9 | deny-secrets.sh 落文件，未接 hooks.json（暂缓） |
| 7.2 REVIEW.md + review.json | Task 6 | 动态清单 + PENDING verdict |
| 7.3 verification 四态化 | Task 4 | ERROR + subtype，timeout 用例 |
| 7.4 独立复核并入自查 | Task 2 | 规则 2 |
| 7.5 protect-paths | Task 9 | Edit\|Write 拦截 |
| 7.6 CLAUDE-SUPPLEMENT | Task 3 | 模板 + Skill 首次运行询问 |
| 7.7 intent.md 决策留痕 | Task 3 | INTENT-TEMPLATE + Decision 段 |
| 7.8 approval-gate | Task 9 | HUMAN_APPROVED 标记文件 |
| 7.9 SPEC 决策留痕 | Task 3 | SPEC-TEMPLATE 第 0 章 + Decision |
| 7.10 bands.yaml 监控闭环 | Task 7 | check-bands.py，3σ 通知文件 |
| 7.11 Event parent_event_id | Task 8 | emit-event + analytics chain 查询 |
| 7.12 Gate 分级 / plan.md | — | 业务决策未定，spec 明确"技术方案就位，等启用"，**不在本计划** |
| 7.13 评审回灌 | Task 3/6 | 去掉自动回修回路；CLAUDE.md 回灌规则写入 Skill 步骤 8 说明 + agents 规则 |
| 7.14 evals 套件 | — | 需真实仓库任务样本，**本计划只搭插件骨架，evals 属后续**（spec 7.14 要求从真实任务挑，插件刚建无任务可挑） |

**有意排除**：7.12（业务决策未定）、7.14（需真实任务样本，属插件落地后第二阶段）、8（ai-infra 侧改造不在范围）、9（未决问题留档）。

**2. Placeholder scan**：除上述两个有意排除项外，每个 Task 的每个 Step 都有具体文件路径/代码/测试命令。`run-hook.cmd` 的 bat/bash 混合块标注"以复制 superpowers 原文件为准"——这是跨平台歧义的实际解决方案，不是占位。

**3. Type consistency**：
- 脚本路径引用：全部 `${CLAUDE_PLUGIN_ROOT}/scripts/...`，与 spec 一致。
- 运行时产物：全部仓库相对 `.ai-devflow/<task-id>/`，`HUMAN_APPROVED`/`verification.json`/`review.json`/`repair-state.json`/`events`/`bands-alerts` 命名在 Task 3/5/6/7/8/9 间一致。
- glab 命令：`glab mr create`/`glab mr merge`，无 REST API。
- 事件类型：不新增，telemetry-schema enum 与 EVENT_TYPES 保持相等（test_telemetry.py 断言）。
- 归因：`subtype` 键在 Task 4（verify_runner 产出）与 Task 5（attribute 消费）一致，`timeout`/`infra_exception` 两处值相同。

**4. 遗留风险（执行时注意）**：
- `run-hook.cmd` 的 HOOK_DIR 映射（Task 1 与 Task 9 的衔接）需在 Task 9 Step 7 统一确认，文档已标注。
- hook 在 win32 下需要 jq；README 已把 jq 加入可选依赖说明（测试 SKIP 分支已有）。
- `fast-verify.sh`/`full-verify.sh` 的 python3 替换需逐行对照源文件，避免漏改 `python3 -c "import yaml"`。
