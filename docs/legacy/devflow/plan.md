# Plan Writer

现在做执行方案设计，不做实现，也不重新定义验收标准。把已定稿的 Spec 收敛成一份
可拆分、可委派、可独立验收的 Plan 文档。回答「怎么拆给谁、怎么证明做对了」。

设计过程用 `EnterPlanMode` 进入计划模式；方案定稿、写入 Plan 文档正文前先
`ExitPlanMode` 请求批准，批准后才落盘产出、走第 8 节 Gate B。

何时读本文件：见 `skills/devflow/SKILL.md`「阶段·产物·分工」表。容器节点必然已
存在（FEATURE：Intent/Spec 阶段已建；`STANDARD_BUG`：Spec 阶段已建）。

`FAST_BUG` 不走本文件——判定标准见 `skills/devflow/bug-triage.md`。

## 1. 信息优先级

1. 当前任务的 Spec 文档 AC
2. 已有 Plan 文档（续做场景）
3. 已有 API / Domain Contract
4. 项目 CLAUDE.md 与现有开发规范

存在冲突：不自行选，写进风险/回滚一节标注，交给需求人判断。

## 2. 产物落盘

产物落**飞书知识库**容器节点下的 `Plan:` 文档；落盘模型、身份（统一 `--as bot`，
理由见 `intent.md` 3.1 节）、本地不留副本见 `artifact-config.md`——未初始化先走
该文件初始化（理论上前面阶段已做过，这里是兜底）。只写 Plan，不碰 Intent / Spec。

按 `Spec:` 前缀读回全文——**写 Plan 前必须先读 Spec**（见第 3 节）。再按 `Plan:`
前缀找 Plan 文档：命中则读回增量修订；未命中则新建：

```bash
lark-cli docs +create --as bot --title "Plan: <需求名称>" --doc-format markdown \
  --content @./draft.md --parent-token <容器节点token> --format json
```

token/URL 只在本次会话内传递，不落本地文件；整篇覆盖 / 小改的写回命令见
`intent.md` 3.2（本阶段只换 `<doc_token>`）。没有容器节点 token → 停下报错，
不自行猜测。续做且改动涉及「关键实现」代码块 → 默认整篇 `overwrite`，不强求
`str_replace` 命中代码块内部（缩进/语言标注对字符敏感，容易假匹配失败）。

**失败处理**：缺 scope / `permission_denied` 的区分与处置见 `artifact-config.md`
第 3 节；parent 不接受 wiki 节点 → 改用 `wiki +node-create --obj-type docx`
（见该文件「两条等价的建文档路径」）；不改 user 身份绕过、API 报错如实报告。

## 3. 写之前必须核对 Spec

禁止脱离 Spec 设计 Plan：

- Spec 的 AC 是否已覆盖所有需要拆分的行为点；Contract 是否已把 FE/BE 共用契约
  固定（Plan 不能改契约，见第 6 节）。
- `STANDARD_BUG` 场景额外核对：Spec 里的 Root Cause 描述是否明确、复现路径是否
  清楚——不明确的写回风险/回滚一节，不自行拍板。

## 4. Plan 写作规则

- **实现策略**：1-3 句说清契约是否先行、FE/BE 能否并行及依据，要有真实判断依据。
- **Task Graph**：缩进代码块画依赖关系，串行写明原因，并行标 `∥`；简单单 Agent
  改动可不强制建这一节。此图会被 IMPLEMENT 阶段直接读取用于判断单 Agent /
  Agent Team 路由，判定规则见 `skills/devflow/SKILL.md`「IMPLEMENT：单 Agent
  vs Agent Team」一节，不在此重复。本节只放依赖图，「关键实现」的代码块不放
  这里，避免依赖信号被代码稀释。
- **任务拆分**：**每个独立验收任务一行一张 Task Card**，禁止写成「前端实现 X、
  后端实现 Y」这种不可独立验收的空话。每张卡含 Owner（`frontend-developer` /
  `backend-developer` / `test-verifier`）、动词开头的一句话、对应 AC 编号、依赖。
  反例「FE-01 前端做登录页」；正例「FE-01 Owner=frontend-developer：在 LoginForm
  增加验证码输入框并处理错误提示（验收 AC2；依赖 BE-01）」。
- **关键实现**：按 Task ID 只写「实现 agent 自己设计容易猜错、返工成本高」的
  技术决策点——接口/函数签名、关键数据结构、状态机转换、核心算法片段，不是全量
  实现；没有分叉空间的任务不用写。只能把 Spec Contract 已固定的接口具体化成调用
  示例，禁止重写其输入输出结构本身（那是重新定义契约，见第 6 节）；全部任务都
  没有决策点 → 整节写「无」。
