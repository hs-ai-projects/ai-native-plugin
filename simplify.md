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
| 本 spec 存放位置 | `ai-native-plugin` 仓库（这是新项目真实归属地，不放在 `ai-native` 里） |
| `.env`/secrets deny 机制 | **暂缓，留档**（见第 9 节），插件形态下这条不能再靠 Dockerfile 焊死，需要额外方案，本次不展开 |

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

> **订正说明**：初版这里写的"靠飞书任务关联"是没有技术依据的编造说法。核实 `entrypoint.sh:216-271` 和 `Claude_Agent_Teams_AI_DevFlow_Final_Design.md` §4.2 后确认：cc-connect 现状是**一个容器绑一个飞书 bot 身份**（`config.toml` 的 `[[projects.platforms]]` type=feishu），`group_only=true`/`thread_isolation=true`。插件化后两个仓库各自的容器/实例各接一个 cc-connect（各自独立的飞书 bot），本节描述的是"两个 bot 能在同一个飞书群里互相 @ 协作"这个新模式的完整机制——这是之前系统里从未出现过的协作方式（原来只有一个 bot，Team Lead 在容器内部用 Task 工具调度，不存在"bot 互相 @"）。

**触发方式**：没有统一调度入口。用户在飞书群里凭自己判断直接 `@` 该处理这个需求的 bot（觉得是前端问题就 @frontend-bot，是后端问题就 @backend-bot）。哪个 bot 先被 @，就由它先接手判断范围。

**对方定位**：每个仓库装插件时，在插件配置里静态声明"我的搭档 bot 是谁/在哪个飞书群"（比如 `ads-web` 仓库的插件配置写 `partner_bot: "@ads-backend-bot"`，`ads` 仓库反过来写 `partner_bot: "@ads-web-bot"`）。这是显式配置，不是运行时推断——因为两边的 bot 都是各自平台创建的，没有一个共享注册表能互相发现，配置项写在哪由第4节的插件配置文件承载（新增 `config/partner.yaml` 或类似结构，具体落点见实施计划）。

**协作范围**：@来@去这一段**只做"对齐需求边界和接口契约"**，不是两个 bot 在群里合作改代码——比如后端 bot 在群里说"新增接口 `GET /claims/:id/status`，返回 `{status, next_step, eta}`"，前端 bot 确认能接受这个结构。

**停止条件**：任一方在群里明确说"契约/接口已对齐"，这轮群内协作即结束。确认动作触发发起确认那一方写一份 `.ai-devflow/<task-id>/contract.json`（沿用现有 `contract_cmd`/`contract_checker.py` 机制，不新增校验逻辑）。随后两个 bot 各自退回自己仓库，从群聊互动中"消失"，各自独立跑第6节的完整10步流程。

**契约漂移兜底**（关键，没有这条会有真实风险）：后端在自己仓库独立开发期间，如果实现跟对齐时的 `contract.json` 快照不一致（比如返回字段临时改了），`scripts/contract_checker.py` 在步骤6"汇总验证"时对比当前实现与已对齐快照——**发现不一致就自动在原飞书群重新 `@` 对方确认，确认前不允许进入步骤8建 MR**。这样"对齐一次就独立开发"不会变成"契约漂移了对方也不知道"的隐患，形成一个闭环而不是单向脱钩。

**验收**：模拟一次前后端在群里对齐接口→确认→独立开发→后端改动破坏已对齐字段的场景，`contract_checker.py` 在 verify 阶段应能检测出快照差异并阻止建 MR，同时触发一次群内重新确认的通知。

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
│   ├── make-sandbox.sh
│   ├── verify_runner.py / fast-verify.sh / full-verify.sh
│   ├── attribute.py
│   ├── repair-counter.py
│   ├── ai-review.sh
│   ├── create-mr.sh
│   ├── finish-task.sh
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

**目标仓库（团队自己的项目）需要有的东西**（沿用现有约定，不新增）：
- `harness.yaml`（声明 `stack.type` + 分层测试命令，`ads`/`ads-web` 已有现成例子）
- `.ai-devflow/<task-id>/`（运行时产物目录，需要加进该仓库自己的 `.git/info/exclude`）
- 团队自己的 `CLAUDE.md`（插件不再像 Dockerfile 那样焊死一份 `CLAUDE.docker.md` 糊在所有项目头上，而是插件的 Skill 里会提示"读取当前项目已有的 CLAUDE.md 补充上下文"，尊重每个团队自己的组织知识）

---

## 5. Agent 设计

`agents/frontend.md`、`agents/backend.md`，结构与现有 `devflow/agents/frontend.md`/`backend.md` 基本一致（`tools: Read, Write, Edit, Bash, Glob, Grep, LS`，frontend 额外 `model: sonnet`），新增两条规则（把原 test agent 和计划中 verifier agent 的职责并进来）：

1. **改了 `paths.business_code` 必须同步写/改 `paths.test_code`**（沿用现有规则，不变）。
2. **【新增】commit 前必须自己跑一次 `${CLAUDE_PLUGIN_ROOT}/scripts/full-verify.sh` 自查**，确认自己改的这部分是真通过，而不是完全依赖后续统一验证才第一次发现问题——这是把原来"计划中的独立 verifier agent 事后复核"往前移到"自己先查一遍"，因为现在没有一个共享会话可以再派一个"第三方 agent"去复核，只能靠自查规则加强。

