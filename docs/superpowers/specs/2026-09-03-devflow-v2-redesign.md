# AI-Native DevFlow 插件二次设计：入口拆分、Verifier 独立、机器人协作补全

- **日期**：2026-09-03
- **状态**：待审阅（draft）
- **基线**：本次是对 `docs/superpowers/specs/2026-09-02-devflow-plugin-architecture-design.md`（下称"基线 spec"）的定向修订，不推翻其架构决策（一仓库一实例、worktree 隔离、GitLab 走 glab），只调整本文列出的具体条目。未提及的部分沿用基线 spec。
- **触发**：用户对现有 `skills/devflow-start-task/SKILL.md`、`agents/frontend.md`/`backend.md` 提出 13 条反馈 + brainstorming 过程中补出的 1 个协作缺口（任务交接）。

---

## 1. 决策记录

| 决策点 | 结论 |
|---|---|
| 入口拆分方式 | **拆成独立入口 skill**：`devflow-start-task`（需求全流程）+ `devflow-fix-bug`（bug 简化流程），不做同一入口内部分支 |
| 用户如何选入口 | **不需要用户选**——两个 skill 的 `description` 各自写清楚需求特征词 vs bug 特征词，Claude 按对话内容自动路由，不新增路由器 |
| review 能力形态 | **不做第三个顶层入口**，收编为 `skills/review/SKILL.md`（领域能力 skill）；被 `devflow-start-task`/`devflow-fix-bug` 内部自动调用，同时保留用户手动喊"帮我 review 一下这个 MR"的独立触发能力 |
| argument-hint | **去掉**，两个主入口都支持"传 task-id 走飞书拉取" 和 "直接对话描述需求/bug" 两种输入来源，二选一，不强制要 task-id |
| bug 流程复杂度 | **简化为 5 步**：理解→排查→修复方案→开发→验证；不生成 SPEC.md/plan.md 这类需求流程的重工件 |
| bug 排查是否结合日志 | **结合**：目标仓库配了观测云（`owl` cli）时，排查步骤按时间窗口推断+接口过滤查日志；未配置则跳过，纯代码定位，不报错、不阻塞 |
| Verifier 独立性含义 | **Task 子agent 独立上下文**：用 Task 工具起一个全新会话，工具白名单硬性去掉 Write/Edit（不是靠 prompt 软约束），不复用 frontend/backend 自查的文字结论，自己重新跑一遍 diff/verify/AC核对 |
| Agent 与规则的关系 | **解耦**：硬性规则（commit前自查、测试同步）从 `agents/*.md` 抽成独立 `skills/verify/SKILL.md`，frontend/backend/verifier 三方共用同一个 skill，agent md 只保留角色定义 |
| harness.yaml 去留 | **插件自己重新定义**一份最小契约（不依赖 `ai-native` 仓库——那套已在该仓库最近一次容器重构中被删除，没有活的参照物） |
| "契约协作消息"命名 | 改名为**"机器人协作消息"**，相关概念同步改名（机器人对齐/机器人漂移重确认） |
| 跨仓库协作范围 | **原设计有缺口**：只覆盖"对齐接口字段"，没覆盖"把一整块开发工作转交给对方独立完成"。**新增机器人任务交接协议**（见第 5 节），两种协议并存，语义不同不可混用 |
| 任务交接接收方决策权 | **接收方仍要走自己的 Accept/Reject/Defer 判断**，不因为交接方是可信 bot 就默认 Accept——可能存在理解错误/交接理由不成立的情况 |
| 任务交接后的通知对象 | **接收方直接通知原始需求发起人**，不经交接方 bot 转发——交接消息里带上原始发起人身份，接收方 intent.md 完成后直接 @ 那个人，减少一次转发延迟 |
| 飞书通知对象（原"知会需求方"） | 改成**跟谁 @ 机器人就 @ 回谁**（取触发消息事件的 sender），不再依赖 `lark-cli task` 返回的"发起人"字段；无飞书上下文触发时跳过这一步 |
| 机器人边界 | 新增 `skills/bot-boundary/SKILL.md`，**仅限定"飞书群里被另一个 bot @"的场景**：不带 `[cc-task]` 前缀的 bot 消息只输出分析性回复，不执行任何写操作；带前缀的按机器人协作/任务交接协议处理 |
| 踩坑记录存放位置 | **插件仓库内 `PITFALLS.md`**，随插件分发给所有装这个插件的人；不放进 Claude 个人 memory（那样不随插件分发，团队其他人受益不到） |
| 目录结构基本盘 | 借用已在用的 `pipelit` 插件里验证过的两个模式：`failure-modes.md`（阶段/触发条件/兜底行为/是否阻断表）+ `rules/*.md`（决策树替代散文判定）；不搬 `protocols/`、`output-contracts/*.schema.json`（当前没有对应的程序化解析需求，加了是过度设计） |

