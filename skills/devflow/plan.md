# Plan Writer

现在做执行方案设计，不做实现，也不重新定义验收标准。把已定稿的 Spec 收敛成一份
可拆分、可委派、可独立验收的 Plan 文档。回答「怎么拆给谁、怎么证明做对了」。

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

产物落**飞书知识库**：容器节点下的 Plan 文档。本地不留副本，草稿写 `/tmp`。

- 未初始化 → 先走 `skills/devflow/artifact-config.md` 初始化（理论上前面阶段已做过，这里是兜底）。
- 只写 Plan，不碰 Intent / Spec。身份统一 `--as bot`，理由见 `intent.md` 3.1 节。

按 `Spec:` 前缀读回全文——**写 Plan 前必须先读 Spec**（见第 3 节）。再按 `Plan:`
前缀找 Plan 文档：命中则读回增量修订；未命中则新建：

```bash
lark-cli docs +create --as bot --title "Plan: <需求名称>" --doc-format markdown \
  --content @./draft.md --parent-token <容器节点token> --format json
```

Plan 文档 token/URL **只在本次会话内传递**，不落本地文件。写入整篇覆盖：
`lark-cli docs +update --as bot --doc <doc_token> --command overwrite --doc-format markdown --content @./section.md`
（小改可用 `--command str_replace`）。没有容器节点 token → 停下报错，不自行猜测。

**失败处理**：缺 scope → 走 `artifact-config.md` 授权流程；`permission_denied` →
先查 bot 是否还在知识空间里，不改 user 身份绕过；parent 不接受 wiki 节点 → 改用
`wiki +node-create --obj-type docx`；API 报错如实报告。

## 3. 写之前必须核对 Spec

禁止脱离 Spec 设计 Plan：

- Spec 的 AC 是否已覆盖所有需要拆分的行为点；Contract 是否已把 FE/BE 共用契约
  固定——**Plan 不能重新定义契约，只能引用**。
- `STANDARD_BUG` 场景额外核对：Spec 里的 Root Cause 描述是否明确、复现路径是否
  清楚——不明确的写回风险/回滚一节，不自行拍板。

## 4. Plan 写作规则

- **实现策略**：1-3 句说清契约是否先行、FE/BE 能否并行及依据，要有真实判断依据。
- **Task Graph**：缩进代码块画依赖关系，串行写明原因，并行标 `∥`；简单单 Agent
  改动可不强制建这一节。此图会被 IMPLEMENT 阶段直接读取用于判断单 Agent /
  Agent Team 路由，判定规则见 `skills/devflow/SKILL.md`「IMPLEMENT：单 Agent
  vs Agent Team」一节，不在此重复。
- **任务拆分**：**每个独立验收任务一行一张 Task Card**，禁止写成「前端实现 X、
  后端实现 Y」这种不可独立验收的空话。每张卡含 Owner（`frontend-developer` /
  `backend-developer` / `test-verifier`）、动词开头的一句话、对应 AC 编号、依赖。
  反例「FE-01 前端做登录页」；正例「FE-01 Owner=frontend-developer：在 LoginForm
  增加验证码输入框并处理错误提示（验收 AC2；依赖 BE-01）」。
- **Contract Changes**：与上一版契约的差异、是否向后兼容、影响哪些消费方；必须与
  Spec 的 Contract 一致，**不能在 Plan 里悄悄改契约**；无变化写「无」。
- **验证方式**：每个任务跑哪条命令、看什么结果算过，不写「确保正常」这类空话。
- **风险/回滚**：风险点与回滚方案；第 3 节核对发现的冲突也写在这里。

## 5. 模板（产物必须严格按此结构，一字不改）

`<名称>` 与 Intent/Spec 同名。

```markdown
# Plan: <名称>

> 用途：多 Agent 编排的执行方案。不能写成「前端实现 X、后端实现 Y」这种
> 不可独立验收的空话。

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

## Contract Changes
（与上一版契约的差异 / 是否向后兼容 / 影响哪些消费方；无则写「无」）

## 验证方式
（每个实现任务跑哪条命令、看什么结果算过；不写「确保正常」这类空话）

## 风险 / 回滚
（风险点与对应回滚方案）
```

## 6. 禁止事项

- 禁止重新定义验收标准或契约——AC/Contract 以 Spec 为准，Plan 只能引用不能改写。
- 禁止把任务拆分写成不可独立验收的空话。
- 禁止碰 Intent / Spec 文档、改容器节点标题、改 Plan 文档标题。
- 禁止在未初始化时自行挑知识空间，或把产物改写到本地文件。
- 禁止在已有同 task-id 容器节点或已有 Plan 文档时再新建第二个。

## 7. 收尾：Gate B

Plan 定稿后**停下**，与 Spec 一起呈现给需求人确认——**FEATURE 与 `STANDARD_BUG`
都要过 Gate B，没有特例**：给容器节点 URL + Spec/Plan 文档 URL + 任务拆分摘要。
**禁止自行批准、自行续跑**；打回则按反馈修订后重新提交。

`FAST_BUG` 不走本文件，不过 Gate B——判定标准见 `skills/devflow/bug-triage.md`。
