# AI-Native DevFlow 插件化改造设计

- **日期**：2026-09-01
- **状态**：待审阅（draft）
- **范围**：把 `ai-native` 仓库里跑在共享 Docker 容器中的 devflow 流水线，改造成可安装进任意团队自己项目的 Claude Code 插件（`ai-native-plugin`），保留完整流水线能力，只换分发/运行形态
- **依据**：`ai-native` 仓库 `Dockerfile`/`entrypoint.sh`/`devflow/**`/`docs/PLAYBOOK-ADOPTION-STATUS.md`；`ai-infra` 仓库 `src/lib/claude-code/provisioner.js`

---

## 1. 背景与转向原因

现状（`ai-native` 仓库）：devflow 跑在一个自定义 Docker 镜像里，镜像通过 `REPOS` 环境变量一次性克隆多个仓库，容器内一个"Team Lead"会话编排 Frontend/Backend/Test 三个 Task 子 agent 在 git worktree 沙箱里改代码，走验证/归因回流/AI Review/建MR/人工确认合并/埋点全流程。

转向原因有两条，互相印证：
1. **业务原因**：不想强制所有团队都接入这套"专属容器"才能用，希望能力可以被任意团队按需拿走，装个插件就能用，不用重新搭一套 devflow 容器基建。
2. **平台原因**（读 `ai-infra/src/lib/claude-code/provisioner.js` 发现的）：ai-infra 这个 agent provisioning 平台本身就是**按"一个 repo 一个容器"分配**的模型（`dataDirBase: /data/agents/claude-code`，repo 直接克隆进该容器自己的 `/root`），跟 `ai-native` 现在"一个容器扛多个仓库"的设计本来就不匹配——旧设计等于在跟平台的分配模型对抗。

**目标**：`ai-native-plugin` 作为标准 Claude Code 插件，装进任意单个仓库即可用；两个仓库（一个前端、一个后端）各自独立安装一份插件、独立运行，互不依赖同一个共享容器/会话；核心流水线能力（SPEC 工件化、验证、归因回流、AI Review、MR、人工确认合并、埋点）原样保留，只是运行主体从"容器"变成"装了插件的任意 Claude Code 会话"。

---

## 2. 关键决策记录（brainstorming 过程中已拍板，不再讨论）

| 决策点 | 结论 |
|---|---|
| 流水线取舍 | **完整保留**，只换分发形式，不阉割成纯编码工具 |
| Team Lead 角色落地 | 做成插件的 **Skill**（`/ai-native-plugin:devflow-start-task`），跑在用户当前主会话里，不做成独立 agent，也不做成纯脚本状态机 |
| test / verifier 角色 | **并入 frontend / backend 自己负责**——改代码必须同步写测试，commit 前自己跑一次 full-verify 自查，不再单列 test agent，也不新增独立 verifier agent |
| 沙箱隔离 | **保留 git worktree 隔离**——但作用域是"同一仓库内的并发任务隔离"，不再是"跨仓库统一调度" |
| 需求入口 | **仍以飞书（lark-cli）为默认**，不做多源适配层 |
| "前后端两个 agent"的含义 | **两个独立容器/会话**（各自装在自己的 repo 里独立运行），不是同一会话里 Task 派发的两个子任务——这一条改变了原设计里"Team Lead 同时指挥前后端"的假设，见第 3 节 |
| 跨仓库协作触发方式 | **用户在飞书群里 @ 谁就谁处理**，需要合作时再 @ 对方 bot，不设统一调度入口（2026-09-02 订正，见 3.2；此前"靠飞书任务关联"是编造说法，已修正为基于 cc-connect 真实机制的 bot 互 @ 模式） |
| 契约漂移处理 | **插件强制**：`contract_checker.py` 发现当前实现与已对齐的 `contract.json` 快照不一致时，自动重新 @ 对方确认，确认前不允许建 MR（见 3.2） |
| sandbox 隔离脚本 | **去掉 `make-sandbox.sh` 封装脚本**（2026-09-02）——worktree 隔离机制本身保留，只是这一步足够简单，改成编排 Skill 里直接写 `git worktree add` 命令，不单独封装成脚本文件，见 4/6 |
| GitLab 操作方式 | **确认约束**：所有 GitLab 相关操作（建MR/查状态/merge）必须走 `glab` CLI，不允许脚本内直接调 GitLab REST API（2026-09-02 确认，对现有实现方式的显式约束记录，非新增功能） |
| 评审回路 | **去掉"@claude 自动回修回路"**（2026-09-02）——MR 建开后不再自动检查 `glab mr note list` 未解决评论并分类回修，MR 评论由用户自己人工处理，见 6/7.13 |
| 本 spec 存放位置 | `ai-native-plugin` 仓库（这是新项目真实归属地，不放在 `ai-native` 里） |
| `.env`/secrets deny 机制 | **暂缓，留档**（见第 9 节），插件形态下这条不能再靠 Dockerfile 焊死，需要额外方案，本次不展开 |
| 跨仓库确认闭环（2026-09-02 定稿） | 两实例**文件系统隔离**，协作状态真值只落飞书群消息；本地 `partner.yaml`/`contract-state.json` 仅做断点缓存，不新增共享存储/同机假设，见 3.2 |
| `partner.yaml` 落点（2026-09-02 定稿） | 目标仓库 `.ai-devflow/partner.yaml`（每实例各写各的"我是谁/对面是谁/在哪个群"，不做运行时互发现），不入插件仓库与 git 远端，见 3.2.2 |
| 协作子协议形态（2026-09-02 定稿） | **叠加层而非并行流程**：只在一个任务命中跨仓库契约影响面时介入，插在 9 步步骤 1 后（阶段 0 对齐）与步骤 6/8（漂移检测、建 MR 收敛闸门）；纯本仓库任务与现状一致，见 3.2.0/3.2.4 |
| 协作埋点（2026-09-02 定稿） | **不新增事件类型**，对齐/漂移动作复用 `task_updated` + `data.phase`，遵守 7.11 的 enum 同步约束，见 7.15 |

---

## 3. 架构总览

### 3.1 核心变化：从"一个容器管多仓库"到"一仓库一实例"