---

## 2. 目录结构总览

```
ai-native-plugin/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── agents/
│   ├── frontend.md              # 仅角色定义：是谁/读SPEC哪部分/不能碰什么，硬性规则移出
│   ├── backend.md
│   └── verifier.md               # 新增：tools 不含 Write/Edit，独立判 PASS/FAIL
├── skills/
│   ├── devflow-start-task/       # 需求主入口（9步，自动路由）
│   │   ├── SKILL.md
│   │   ├── failure-modes.md
│   │   └── templates/
│   │       ├── INTENT-TEMPLATE.md
│   │       ├── SPEC-TEMPLATE.md
│   │       └── CLAUDE-SUPPLEMENT.md
│   ├── devflow-fix-bug/          # bug主入口（5步，自动路由）
│   │   ├── SKILL.md
│   │   ├── failure-modes.md
│   │   └── rules/
│   │       └── severity.md       # 高风险判定决策树（数据库迁移/支付逻辑/跨仓库→只报告不下手）
│   ├── verify/                   # 领域能力：被 frontend/backend/verifier 三方调用
│   │   └── SKILL.md
│   ├── review/                   # 领域能力：被两条主流程内部调用 + 支持用户手动触发
│   │   └── SKILL.md
│   └── bot-boundary/             # 领域能力：飞书群"被另一个bot @"场景的行为边界
│       └── SKILL.md
├── scripts/
│   ├── verify/                   # verify_runner.py / fast-verify.sh / full-verify.sh
│   ├── state/                    # attribute.py / repair-counter.py
│   ├── review/                   # ai-review.sh
│   ├── lifecycle/                # create-mr.sh / finish-task.sh
│   ├── collab/                   # partner.py / contract-align.py / handoff.py（新增，见第5节）
│   ├── telemetry/                # emit-event.py / load-events.py / analytics.py
│   ├── bootstrap/                # ensure-python-deps.sh
│   └── hooks/                    # protect-paths.sh / approval-gate.sh / deny-secrets.sh(暂缓)
├── policies/
│   └── REVIEW.md
├── PITFALLS.md                   # 新增：外部工具踩坑记录，随插件分发
└── hooks/
    └── hooks.json
```

去掉基线 spec 里的独立 `devflow-review` 顶层 skill 目录，改为 `skills/review/`；新增 `verifier.md`、`skills/bot-boundary/`、`PITFALLS.md`。其余沿用基线 spec 第 4 节结构。

---

## 3. 两个主入口：自动路由，不要求 task-id

### 3.1 为什么不需要用户手动选

Claude Code 按每个 `SKILL.md` 的 `description` 做语义匹配自动调用，不需要额外造路由器。只要两份 description 把"需求特征词"和"bug特征词"写清楚即可让 Claude 自己分对：

```yaml
# skills/devflow-start-task/SKILL.md frontmatter
description: >
  处理新需求/新功能开发。触发词：新增XX、想要一个XX功能、优化XX体验、
  改成XX样式。飞书任务ID也可触发（先判断任务性质，若判定为bug走devflow-fix-bug）。
  走完整9步：理解→intent.md→SPEC→sandbox→开发→验证→归因回流→review→人工确认合并。

# skills/devflow-fix-bug/SKILL.md frontmatter
description: >
  处理bug修复。触发词：报错、坏了、不对、显示错误、点了没反应、XX失败、
  复现步骤、截图里的异常。飞书任务ID也可触发（先判断任务性质）。
  走简化5步：理解→排查→修复方案→开发→验证，不生成SPEC/plan重工件。
```