---

## 6. 编排 Skill：`devflow-start-task`

对应原 `devflow-teamlead/SKILL.md` 的 8 步，去掉"派发 frontend **和** backend"，并把第7节里 7.7（intent.md）、7.13（双向评审回灌）两项已经设计好的机制正式接入主流程（之前版本漏了，只在7.7/7.13单独描述，没体现在这里）——现在是完整 10 步：

1. **需求理解 + 写 intent.md**：`lark-cli` 拿分配给**当前仓库**的任务全字段，图片走 sonnet 识图。按 `templates/INTENT-TEMPLATE.md` 写 `.ai-devflow/<task-id>/intent.md`，末尾加 `## Decision: Accept/Reject/Defer + 理由`。**Defer 型任务到此止步**——只飞书知会一句，不进入步骤2，不产生 sandbox 与 MR。
2. **写 SPEC.md**（仅 Accept 才继续）：读取 intent.md，按模板写 `.ai-devflow/<task-id>/SPEC.md`（SPEC 首行引用 intent.md 路径，路径在当前仓库工作区里，不再是容器内 `/app/.ai-devflow/`）。
3. **飞书知会**需求方。
4. **建 sandbox**：`${CLAUDE_PLUGIN_ROOT}/scripts/make-sandbox.sh` 在当前仓库内建 worktree（隔离同仓库内的并发任务，不是跨仓库隔离）。
5. **派发开发**：用 Task 工具派发给当前仓库对应的 persona（读 `harness.yaml` 的 `stack.type` 决定是 `frontend` 还是 `backend`），该 agent 自己改代码+写测试+自查（见第5节新增规则）。
6. **汇总验证**：跑 `full-verify.sh`，命令定义来自当前仓库自己的 `harness.yaml`。
7. **FAIL → 归因回流**：`attribute.py` 不变，按 owner 打回步骤5，`repair-counter.py` 计数≥3升级人工。
8. **PASS → Review/建MR**：`ai-review.sh` 读插件自带 `policies/REVIEW.md` 生成 review 包 → `create-mr.sh` 建 MR → 飞书卡片通知。
9. **评审回路**（对应7.13，之前漏接的一步）：`glab mr note list` 检查未解决评论——含 `@claude` 或未解决讨论就分类处理：可修复缺陷在沙箱新 commit 修复推送更新 MR；需求偏差回飞书对齐更新 SPEC；一次性意见记录忽略。**所有未解决评论关闭后才能进入步骤10**。
10. **等人工确认 → merge**：`finish-task.sh` merge + worktree 清理 + 埋点（`approval-gate.sh` hook 强制检查 `HUMAN_APPROVED` 标记文件存在才放行）。

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

### 7.13 双向评审回灌 CLAUDE.md

**@claude 修复回路**：`finish-task.sh` merge 前用 `glab mr note list` 检查未解决评论，含 `@claude` 或未解决讨论就分类处理——可修复缺陷在沙箱新 commit 修复推送更新 MR（commit 带 `Claude Fix:` 前缀+评论 id）；需求偏差回飞书对齐更新 SPEC；一次性意见记录忽略。所有未解决评论关闭后才允许 merge。**回灌规则**：同一错误第二次出现，纠正方法写进该仓库自己的 CLAUDE.md；已在 CLAUDE.md 的错误再犯，提示是否升级为 hook。**遥测回灌**：`analytics.py` 输出增加"建议沉淀"标记（同 owner 连续失败/同 AC 类型反复 FAIL）。这一项跟单/多仓库形态无关，插件化后原样适用。

### 7.14 evals 评测套件

从该仓库真实任务里挑可自包含复现的（纯前端/可 stub 后端），目标20+最低10。目录结构 `evals/<name>/{task.md,setup.sh,check.sh}`。插件自带 `${CLAUDE_PLUGIN_ROOT}/scripts/run-evals.py`：每个 eval 在临时 worktree 跑 `claude -p "<task.md>" --allowedTools "Read,Edit,Bash"`，跑 `check.sh` 断言，汇总JSON通过率。CI（该仓库自己的）命中 `CLAUDE.md`/`.claude/**`/`evals/**` 变更触发，通过率<80%阻止合并。**每起生产事件补一条 eval**，与7.13联动。成本提示：10-20个eval全跑一次约$1-3。

---

## 8. 与 ai-infra / 现有 Dockerfile 的集成边界

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

- **Placeholder scan**：无 TBD/TODO，第9节明确列出的是"有意暂缓"而非遗漏。
- **一致性**：第2节的决策记录与第3-7节的具体设计逐条对应，没有矛盾；"两个独立容器"这条决策贯穿了第3节架构图、第5节 agent 自查规则新增的原因（没有第三方可派）、第6节编排流程去掉"同时派发前后端"这几处，是自洽的。
- **范围检查**：聚焦"插件本身怎么设计"，ai-infra 侧的镜像改造明确排除在外（第8节），没有把两个项目的改造混在一份 spec 里。
- **依赖顺序**：本 spec 完成后，下一步是用 `superpowers:writing-plans` 把第4-6节拆成可执行的实施计划（先搭插件骨架 `.claude-plugin/plugin.json` + 目录结构，再移植 scripts，再写 agents/skills，最后接 hooks/policies）。