```
旧：一个容器
    ├── clone ads (backend)
    ├── clone ads-web (frontend)
    └── Team Lead 会话（同时看得到两个仓库，Task 派发 frontend/backend/test 三个子agent）

新：两个独立实例（各自可能是 ai-infra 容器，也可能是本地开发机）
    实例A：装了 ai-native-plugin 的 ads 仓库      → 该实例是"backend agent"
    实例B：装了 ai-native-plugin 的 ads-web 仓库  → 该实例是"frontend agent"
    两者互不感知对方的会话，只通过飞书任务关联 + git 层的 contract.json 契约文件协作
```

**插件如何知道自己该扮演 frontend 还是 backend**：读该仓库自己的 `harness.yaml` 的 `stack.type` 字段（`frontend`/`backend`，这个字段已经存在，`ads`/`ads-web` 现有的 `harness.yaml` 就有），据此加载对应的 agent persona 和验证/归因规则。**不需要新增配置**，复用现有约定。

### 3.2 跨仓库协作怎么做（基于 cc-connect 真实机制，2026-09-02 订正）

> **订正说明**：初版这里写的"靠飞书任务关联"是没有技术依据的编造说法。核实 `entrypoint.sh:216-271` 和 `Claude_Agent_Teams_AI_DevFlow_Final_Design.md` §4.2 后确认：cc-connect 现状是**一个容器绑一个飞书 bot 身份**（`config.toml` 的 `[[projects.platforms]]` type=feishu），`group_only=true`/`thread_isolation=true`/`resolve_mentions=true`。插件化后两个仓库各自的容器/实例各接一个 cc-connect（各自独立的飞书 bot），本节描述的是"两个 bot 能在同一个飞书群里互相 @ 协作"这个新模式的完整机制——这是之前系统里从未出现过的协作方式（原来只有一个 bot，Team Lead 在容器内部用 Task 工具调度，不存在"bot 互相 @"）。**"bot 互相 @ 并在群内收发确认"的能力已由用户在实际部署中验证可用，本节不再讨论该能力是否存在，只把它当作既定事实来规范落地结构（2026-09-02 定稿）。**

> **落地前提（2026-09-02 定稿确认）**：两个实例**文件系统隔离**——各自容器/机器互不可见彼此的 `.ai-devflow/`。它们之间唯一的可观测共享通道是**飞书群消息**。因此跨仓库协作的状态真值只能落在群消息里；实例本地的配置/状态文件只做断点缓存，**不是同步源**。协作机制不新增共享存储、不假设同机。

#### 3.2.0 协作子协议总览

跨仓库协作是叠加在单仓库 9 步流程之外的**横向子协议**，只在一个任务"需要跨仓库改动或涉及接口契约"时介入。介入点不是并行跑 9 步，而是插在 9 步之前（阶段 0：对齐）与两个闸门（verify 漂移检测、建 MR 前确认收敛）上。由三件东西承载：

1. **配置**：目标仓库 `.ai-devflow/partner.yaml`（每实例声明"我是谁 / 对面是谁 / 在哪个群"）。
2. **机器可读消息前缀协议**：所有 bot↔bot 契约协作消息带 `[cc-task <task-id>][contract <major>.<minor>]` 前缀，让被唤起的新会话能认出"这是对 task X 契约 vN 的什么动作"。
3. **产物**：`.ai-devflow/<task-id>/contract.json`（对齐快照）+ `.ai-devflow/<task-id>/contract-state.json`（本地断点状态机）。

#### 3.2.1 触发方式与范围判定（阶段 0 入口）

没有统一调度入口。用户在飞书群里凭自己判断直接 `@` 该处理这个需求的 bot（觉得是前端问题就 @frontend-bot，是后端问题就 @backend-bot）。哪个 bot 先被 @，就由它先接手判断范围：

- 读任务/需求，结合 `harness.yaml` 的 `paths` 与需求语义做**影响面判定**，分三类：
  - **纯本仓库**：不进协作子协议，直接走第 6 节 9 步（现有流程不变）。
  - **涉及跨仓库 + 接口契约**：进入阶段 0 对齐子流程（3.2.3），再各自退回 9 步。
  - **纯对方仓库**：不接手，飞书回一句"该由 @partner 处理"，不产生 sandbox/MR。
- 判定结果写进 `intent.md` 的 `## Decision`（沿用 7.7），Accept 且带契约影响面时追加 `## Contract scope` 小节列出候选对齐端点，作为阶段 0 的输入。

#### 3.2.2 对方定位（配置，不是运行时推断）

每个仓库装插件时，在**目标仓库自己的** `.ai-devflow/partner.yaml` 静态声明（文件系统隔离下无共享注册表可互相发现，各写各的，不做双向往返探测）：

```yaml
me:
  bot: "@fe-bot"                 # 本实例在群里的 bot 名（自我识别/落款）
partner:
  bot: "@be-bot"                 # 跨仓库协作对象（对方 bot）
  group_id: "oc_xxxx"            # 双方共同所在的飞书群 chat_id
  contract_dir: ".ai-devflow"    # 对方仓库侧契约产物目录约定（通常同构，可覆盖）
collaboration:
  enabled: true
  auto_align: true               # 命中契约影响面时自动发起对齐；false = 只提示人工在群里发起
```

> 该文件是目标仓库运行时配置（含仓库自己的群/搭档，与插件本体解耦），不入插件仓库、不进 git 远端（随 `.ai-devflow/` 一起被 `.git/info/exclude` 忽略）。读取/校验脚本见 7.15。

#### 3.2.3 对齐与确认（协作范围 + 停止条件）

**协作范围**：@来@去这一段**只做"对齐需求边界和接口契约"**，不是两个 bot 在群里合作改代码——比如后端 bot 发对齐请求"新增接口 `GET /claims/:id/status`，返回 `{status, next_step, eta}`"，前端 bot 确认能接受这个结构。

**消息协议（机器可读前缀，两处新会话靠它识别上下文）**：

- 对齐请求：`[cc-task <task-id>][contract 1.0] 发起契约对齐，端点如下：...`（@ 对方）
- 对齐确认：`[cc-task <task-id>][contract 1.0] 确认` / `拒绝：<差异>`
- 漂移重确认：`[cc-task <task-id>][contract 1.1] 契约漂移：<路径/字段 A→B>，请重新确认`

**发起方流程（阶段 0，发起方=先接手的实例）**：