两者判定有歧义时（比如"这个页面显示不对，顺便加个新筛选项"，既有bug特征又有需求特征）：**按主要工作量归类**——描述里超过一半的诉求是"新增能力"则归 `devflow-start-task`，超过一半是"修正现有行为"则归 `devflow-fix-bug`，读不出主次时用 AskUserQuestion 直接问一句"这个算新需求还是bug修复"，不猜。

### 3.2 输入来源二选一（去掉 argument-hint 后的替代设计）

两个 skill 的第一步统一支持：

```
a) 传了 task-id → lark-cli 拉取飞书任务全字段（图片走 sonnet 识图，识完切回默认模型）
   → 产生飞书通知（见第4节"飞书通知对象"）
b) 直接对话描述需求/bug → 就用这段描述当输入
   → 不产生飞书通知（没有飞书消息上下文可回）
c) 收到机器人任务交接消息（仅devflow-start-task，见第5.2节）
   → 用交接内容当输入，通知交接消息里带的原始发起人
```

---

## 4. `devflow-start-task`：9 步流程（步骤 1 拆细，其余沿用基线 spec 第 6 节）

第 8 条反馈指出原步骤 1 描述语言太抽象，混杂了"怎么拿数据"和"做什么决策"。拆开：

```
1. 理解需求
   1.1 输入来源二选一/三选一（见3.2）
   1.2 写 intent.md（模板不变：问题/预期成果/受影响系统/约束/待确认问题）
   1.3 末尾判定 Decision: Accept / Reject / Defer
       - Defer → 若有飞书触发来源，@回触发者一句说明；到此止步，不产生 sandbox/MR
       - Accept → 继续
   1.4 影响面判定（细化版，见第5.1节）：
       - 纯本仓库 → 走 2-9 步，不进任何协作子协议
       - 涉及跨仓库·仅需对齐字段 → 插入机器人对齐子协议（5.1），完成后回 2-9 步
       - 涉及跨仓库·需要对方真正开发 → 插入机器人任务交接子协议（5.2），
         交接后本仓库这部分若还有工作则继续2-9步，若整块转出则到此止步
       - 纯对方仓库 → 不接手，飞书回一句"该由 @partner 处理"，终止
2. 写 SPEC.md（仅Accept）
3. 飞书通知（@回触发者，见第4节）
4. 建 sandbox（git worktree，当前仓库内隔离并发任务）
5. 派发开发（Task工具派给frontend/backend agent，agent调用skill:verify自查）
6. 汇总验证（skill:verify --full，命中协作任务时含机器人漂移检测）
7. FAIL → 归因回流（attribute.py + repair-counter.py，≥3次升级人工）
8. PASS → 调用 skill:review 生成review包 → 通过则建MR，飞书通知
9. 等人工确认 → merge（finish-task.sh + approval-gate.sh hook 强制检查HUMAN_APPROVED）
```

---

## 5. 跨仓库协作：两种协议并存

原基线 spec 3.2 节只解决"两个 bot 对齐一下接口定义"，覆盖不了"真的把一块开发工作转交给对方独立完成"。这是本次 brainstorming 中发现的缺口，新增第二种协议，两者语义不同，不可混用。

### 5.1 机器人对齐（沿用基线 spec 3.2.3，仅改名）

消息前缀：`[cc-task <task-id>][contract <M.m>] <action>`，action ∈ `发起机器人对齐`/`确认`/`拒绝：<差异>`/`机器人漂移重确认：<A→B>`。

适用场景：**只需要确认一下接口/字段定义能不能被对方接受，不需要对方真的动手改代码**（比如"我要加个接口返回这几个字段，你能接受这个结构吗"）。确认完双方各自退回本仓库独立开发，机制细节（contract.json 快照、字段级漂移检测、建MR前收敛闸门）不变，见基线 spec 3.2.3/3.2.4/7.15。

### 5.2 机器人任务交接（新增）