- **Contract Changes**：与上一版契约的差异、是否向后兼容、影响哪些消费方（不能
  悄悄改契约，见第 6 节）；无变化写「无」。
- **验证方式**：起草前先读 `skills/devflow/test-team.md` 并按其执行——
  按豁免判据决定是否派发 `security-tester` / `whitebox-tester` 补全测试
  用例,产出整合进本节正文;每个任务跑哪条命令、看什么结果算过,不写「确保
  正常」这类空话。
- **风险/回滚**：风险点与回滚方案；第 3 节核对发现的冲突也写在这里。

## 5. 模板（产物必须严格按此结构，一字不改）

`<名称>` 与 Intent/Spec 同名。

````markdown
# Plan: <名称>

> 用途：多 Agent 编排、可独立验收的执行方案；每个任务卡要能单独验收，
> 不写笼统的角色分工描述。

## 实现策略
（1-3 句：契约先行？FE / BE 是否可并行及依据？依赖哪条探索结论？）

## Task Graph
（缩进渲染代码块；串行写明原因，并行标注 ∥）

    BE-01 ─┐
            ├─→ TEST-01        # FE-01 ∥ BE-01（契约已在 SPEC 固定）
    FE-01 ─┘

或：

    BE-01 → FE-01 → TEST-01    # 串行原因：FE 依赖 BE 输出

## 任务拆分
（每个独立验收任务一行一张 Task Card；TEST-01 由 test-verifier 验收）

- [ ] `BE-01` Owner=backend-developer：<以动词开头、可独立验收的一句话>（验收 AC-xx；依赖 无）
- [ ] `FE-01` Owner=frontend-developer：<……>（验收 AC-xx；依赖 BE-01）
- [ ] `TEST-01` Owner=test-verifier：回归与验收全部 AC（依赖 上述实现完成）

## 关键实现
（只写「实现 agent 自己设计容易猜错、返工成本高」的技术决策点：接口/函数签名、
关键数据结构、状态机转换、核心算法片段，不是全量实现；不重复 Spec Contract 已
固定的对外契约结构，只写「满足契约要怎么在这个任务内部实现」。按 Task ID 索引，
只列有决策点的任务，其余任务不出现在本节；全部任务都没有决策点 → 整节写「无」。）

### `BE-01`
- 决策点：<一句话说明为什么这里容易被猜歧义 / 为什么要预先钉死>

```ts
// 关键签名 / 类型定义 / 状态机或算法片段，不是完整实现
```

## Contract Changes
（与上一版契约的差异 / 是否向后兼容 / 影响哪些消费方；无则写「无」）

## 验证方式
（测试小组按 `skills/devflow/test-team.md` 产出的测试用例清单按 Task Card
归类整合于此；每个实现任务跑哪条命令、看什么结果算过；不写「确保正常」这类
空话）

## 风险 / 回滚
（风险点与对应回滚方案）
````

## 6. 禁止事项

- 禁止重新定义验收标准或契约——AC/Contract 以 Spec 为准，Plan 只能引用不能改写。
- 禁止在「关键实现」节重复或改写 Spec 已固定的 Contract（接口/数据/状态机/权限/
  错误码）——只能把契约具体化成调用示例，不能增删契约本身；禁止贴生产级全量
  实现，代码只用来钉死关键决策点，写多了是维护负担，且 Spec 改了 Plan 代码不会
  自动跟着改。
- 禁止把任务拆分写成不可独立验收的空话。
- 禁止碰 Intent / Spec 文档、改容器节点标题、改 Plan 文档标题。
- 禁止在未初始化时自行挑知识空间，或把产物改写到本地文件。
- 禁止在已有同 task-id 容器节点或已有 Plan 文档时再新建第二个。

## 7. 回帖到任务

Plan 定稿、**停下过 Gate B 之前**，若有飞书任务链接，把 Spec + Plan 两篇文档 URL
一起回帖到任务（回帖规则同 `intent.md` 3.3 节：口述需求跳过、只在新建时回帖
一次、失败不阻断产出）：

```bash
lark-cli task +comment --task-id <task_id> --as bot \
  --content "Spec 文档：<spec_doc_url>\nPlan 文档：<plan_doc_url>"
```

## 8. 收尾：Gate B

Plan 定稿后**停下**，与 Spec 一起呈现给需求人确认——**FEATURE 与 `STANDARD_BUG`
都要过 Gate B，没有特例**：给容器节点 URL + Spec/Plan 文档 URL + 任务拆分摘要
（摘要到 Task Card 一行级别，不贴关键实现的代码，需求人要看代码自己点文档 URL）。
**禁止自行批准、自行续跑**；打回则按反馈修订后重新提交。批准后把审批人记进
Plan 与 Spec 两篇文档（见 `skills/devflow/gate-approval.md` 第 3 节）。