1. 依据 `intent.md` 的 `## Contract scope`，把候选端点组织成一条对齐请求，@ 对方发到 `partner.yaml` 声明的群里；本地 `contract-state.json` 置 `status: pending`，记录发出的 `message_id`。
2. 对方 bot 被唤起 → 新会话里由 7.15 的识别规则判定为"契约协作消息" → 核对端点/字段对其自身 stack 是否可接受 → 回复确认或拒绝（拒绝附差异，回去改对齐请求再发）。
3. 发起方看到（或被 @ 唤起后收敛到）对方确认 → 把对齐结果写成 `.ai-devflow/<task-id>/contract.json`（结构沿用现有 checker：`{api:[{path,method,...}], meta:{aligned_with, version, aligned_at}}`；端点可带 response 等附加字段，结构校验只要求 `path`+`method`，多余字段兼容）；`contract-state.json` 置 `status: aligned, ack_version: <对齐的 version>`。
4. 双方各自退回自己仓库，从群聊互动中"消失"，各自独立跑第 6 节 9 步。**对齐确认动作触发写 contract.json 的是发起方**，对方不重复写（它只需在群里确认）。

**停止条件**：任一方在群里明确说"契约/接口已对齐"且发起方已落 `contract.json` + `status: aligned`，这轮群内协作即结束。

#### 3.2.4 契约漂移兜底（关键闭环）

（场景：后端独立开发期间改了已对齐的端点/字段。）两个闸门都在**本实例本地**闭环，不依赖对方实时在场：

- **verify 漂移检测**（第 6 节步骤 6）：`contract_checker.py` 在 contract 层比对——当前仓库 `business_code` 是否仍实现 `contract.json` 声明的端点。两级哨兵：**path**（现有语义：路径是否被引用）；**字段级**（7.15 扩展）：端点声明可选 `fields`/`response.fields` 时，对每个字段名做与 path 相同的引用检查，**未声明则不查（默认关）**。任一级不引用 → contract 层 FAIL、归因本仓库 stack.type。
- **重确认子流程**（FAIL 且归因是本仓库 stack 类型时，在回到步骤 5 修复前先走）：把漂移差异组织成一条"漂移重确认"消息 @ 对方发到群里，`contract-state.json` 置 `status: drifted, pending_version: <new>`；等对方新会话确认/建议修正后再更新 `contract.json` 的 version 与端点声明，回到步骤 5 修实现。
- **建 MR 闸门**（步骤 8 的 `create-mr.sh`）：该 task 带 `contract.json` 时，**建 MR 前先收敛**——以 `contract-state.json` 记录的 `last_message_id` 为游标，用 `lark-cli` 查群里该 task 的确认消息，把最新 ack 版本写回本地状态；若收敛结果 ≠ `contract.json` 的 `meta.version`（有漂移未闭环），`create-mr.sh` exit 2 拒绝建 MR 并提示先完成群内重确认。这与 `approval-gate.sh`（拦 `finish-task.sh`）同一治理思路，但挂在建 MR 这一侧。

这样"对齐一次就独立开发"不会变成"契约漂移了对方也不知道"的隐患，形成一个闭环而不是单向脱钩。

**验收（写进 7.15）**：模拟一次前后端在群里对齐接口→确认→各自独立开发→后端改动破坏已对齐端点/字段的场景：`contract_checker.py` 在 verify 阶段检出快照差异并归因本仓库；`create-mr.sh` 在收敛到群内新确认前被拦（exit 2）；触发一次群内"漂移重确认"往返后，确认收敛，建 MR 放行。

### 3.3 插件与运行环境解耦（新增的设计原则）

旧容器把"跑在 Docker 里"这个假设焊死在 `entrypoint.sh`/`Dockerfile` 里。插件不应该重复这个假设——`ai-native-plugin` 只依赖：
- 一个已 checkout 的 git 仓库（不关心是 ai-infra 容器还是本地开发机）
- `lark-cli`（飞书）、`glab`（GitLab MR）在 PATH 里可用
- 仓库自己的 `harness.yaml` 声明测试命令

这样以后 ai-infra 那边如果想把现在这个重的自定义 devflow 镜像换成一个通用轻量基础镜像（装好 `claude` CLI + 用 `claude plugin marketplace add` 装上 `ai-native-plugin`），插件不需要跟着改——**这是本次改造的一个隐含收益**，但 ai-infra 侧的镜像/`provisioner.js` 改造本身不在这份 spec 范围内，只在第 8 节标注集成边界。

---

## 4. 插件内部结构

> 本节按 2026-09-02 用 `claude-code-guide` 核实的官方插件规范重写（此前版本有4处偏差：混用了已被官方合并进 skills 的 `commands/`；调用名格式编造；漏了插件分发必需的 `marketplace.json`；漏了 Python 依赖声明。以下是修正后的版本）。

```
ai-native-plugin/                       (同时是这个插件自己的 marketplace 仓库)
├── .claude-plugin/
│   ├── plugin.json                     # 插件元数据：name 必填，version/description/author 等可选
│   └── marketplace.json                # 插件分发清单，装插件的前提条件，见 4.1
├── agents/
│   ├── frontend.md                     # 前端 persona，并入原 test/verifier 职责
│   └── backend.md                      # 后端 persona，并入原 test/verifier 职责
├── skills/
│   └── devflow-start-task/
│       ├── SKILL.md                    # 原 Team Lead 编排逻辑，第6节展开；调用名 /ai-native-plugin:devflow-start-task
│       └── templates/                  # 该 skill 专属的产物模板
│           ├── INTENT-TEMPLATE.md      # 7.7
│           ├── SPEC-TEMPLATE.md        # 7.9/7.12
│           └── CLAUDE-SUPPLEMENT.md    # 7.6
├── scripts/                            # 移植自 ai-native/scripts/，路径引用改为 ${CLAUDE_PLUGIN_ROOT}/scripts/...
│   ├── verify_runner.py / fast-verify.sh / full-verify.sh
│   ├── attribute.py
│   ├── repair-counter.py
│   ├── ai-review.sh
│   ├── create-mr.sh                    # 内部全部走 glab，见 4.3
│   ├── finish-task.sh                  # 内部全部走 glab，见 4.3
│   ├── contract_checker.py
│   ├── check-bands.py                  # 7.10
│   ├── run-evals.py                    # 7.14
│   ├── emit-event.py / load-events.py / analytics.py
│   ├── ensure-python-deps.sh           # 见 4.2，首次运行时自装 pyyaml/pytest 到 CLAUDE_PLUGIN_DATA
│   └── hooks/
│       ├── protect-paths.sh            # 7.5
│       ├── approval-gate.sh            # 7.8
│       └── deny-secrets.sh             # 7.1，主动暂缓，未接入 hooks.json
├── policies/
│   └── REVIEW.md                       # 评审策略，7.2
└── hooks/
    └── hooks.json                      # PostToolUse(code-review-graph) + PreToolUse(protect-paths/approval-gate)
```