适用场景：**己方判定这块工作根本不该由自己完成，需要对方仓库真正开发**（比如前端处理需求时发现"这个功能后端接口不存在，得后端从零开发一个"）。

消息前缀：`[cc-task <task-id>][handoff] <action>`，action ∈：
- `交接请求：<需求摘要> | 触发原因：<为什么判定对方需要开发> | 原始发起人：<@某人 或 无（对话触发）>`
- `接受`
- `拒绝：<理由>`
- `延后：<理由>`
- `已完成：<MR链接>`

**流程**：

1. 发起方（如前端bot）在步骤 1.4 影响面判定中识别出"需要对方真开发"，发交接请求 @ 对方 bot，消息里带上第 3 类原因（`原始发起人` 字段，取自触发这次会话的飞书消息 sender；若是对话触发则填"无"）。
2. 接收方（如后端bot）会话被唤起，识别 `[handoff]` 前缀 → **把交接内容当成自己 `devflow-start-task` 步骤1的输入来源（c类，见3.2）**，走自己完整的 1.1-1.4：自己写 intent.md、自己独立判断 Accept/Reject/Defer——**不因为交接方是可信bot就默认Accept**，可能交接理由本身就站不住脚。
3. 接收方 Accept → intent.md 完成后，**直接通知原始发起人**（若"原始发起人"字段非空，@回那个人；若为无，跳过通知），说明"已接手，正在处理"，然后独立跑完整 2-9 步（自己的SPEC/sandbox/开发/验证/review/MR），跟发起方仓库的流程互不阻塞。
4. 接收方 Reject/Defer → 回 `[cc-task X][handoff] 拒绝：<理由>` 给发起方 bot，发起方收到后**必须转告原始发起人**（这一步不能省，否则需求方会以为已经在处理）。
5. 接收方完成开发（MR建好）→ `[cc-task X][handoff] 已完成：<MR链接>` 回发起方群，发起方视情况通知原始发起人"已由XX仓库处理，MR见此"（若步骤3已经让接收方直接通知过，这里发起方只需在自己任务记录里标注完成，不必重复打扰用户）。

**与机器人对齐的关键区别**：对齐是"确认字段定义，各自退回本仓库独立开发"，交接是"整块工作真实转移，接收方走自己完整devflow且有独立决策权"。两种协议不共用确认/拒绝语义，`[contract]`前缀的消息不会被误当成`[handoff]`处理，反之亦然。

---

## 6. `devflow-fix-bug`：5 步简化流程

```
1. 理解
   - 输入来源二选一/三选一（同3.2，交接场景同样适用于bug——后端bot收到bug交接后走自己的5步而非9步）
   - 额外识别：复现路径/报错信息/截图
2. 排查
   - 目标仓库配置了观测云（检测 `owl` cli 是否在PATH + 项目是否声明观测云workspace）：
     结合日志排查，按时间窗口推断（P1截图时间戳 > P2描述短语 > P3任务创建时间fallback）
     + 接口路径过滤查询错误/全量日志
   - 未配置：跳过日志辅助，纯代码 grep 定位，不报错、不阻塞
   - 按 rules/severity.md 决策树判定风险等级：
     高风险（数据库迁移/支付逻辑/跨仓库影响面大）→ 只输出排查报告，到此止步，不进入3-5
     普通 → 继续
3. 修复方案
   - 写清楚要改什么/不改什么（轻量文字说明，不生成SPEC.md/plan.md）
4. 开发
   - 派给 frontend/backend agent 直接改（bug场景不需要Task Breakdown那套结构）
5. 验证
   - agent 调用 skill:verify 自查
   - 调用 skill:review 生成review包
   - 视风险等级决定是否需要 verifier 独立复核（普通bug可跳过，风险判定为"中"但未到"高风险止步线"的可选择性触发）
```

`skills/devflow-fix-bug/rules/severity.md` 决策树示例（按优先级自上而下匹配）：

| 优先级 | 条件 | 判定 | 处理 |
|---|---|---|---|
| 1 | 描述含"数据库迁移"/"支付"/"资金"/"批量删除" | 高风险 | 只输出排查报告，止步 |
| 2 | 影响面判定为"涉及跨仓库+需要对方开发" | 高风险 | 转入第5.2节机器人任务交接，不在本仓库直接修 |
| 3 | grep 候选文件 > 5 | 中风险 | 继续，但验证阶段建议触发verifier |
| 4 | 其他 | 普通 | 继续5步，验证阶段可跳过verifier |