**去掉了 `commands/` 目录**：官方文档已明确"Custom commands have been merged into skills"，且新插件建议直接用 `skills/`，不要两套并存。原来 `commands/start-task.md` 想做的事，`skills/devflow-start-task/SKILL.md` 本身就能承担（skill 支持 `argument-hint` 声明参数）。

**调用名订正**：插件里的 skill 调用名规则是 `/<插件名>:<skill目录名>`。这个插件叫 `ai-native-plugin`，所以正确调用是 **`/ai-native-plugin:devflow-start-task <task-id>`**，不是之前写的 `/devflow:start-task`（那是编造的格式，全文已同步修正）。

### 4.1 marketplace.json：插件能被安装的前提条件

之前的版本完全没提这个文件，导致按原设计这个插件实际上装不上。Claude Code 插件的标准安装流程是：

```bash
claude plugin marketplace add <这个仓库的URL>
claude plugin install ai-native-plugin@<marketplace名>
```

这要求仓库根目录有 `.claude-plugin/marketplace.json`（可以和插件本身放同一仓库，`source` 填相对路径 `./`）：

```json
{
  "name": "ai-native-plugin-marketplace",
  "owner": {"name": "<团队/负责人>"},
  "plugins": [
    {"name": "ai-native-plugin", "source": "./"}
  ]
}
```

**验收**：`claude plugin validate .` 通过；在一个全新仓库里跑 `claude plugin marketplace add <本仓库地址>` + `claude plugin install ai-native-plugin@ai-native-plugin-marketplace` 能成功装上。

### 4.2 外部依赖声明（之前完全遗漏）

官方结论：插件**没有任何机制**能声明"需要预装 Python3/PyYAML/pytest/glab/lark-cli"（Node.js 包有 `package.json` 自动安装，Python/系统 CLI 没有）。旧 Dockerfile 是靠 `pip install pyyaml pytest httpx` + `npm install -g @larksuite/cli` 焊死在镜像里解决的，插件化后这些不会跟着有，必须显式处理：

- **系统级 CLI**（`glab`、`lark-cli`、`git`）：插件无法自动安装，只能在 `README.md` 和 `devflow-start-task` SKILL.md 的开头写清楚前置依赖，并在 Skill 第一步做一次 `command -v glab && command -v lark-cli` 探测，缺失就提示用户先装，而不是跑到中途才报错。
- **Python 包**（`pyyaml`、`pytest`、`httpx`，被 `verify_runner.py`/`check-bands.py`/后端 harness 的 `api_cmd` 用到）：用官方支持的 `${CLAUDE_PLUGIN_DATA}` 目录（插件专属数据目录，卸载时自动清理）自建 venv。新增 `scripts/ensure-python-deps.sh`：

```bash
#!/bin/bash
# 插件专属 venv，装在 CLAUDE_PLUGIN_DATA 下（卸载插件时随之清理，不污染目标仓库环境）
VENV_DIR="${CLAUDE_PLUGIN_DATA}/venv"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q pyyaml pytest httpx
fi
echo "$VENV_DIR/bin/python3"
```

`verify_runner.py`/`check-bands.py` 等脚本的 shebang 或调用处改成先跑一次这个脚本拿到正确的 `python3` 路径，而不是假设系统环境已经装好。**验收**：一个全新、没装过 pyyaml 的机器上，第一次跑 `devflow-start-task` 能自动装好依赖再继续，不因为缺包直接报错退出。

### 4.3 GitLab 操作统一走 glab CLI（2026-09-02 确认）

`create-mr.sh`/`finish-task.sh`（以及第6节里 Team Lead 编排逻辑涉及的任何 GitLab 交互）内部**必须全部调用 `glab` 命令行**，不允许脚本直接拼 GitLab REST API 请求（比如自己 `curl` 打 `/api/v4/projects/:id/merge_requests`）。这不是新功能，是对现有实现方式的显式约束记录——建 MR 用 `glab mr create`，查状态用 `glab mr view`/`glab mr note list`，合并用 `glab mr merge`。好处：`glab` 已经处理好认证（`GITLAB_TOKEN`）、分页、错误提示这些细节，脚本只需要关心业务逻辑；也让 4.2 节"外部依赖清单"里的 `glab` 探测覆盖到所有 GitLab 相关操作，不会有一部分操作绕过依赖检查直接用裸 API 调用。

**目标仓库（团队自己的项目）需要有的东西**（沿用现有约定；跨仓库协作所需的条目见 3.2，属"启用 3.2 协作的任务才需要"）：
- `harness.yaml`（声明 `stack.type` + 分层测试命令，`ads`/`ads-web` 已有现成例子）
- `.ai-devflow/<task-id>/`（运行时产物目录，需要加进该仓库自己的 `.git/info/exclude`）
- 团队自己的 `CLAUDE.md`（插件不再像 Dockerfile 那样焊死一份 `CLAUDE.docker.md` 糊在所有项目头上，而是插件的 Skill 里会提示"读取当前项目已有的 CLAUDE.md 补充上下文"，尊重每个团队自己的组织知识）
- **`harness.yaml`（启用 3.2 协作的任务）**：`gates.full` 含 `contract` 层时其命令由既有 `stack.contract_cmd` 提供（如 ads 的 `python3 <checker> .ai-devflow/contract.json .`）；字段级漂移检测**不新增 harness 命令**——依赖端点里声明的可选 `fields`/`response.fields` + 既有 `paths.business_code`，见 7.15。不启用协作的仓库可完全不配，不破坏现有结构。
- **`.ai-devflow/partner.yaml`**（3.2 目标仓库侧静态配置：`me`/`partner`/`collaboration`，见 3.2.2；该文件不进 git 远端）
- **`.ai-devflow/<task-id>/contract.json` + `contract-state.json`**（3.2 对齐快照与本地断点状态机，见 3.2.3/3.2.4）

---

## 5. Agent 设计

`agents/frontend.md`、`agents/backend.md`，结构与现有 `devflow/agents/frontend.md`/`backend.md` 基本一致（`tools: Read, Write, Edit, Bash, Glob, Grep, LS`，frontend 额外 `model: sonnet`），新增两条规则（把原 test agent 和计划中 verifier agent 的职责并进来）：

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（沿用现有规则，不变）。
2. **【新增】commit 前必须自己跑一次 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh` 自查**，确认自己改的这部分是真通过，而不是完全依赖后续统一验证才第一次发现问题——这是把原来"计划中的独立 verifier agent 事后复核"往前移到"自己先查一遍"，因为现在没有一个共享会话可以再派一个"第三方 agent"去复核，只能靠自查规则加强。

---

## 6. 编排 Skill：`devflow-start-task`

对应原 `devflow-teamlead/SKILL.md` 的 8 步，去掉"派发 frontend **和** backend"，把 7.7（intent.md）接入主流程；**2026-09-02 再次调整**：去掉 sandbox 封装脚本（改成 Skill 内直接执行 git 命令）、去掉评审回路步骤（MR建开后不再自动回修，人工自己处理评论）——现在是 9 步：

> **跨仓库协作叠加层（2026-09-02 定稿，见 3.2）**：下面的 9 步是**单仓库基线流程**。仅当任务带跨仓库契约影响面、且该仓库 `partner.yaml` 的 `collaboration.auto_align: true` 时，才在其上叠加协作子协议：步骤 1 影响面判定命中"涉及跨仓库 + 接口契约" → 插入**阶段 0 对齐**（3.2.3，产出 `contract.json` + `contract-state.json`）再进步骤 2；随后在步骤 6（contract 层漂移检测/重确认）与步骤 8（`create-mr.sh` 前收敛闸门）接入 3.2.4。**纯本仓库任务不进阶段 0、不读 partner.yaml，流程与现状完全一致。**

1. **需求理解 + 写 intent.md**：`lark-cli` 拿分配给**当前仓库**的任务全字段，图片走 sonnet 识图。按 `templates/INTENT-TEMPLATE.md` 写 `.ai-devflow/<task-id>/intent.md`，末尾加 `## Decision: Accept/Reject/Defer + 理由`。**Defer 型任务到此止步**——只飞书知会一句，不进入步骤2，不产生 sandbox 与 MR。Accept 且命中跨仓库契约影响面时，追加 `## Contract scope` 小节（候选对齐端点）作为阶段 0 输入。
2. **写 SPEC.md**（仅 Accept 才继续）：读取 intent.md，按模板写 `.ai-devflow/<task-id>/SPEC.md`（SPEC 首行引用 intent.md 路径，路径在当前仓库工作区里，不再是容器内 `/app/.ai-devflow/`）。
3. **飞书知会**需求方。
4. **建 sandbox**（2026-09-02：不再走封装脚本，Skill 直接执行 git 命令）：`git worktree add .ai-devflow/sandboxes/<task-id> -b task/<task-id>/<ts>`，在当前仓库内建 worktree（隔离同仓库内的并发任务，不是跨仓库隔离）——这一步足够简单，不需要单独维护一个 `make-sandbox.sh` 文件。
5. **派发开发**：用 Task 工具派发给当前仓库对应的 persona（读 `harness.yaml` 的 `stack.type` 决定是 `frontend` 还是 `backend`），该 agent 自己改代码+写测试+自查（见第5节新增规则）。
6. **汇总验证**：跑 `full-verify.sh`，命令定义来自当前仓库自己的 `harness.yaml`。带 `contract.json` 的任务，contract 层按 3.2.4 做字段级漂移比对，检出即进重确认子流程。
7. **FAIL → 归因回流**：`attribute.py` 不变，按 owner 打回步骤5，`repair-counter.py` 计数≥3升级人工。
8. **PASS → Review/建MR**：`ai-review.sh` 读插件自带 `policies/REVIEW.md` 生成 review 包 → `create-mr.sh`（内部走 `glab mr create`，见4.3）建 MR → 飞书卡片通知。**建完 MR 编排流程即告一段落**——不再自动检查/处理 MR 评论，评论由用户自己在 GitLab 上人工跟进（2026-09-02 去掉，原7.13的"@claude 自动回修回路"）。带 `contract.json` 的任务，`create-mr.sh` 建 MR 前先执行 3.2.4 的收敛闸门（群内最新确认版本 ≠ `contract.json` 的 `meta.version` 则 exit 2 拒绝）。
9. **等人工确认 → merge**：`finish-task.sh`（内部走 `glab mr merge`，见4.3）merge + worktree 清理 + 埋点（`approval-gate.sh` hook 强制检查 `HUMAN_APPROVED` 标记文件存在才放行）。

---

## 7. 14 项能力在插件里的完整实现

`ai-native` 仓库 `docs/PLAYBOOK-ADOPTION-STATUS.md` 第六节的 14 项分析结论逐条搬过来，不是总结表，是每一项的完整机制/代码/验收标准——路径和架构按第3节的决策改写，逻辑层面不打折扣。

### 7.1 `.env`/secrets 安全 deny（技术方案存档，主动暂缓）

容器形态下靠 Dockerfile 焊死 `settings.json` 的 `permissions.deny` 强制所有任务遵守。插件形态下插件装不进目标仓库的 `settings.json`，唯一能自动生效（不依赖目标仓库配合）的等价方案是插件自带一条 `PreToolUse` hook：

```json
{
  "matcher": "Read",
  "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/deny-secrets.sh"}]
}
```

`deny-secrets.sh` 逻辑：读 `.tool_input.file_path`，命中 `.env`/`.env.*`/`**/secrets/**`/`**/*.pem`/`**/.git/**` 就 `exit 2` 拦截。**这是完整可行的技术方案，随时可以启用**——本次 brainstorming 中用户明确"暂时不考虑"，标记为主动暂缓，不是遗漏。

### 7.2 REVIEW.md + review.json 拆分

插件自带 `policies/REVIEW.md`：

```markdown
# Review Policy

## Critical
- 改动范围超出 SPEC Task 声明的文件
- AC 未被任何测试覆盖

## Important
- business_code 改了但 test_code 没同步改
- verification.json 存在 NOT_RUN 但被当 PASS 处理

## Nit
- 命名/可读性

Maximum Nit Comments: 5

## 不需要报告
生成文件；CI 已强制的内容（lint/format）。
```