---

## 7. Verifier 独立性与 Agent-Skill 解耦

### 7.1 `agents/verifier.md`（新增）

```yaml
tools: Read, Bash, Glob, Grep, LS   # 硬性不含 Write/Edit
```

由 `devflow-start-task`/`devflow-fix-bug` 用 Task 工具起一个全新上下文的子会话派给它。**不信任前面自查结论**，具体落地：verifier 只拿三样东西自己算，不接收 agent 转述的文字结论作为证据：

1. 自己跑 `git diff <base>...HEAD`
2. 自己重跑一次 `skill:verify --independent`（强制忽略已有 verification.json，重新执行分层命令）
3. 自己读 SPEC.md 里 owner 对应的 AC 列表，逐条核对 diff 是否覆盖

只输出 `PASS` 或 `FAIL + EVIDENCE`（具体是哪条AC没覆盖/哪层命令失败），不给修复建议——避免它越权变成"第二个开发者"。判 FAIL 直接回归归因回流（第4节步骤7），不需要人工介入。

### 7.2 `skills/verify/SKILL.md`（新增，从 agent md 里抽出的硬性规则）

原基线 spec `agents/frontend.md`/`backend.md` 里的两条硬性规则移到这里：

```markdown
## 参数：--self-check | --independent | --full

--self-check（frontend/backend commit前调用）：
  1. 改了 harness.yaml 声明的 paths.business_code 必须同步改 paths.test_code
     （git diff --name-only 检查，只有business_code路径无test_code路径 → 先补测试）
  2. 跑 harness.yaml 声明的 gates.fast 命令
  3. FAIL 禁止 commit，先修完再提交

--independent（verifier调用）：
  1. 忽略已有 verification.json，强制重新执行
  2. 跑 gates.full 全部命令
  3. 输出 PASS/FAIL + 逐层EVIDENCE，不做修复

--full（编排skill步骤6汇总验证调用）：
  同 --independent 的执行部分，但产出写入 verification.json 供 attribute.py 读取
```

`agents/frontend.md`/`backend.md` 因此只保留角色定义（你是谁/只读SPEC里哪个owner的AC/不接受口头需求变更/不改不属于自己的文件），commit前那句改成"调用 `skill:verify --self-check`"。

---

## 8. 飞书通知与机器人边界

### 8.1 通知对象

原"知会需求方"逐条改为"@回触发者"：

```
触发来源a（task-id）→ 读飞书消息事件的 sender（谁@了机器人），通知回那个人
触发来源b（对话描述）→ 无飞书消息上下文，跳过通知
触发来源c（机器人交接）→ 通知交接消息里携带的"原始发起人"字段（见5.2）
```

不再依赖 `lark-cli task tasks get` 返回的"发起人"字段（该字段在有些任务里可能是任务分配人而非实际@机器人的人，容易对错人）。

### 8.2 `skills/bot-boundary/SKILL.md`（新增）

仅限定"飞书群里被另一个 bot @"的场景，与"被人类用户@"区分：

```
触发条件：飞书群消息 sender 是另一个bot身份
判断：
  消息带 [cc-task][contract] 前缀 → 走机器人对齐协议（5.1）
  消息带 [cc-task][handoff] 前缀   → 走机器人任务交接协议（5.2）
  消息不带任何已知前缀            → 只输出分析性回复，不执行任何写操作
                                    （不改代码、不建sandbox、不建MR、不merge）
```

这条边界只管"另一个bot发来的、不带已知协议前缀的消息"该怎么办——避免机器人之间闲聊式@意外触发完整devflow。带前缀的消息则严格按各自协议处理，不受此边界限制（协议本身已经定义好该做什么）。

---

## 9. harness.yaml：插件自建最小契约