`${CLAUDE_PLUGIN_ROOT}/scripts/ai-review.sh` 改造：checklist 从硬编码改为动态解析插件自带的 `policies/REVIEW.md` 的 Passes 节生成，同时产出机读 `review.json`（`{verdict, critical[], important[], nits[], spec_compliance}`），写到当前仓库的 `.ai-devflow/<task-id>/review.json`。**验收**：改插件的 REVIEW.md 加一条 pass，`ai-review.sh` 生成的 checklist 自动包含新 pass。

### 7.3 verification.json 四态化（ERROR + subtype）

`${CLAUDE_PLUGIN_ROOT}/scripts/verify_runner.py` 的 `run_layer()`：

```python
def run_layer(repo_dir, layer, cmd):
    if not cmd:
        return {"result": "NOT_RUN", "reason": f"{layer}_cmd not configured"}
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=repo_dir, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"result": "ERROR", "subtype": "timeout"}
    except Exception:
        return {"result": "ERROR", "subtype": "infra_exception"}
    return {
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "subtype": "success" if proc.returncode == 0 else "assertion_failed",
    }
```

`attribute.py` 直接用 `subtype == "ERROR"` 判定归 infra，不用再靠关键词猜。**需要补的测试**：新增一个 timeout 用例（`sleep 999` 配合短 timeout），断言 `result=="ERROR"` 且 `subtype=="timeout"`。**验收**：改坏一层命令触发超时，verification.json 显示 `ERROR/timeout` 而不是笼统 `FAIL`。

### 7.4 独立复核：并入 frontend/backend 自查，不新增第三方 agent

**机制**：`agents/frontend.md`/`backend.md` 新增硬性规则——完成开发、准备 commit 前，必须自己执行一次 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh`，把结果贴进自己给 `devflow-start-task` Skill 的完成报告里；自查 FAIL 禁止 commit，必须先修完再提交。这条规则替代了原计划里"Team Lead 判 PASS 后派一个独立上下文的 verifier agent 复核"的功能——单仓库场景下没有另一个仓库/团队可以扮演真正的"第三方"，只能靠强制自查规则弥补这个真空，跟第2节的决策记录保持一致。**验收**：任意开发任务的完成报告里必须包含一次自查的 verification 结果，缺失视为未完成。

### 7.5 hooks 治理护栏 protect-paths

`hooks/hooks.json` 新增：

```json
{
  "PreToolUse": [
    {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/protect-paths.sh", "timeout": 10}]}
  ]
}
```

`scripts/hooks/protect-paths.sh`：

```bash
#!/bin/bash
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

**验收**：agent 尝试编辑这两类路径被拦截，普通业务文件不受影响。

### 7.6 CLAUDE.docker.md 详细化 → 插件自带 CLAUDE.md 补充模板（建议，不焊死）

容器形态下是 `COPY CLAUDE.docker.md /root/.claude/CLAUDE.md` 焊死一份糊在所有项目头上。插件形态下**不能也不应该覆盖目标仓库自己的 CLAUDE.md**——改成插件自带 `templates/CLAUDE-SUPPLEMENT.md`（通用版"验证工作/架构简述/易犯错清单"三节，不含 ads 专属内容），`devflow-start-task` Skill 第一次在某仓库跑起来时，检测该仓库 CLAUDE.md 里没有这几节就提示"是否要把这份模板追加进你的 CLAUDE.md"，用户可以拒绝——**这是"不强制使用方式"原则在这一项上的具体体现**。

### 7.7 intent.md 决策留痕（解决原文档遗留的方案分歧）

原 `ai-native` 分析文档留了两个互斥方案没选：方案A新建独立文件 / 方案B只在SPEC加YAML块。**这次选方案A**——理由：跟第2节"完整保留不阉割"的总决策一致，intent 与 SPEC 分离更贴合官方原意，插件形态下多一个文件的成本可以忽略。

插件自带 `templates/INTENT-TEMPLATE.md`（问题/预期成果/受影响用户系统/约束/待确认问题五节），`devflow-start-task` Skill 步骤1产出 `.ai-devflow/<task-id>/intent.md`，末尾加 `## Decision: Accept/Reject/Defer + 理由`，步骤2读取 intent.md 再写 SPEC.md（SPEC 首行引用 intent.md 路径）。**验收**：处理一个任务，`.ai-devflow/<task-id>/` 下存在含 Decision 段的 intent.md；Defer 型任务不产生 sandbox 与 MR。

### 7.8 Deploy 审批门禁 approval-gate

`hooks/hooks.json` 新增 `Bash` matcher 条目：

```json
{"matcher": "Bash", "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/approval-gate.sh", "timeout": 10}]}
```

`scripts/hooks/approval-gate.sh`：命令含 `finish-task.sh` 时提取 task_id，检查当前仓库 `.ai-devflow/<task_id>/HUMAN_APPROVED` 标记文件是否存在，不存在就 `exit 2` 阻止。标记文件由该仓库实例在飞书收到**自己那条任务**的人工确认回执后自行 `touch` 创建——不再有一个总管会话统一等两边确认，每个仓库实例各自等自己的。**验收**：没有标记文件时 `finish-task.sh` 被拦截，有标记文件后放行。

### 7.9 SPEC.md 决策留痕

插件自带 `templates/SPEC-TEMPLATE.md` 在现有4章基础上补：

```markdown
## 0. 不可违反原则
<列出这个任务不能碰的边界>

### Decision
status: accepted | deferred | rejected
actor: <决策人>
timestamp: <ISO时间>
```

只做增强，不引入风险分级 Gate（Gate 是7.12待拍板的决策，不能顺带塞进这一项）。

### 7.10 bands.yaml 监控闭环

插件自带 `${CLAUDE_PLUGIN_ROOT}/scripts/check-bands.py`，目标仓库自己放一份 `bands.yaml`：

```yaml
metric: repair_round_count
baseline: {strategy: rolling, window_days: 30}
thresholds:
  sigma_2: {action: log}
  sigma_3: {action: notify}
```

`check-bands.py <db_path> [bands_yaml]` 只读当前仓库自己的 `events` 表算 z-score，3σ 时只落一份通知文件到 `.ai-devflow/bands-alerts/<today>.md`，不接入 `emit-event.py`、不自动生成新任务。**验收**：模拟一次 baseline 均值2、当日飙到20 的数据，`check-bands.py` 输出 `tier=sigma_3` 且落一份含 z-score 的通知文件。

### 7.11 Event 加 parent_event_id

```python
# scripts/emit-event.py
p.add_argument("--parent-event-id", default="")
event = {
    "type": args.event_type,
    "event_id": str(uuid.uuid4()),
    "parent_event_id": args.parent_event_id or None,
    ...
}
```

`devflow-start-task` Skill 每次 emit 后把打印出的 `event_id` 存进 SPEC 第4章 Status，下次 emit 时作为 `--parent-event-id` 传入。**必须同步改**：如果新增 `review_passed`/`review_failed` 事件类型，插件自带的 `docs/telemetry-schema.json`（如果插件也要产出遥测 schema）enum 必须跟 `EVENT_TYPES` 同步。**验收**：`analytics.py` 能用递归查询重建一条完整的 task→verification→review→merge 链路。

### 7.12 Gate 分级 / plan.md 批准关卡（技术方案就位，等业务决策启用）

先由负责人定"高风险"判据（如数据库迁移/支付逻辑/跨仓库变更）。`templates/SPEC-TEMPLATE.md` 顶部加 `## 0. Gate Status`（`- [ ] Intent confirmed`，低风险自动勾选跳过，高风险等飞书回执）。若同时要做 plan.md：`agents/frontend.md`/`backend.md` 增加规则——先用 plan mode 产出 `.ai-devflow/<task-id>/plans/<repo>.plan.md`（改哪些文件/顺序/风险/验证方式），编排 Skill 写 `## Decision: Approve/Revise`，Approve 后才能动 business_code，偏离计划要同 commit 更新 plan.md。**这一项的技术实现跟插件化无关，随时可以做**，是否启用取决于"要不要设人工审批卡点"这条业务决策（见第9节第2条），跟能不能把插件搭起来无关。

### 7.13 评审回灌 CLAUDE.md（2026-09-02 收窄范围：去掉自动回修回路）

**去掉的部分**：原设计里"`finish-task.sh` merge 前自动用 `glab mr note list` 检查未解决评论、分类处理、@claude 自动推修复 commit"这条回路已去掉——MR 建开后的评论处理完全交给用户人工在 GitLab 上跟进，不再由插件自动介入，见第6节步骤8。

**保留的部分**（跟自动回修回路无关，是两个独立机制）：
- **CLAUDE.md 回灌规则**：同一错误第二次出现，纠正方法写进该仓库自己的 CLAUDE.md；已在 CLAUDE.md 的错误再犯，提示是否升级为 hook。这条不依赖"自动读MR评论"，可以是人工review时手动发现模式后让 Skill 帮忙写进 CLAUDE.md。
- **遥测回灌**：`analytics.py` 输出增加"建议沉淀"标记（同 owner 连续失败/同 AC 类型反复 FAIL），人工确认后写入 CLAUDE.md/skill。

这两条保留机制跟单/多仓库形态无关，插件化后原样适用。

### 7.14 evals 评测套件

从该仓库真实任务里挑可自包含复现的（纯前端/可 stub 后端），目标20+最低10。目录结构 `evals/<name>/{task.md,setup.sh,check.sh}`。插件自带 `${CLAUDE_PLUGIN_ROOT}/scripts/run-evals.py`：每个 eval 在临时 worktree 跑 `claude -p "<task.md>" --allowedTools "Read,Edit,Bash"`，跑 `check.sh` 断言，汇总JSON通过率。CI（该仓库自己的）命中 `CLAUDE.md`/`.claude/**`/`evals/**` 变更触发，通过率<80%阻止合并。**每起生产事件补一条 eval**，与7.13联动。成本提示：10-20个eval全跑一次约$1-3。

### 7.15 跨仓库契约协作子协议（spec 3.2 落地，2026-09-02 定稿）

把 3.2 从"机制描述"固化为插件可实现的结构。前置事实见 3.2（文件系统隔离、靠飞书群消息闭环、bot 互 @ 能力已验证）。**实现范围**：纯本仓库任务完全不受影响——所有协作逻辑只在 `partner.yaml` 存在且命中契约影响面时才激活。

**新增/改动文件清单**：
- Create `scripts/partner.py`：读/校验 `.ai-devflow/partner.yaml` + `.ai-devflow/<task-id>/contract-state.json`；子命令 `check <repo>`（配置是否齐）、`state <task-id> <status> [--ack-version V] [--msg-id M]`（本地状态机读写）、`gather <task-id>`（收敛：以 `last_message_id` 为游标，`lark-cli` 查群里该 task 的 `[cc-task ...]` 消息，回写最新 ack 版本，stdout 收敛结果）。
- Create `scripts/contract-align.py`：阶段 0 对齐写快照——读 `intent.md` 的 `## Contract scope` 与群里确认到的端点，写 `.ai-devflow/<task-id>/contract.json`（结构沿用现有 checker：`{api:[{path,method,...}], meta:{aligned_with, version:"M.m", aligned_at}}`）+ `contract-state.json`（`status: aligned`）。**不新增校验逻辑**：contract_checker.py 的结构校验（必填 `path`/`method`、多余字段兼容）原样适用。
- Modify `scripts/contract_checker.py`：**字段级引用检查**（现有"path 被引用"语义保留，纯增量）——端点声明可选 `fields` 或 `response.fields` 时，对每个字段名做与 path 相同的 business_code 文本引用检查；**不声明则只做 path 检查（默认关）**。任一级不引用 → exit 1，stderr 分别列出 `missing_paths`/`missing_fields`（形如 `path#field`），归因沿用现有本仓库 stack.type 语义。不新增 harness 命令、不要求 `contract_cmd` 返回任何实现结构。
- Modify `scripts/create-mr.sh`：**建 MR 前收敛闸门**——该 task 有 `contract.json` 时先调 `partner.py gather <task-id>`，收敛后 `ack_version != meta.version` 或 `contract-state.status == drifted` 则 exit 2 拒绝并提示（与 `approval-gate.sh` 拦 `finish-task.sh` 同一治理思路，挂在建 MR 这一侧）。
- Modify `skills/devflow-start-task/SKILL.md`：
  - **步骤 1 影响面判定**：`Accept` 且命中跨仓库契约影响面 → 写 `## Contract scope`；有 `partner.yaml` 且 `auto_align: true` → 执行阶段 0（调 `contract-align.py` 写快照、按 3.2.3 发对齐请求）。
  - **协作消息识别（新会话被唤起时的前置规则，放在"栈判定"之后）**：消息正文含 `[cc-task <task-id>][contract <M.m>]` 前缀 → 若本地 `contract-state.json` 有该 task 且 `status` 为 `pending`/`drifted` → 按前缀动作处理（确认 → 回 `[cc-task X][contract M.m] 确认`；拒绝 → 附差异），处理完更新本地状态，**不进入 9 步主流程**（这是"bot 互 @ 协作"的入口，不是新任务）。
  - **步骤 6**：contract 层 FAIL 且归因本仓库 → 先走重确认子流程（3.2.4：发漂移重确认 @ 对方、`contract-state` 置 `drifted`）再回步骤 5。
- Modify `scripts/emit-event.py`：**不新增事件类型**（遵守 7.11 的 enum 同步约束）——对齐/漂移动作复用 `task_updated`，`data` 带 `phase: "contract-align"|"contract-drift"` + `contract_version`。`docs/telemetry-schema.json` 的 enum 不变，仅 `task_updated.data` 属性说明补这两个字段。

**机器可读消息前缀协议（bot↔bot，双方 SKILL 识别用）**：
```
[cc-task <task-id>][contract <M.m>] <action>
action ∈ {发起契约对齐 / 确认 / 拒绝：<差异> / 契约漂移：<A→B>，请重新确认}
```

**埋点链路**：对齐事件（`task_updated`，phase=contract-align）带 parent_event_id → `analytics.py` 的 `chain` 查询可重建 task→contract-align→verify(contract)→mr 链路（7.11 验收复用，不新增查询）。

**验收**：
1. 两个临时仓库各建 `harness.yaml`（前后端）+ `.ai-devflow/partner.yaml` 互指，模拟一次群内对齐：前端 bot 发起对齐请求（含 `[cc-task]` 前缀）→ 后端 bot 会话识别为协作消息 → 回复确认 → 前端写 `contract.json`（`meta.version=1.0`）、`contract-state` 置 `aligned`。
2. 漂移场景：后端实现改动已对齐端点 → verify 阶段 `contract_checker.py` 检出现有/字段级差异并归因本仓库 → `create-mr.sh` 在未收敛到群内新确认前 exit 2（复刻 3.2 验收原文）。
3. 收敛后放行：后端发漂移重确认 → 前端确认 → `partner.py gather` 收敛 `ack_version=1.1` 且 `contract.json` 更新为 `meta.version=1.1` → `create-mr.sh` 通过。
4. 纯本仓库任务回归：无 `partner.yaml` 或未命中契约影响面时，流程与 3.2 定稿前的 9 步完全一致。

**留档（实现 Task 10 时收敛，不阻塞本项结构定稿）**：字段名引用检查是文本启发式（与 path 检查同级别），可能对过泛字段名（如 `id`）误报/漏报，深度/忽略集作为后续增强；群消息游标用 `message_id` 还是时间戳；`contract-state.json` 的字段名终稿。

本 spec **不重新设计 ai-infra**，只标注边界：
- `provisioner.js` 现在的 `containerSpec` 用的是 `ai-native` 那个重的自定义 Dockerfile（焊死 devflow 模板、飞书/GitLab/OWL 全套 CLI）。
- 插件化之后，理论上 `provisioner.js` 可以指向一个通用轻量镜像（装 `node`+`claude` CLI + 常用 CLI 工具），启动时 `claude plugin marketplace add`/`claude plugin install ai-native-plugin`，而不用为 devflow 单独维护一份重镜像。
- **这个镜像替换工作不在本次范围内**，留给后续单独的 ai-infra 侧改造，本 spec 只保证插件本身不对"跑在 Docker 里"做任何强假设（见 3.3），不阻塞未来这条路。

---

## 9. 未决问题（暂缓，留档）

1. **`.env`/secrets 安全 deny 机制**：容器形态下靠 Dockerfile 焊死 `settings.json` 的 `permissions.deny` 强制所有任务遵守；插件形态下插件无法伸手改目标仓库自己的 `settings.json`。技术上可行的替代方案是插件自带一个 `PreToolUse` hook 拦截 `Read(.env)`（hook 随插件安装自动生效，不依赖目标仓库配合），但本次 brainstorming 中用户明确"暂时不考虑"，留档待后续决策。
2. **"高风险任务需要真人工批准"的判据**：仍然悬而未决（`EXECUTION-PLAN.md:152` 的"不设人工审批卡点"决策与官方 Playbook 的 Gate 设计之间的张力，见 `ai-native` 仓库 `docs/PLAYBOOK-ADOPTION-STATUS.md` 第四节），跟插件化无关，需要负责人单独拍板。

---

## 10. Self-Review

- **Placeholder scan**：无 TBD/TODO，第9节明确列出的是"有意暂缓"而非遗漏；7.15 末尾"留档"列的是实现 Task 10 时收敛的实现细节终稿，非本次结构空缺。
- **一致性**：第2节的决策记录与第3-7节的具体设计逐条对应，没有矛盾；"两个独立容器"这条决策贯穿了第3节架构图、第5节 agent 自查规则新增的原因（没有第三方可派）、第6节编排流程去掉"同时派发前后端"这几处，是自洽的。"文件系统隔离 + 飞书消息闭环"这条 3.2 新增决策与现有"一仓库一实例"（3.1）互不冲突：协作只叠加在契约影响面任务上，纯本仓库流程（第6节基线）不受影响；`contract_checker.py` 结构校验（7.15 复用）与 `emit-event.py` 的 enum 同步约束（7.11，7.15 遵守）也逐条对应，没有为协作引入违背既有约束的新逻辑。
- **范围检查**：聚焦"插件本身怎么设计"，ai-infra 侧的镜像改造明确排除在外（第8节），没有把两个项目的改造混在一份 spec 里。3.2 落地的全部改动都在插件仓库与目标仓库 `.ai-devflow/` 内，不引入共享存储/跨容器基建。
- **依赖顺序**：本 spec 完成后，下一步是用 `superpowers:writing-plans` 把第4-6节拆成可执行的实施计划（先搭插件骨架 `.claude-plugin/plugin.json` + 目录结构，再移植 scripts，再写 agents/skills，最后接 hooks/policies）。Task 1-9 已完成实施后，3.2/7.15 落为计划的阶段 F（Task 10：跨仓库协作子协议），其代码依赖 `contract_checker.py`/`create-mr.sh`/SKILL 结构（Task 4/6/8/3 已交付），不存在前向依赖。