`ai-native` 仓库原有的 `docker/harness-adapters/*/harness.yaml` 已在该仓库最近一次容器重构（commit `1e39f4e`）中被删除，容器现状收敛成极简 CLAUDE.md，不再有分层验证契约可参照。插件不依赖那套已废弃的实现，自己重新声明一份最小字段集：

```yaml
project:
  stack:
    type: frontend | backend      # 决定加载哪个 persona（frontend.md/backend.md）
paths:
  business_code: ["src/**"]       # skill:verify --self-check 用于"测试是否同步"检查
  test_code: ["test/**", "tests/**"]
gates:
  fast: [unit]                    # commit前自查跑哪些层
  full: [unit, contract]          # 汇总验证/独立verifier跑哪些层，contract层可选
commands:
  unit: "npm run test:unit"       # 具体命令按仓库自己的栈填
  contract: "python3 <checker> ."  # 仅命中跨仓库协作任务时使用
```

**作用**：这是仓库与插件之间的一份显式合同——仓库声明"测试命令是这个/源码测试路径在这"，插件承诺"不猜，只按你说的做"。没有它时插件不知道该跑哪条命令，只能停下来问，不做探测猜测（第6条已明确拒绝猜测路线，猜错比停下问更糟）。

**生效点**：
- 两个主入口步骤1"栈判定"读 `stack.type` 决定派发角色
- `skill:verify` 三种模式分别读 `gates.fast`/`gates.full` + `commands.*` 拼接实际执行的shell命令
- 首次在某仓库运行且缺失 `harness.yaml` → 停下询问用户是否要生成向导，不強行猜测项目结构

---

## 10. PITFALLS.md：踩坑记录机制

新建插件仓库根目录 `PITFALLS.md`，随插件分发（团队其他人装同一个插件时直接受益，不是只存在某个人的Claude memory里）：

```markdown
| 工具/场景 | 已知问题 | 规避方法 | 发现时间 |
|---|---|---|---|
| lark-cli | <具体问题> | <怎么避免> | 2026-09-03 |
```

**写入触发**：不自动写。某次任务里 agent 调用 lark-cli/glab/owl 等外部工具时踩坑（报错、返回格式出乎意料、或被用户当场纠正错误用法），任务收尾时若发生过这类纠偏，主动问用户"这次踩了个坑，要不要记进PITFALLS.md"，用户确认后才追加一行，且作为独立commit（不与业务改动混在一起，避免污染功能提交历史）。

**读取触发**：任何skill在当次会话第一次调用 lark-cli/glab/owl 之前，先grep一下`PITFALLS.md`里有没有该工具的记录，有就提前应用"已知问题+规避方法"，不等报错了才后知后觉。

**不做的部分**：不引入自动过期检测/定期核查机制——记录只会越攒越多，若某条后来发现已不适用，靠人工任务中偶然发现顺手改/删，不为一次性问题加自动化复杂度。

---

## 11. Self-Review

- **Placeholder scan**：无 TBD/TODO。
- **一致性**：第5.1/5.2两种协作协议前缀不同（`[contract]` vs `[handoff]`），第8.2机器人边界规则能正确区分两者，不会误判；第3节自动路由与第4/6节两个流程的输入来源(a/b/c)三选一贯穿一致；第7节verifier的"不复用自查结论"与第7.2 skill:verify的`--independent`模式（强制重跑、忽略已有verification.json）逐条对应。
- **范围检查**：本次只修订基线spec里被反馈指出的13个点+1个协作缺口，未触及基线spec已拍板但未被反馈提及的部分（如插件与运行环境解耦、GitLab走glab、marketplace.json等），这些原样沿用基线spec，不在本文重复。
- **依赖顺序**：本文完成后，下一步是用 `superpowers:writing-plans` 把第2、4、5、6、7、8、9、10节拆成可执行实施计划。建议顺序：先改目录结构（第2节）→ 拆skill/agent文件（第4/6/7节，纯文件搬移+改写，风险最低）→ 新增机器人协作机制（第5节，依赖scripts/collab/新脚本）→ 飞书通知改造（第8节，依赖能拿到消息sender的接口）→ harness.yaml规范文档化（第9节）→ PITFALLS.md机制（第10节，最后做，依赖前面机制先跑起来才有坑可记）。
