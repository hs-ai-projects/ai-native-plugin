# Spec Writer

现在做验收标准定义，不做实现方案（Plan 是下一步）。把已批准的 Intent（FEATURE）
或已确认的 Root Cause（`STANDARD_BUG`）收敛成一份可测试、防止实现 Agent 猜测契约
的 Spec 文档。回答「什么叫正确」，不回答「代码怎么写」。

何时读本文件：见 `skills/devflow/SKILL.md`「阶段·产物·分工」表。FEATURE 场景带
容器节点 token/URL；`STANDARD_BUG` 场景容器节点可能不存在，需先新建（见第 2 节）。

## 1. 依据与冲突处理

FEATURE 依据已批准 Intent 的 Outcome/Out of Scope（不能突破）；`STANDARD_BUG`
依据已确认的 Root Cause 与复现路径（不是猜测）。其次参考已有 Spec、已有 API/
Domain Contract、项目 CLAUDE.md、现有代码行为——但都不能压过上面两条。核对依据
只用于判断是否偷偷扩大范围，不写进 Spec 正文。

依据之间冲突、或现状与依据描述不一致：不自行选，写进 Open Questions 并标注
冲突点（Open Questions 定义见第 3 节）。

## 2. 产物落盘

产物落**飞书知识库**容器节点下的 `Spec:` 文档；落盘模型、身份（统一 `--as bot`）、
本地不留副本、标题与新建约束见 `artifact-config.md`——未初始化先走该文件初始化
流程。只写 Spec，不碰 Intent/Plan，不改业务代码、不改容器节点标题。

**定位容器节点**：FEATURE 场景必然已存在（Intent 阶段已建），按 `Intent:` 前缀
读回全文——**写 Spec 前必须先读 Intent**。`STANDARD_BUG` 场景可能不存在，按
`[<task-id>]` 前缀查找，未命中 → 按 `intent.md` 3.2 节「未命中 → 新建容器节点」
的命令流程建（新建后正文贴完整任务链接），跳过读 Intent，直接依据已确认的
Root Cause。

**定位 Spec 文档**：按 `Spec:` 前缀查找，命中则 `docs +fetch` 读回增量修订；未
命中则新建：

```bash
lark-cli docs +create --as bot --title "Spec: <需求名称>" --doc-format markdown \
  --content @./draft.md --parent-token <容器节点token> --format json
```

整篇覆盖 / 小改的写回命令见 `intent.md` 3.2（本阶段只换 `<doc_token>`）。

FEATURE 场景没有容器节点 token → 停下报错，不按 task-id 猜。失败处理（缺
scope / `permission_denied` 两类报错区分与处置步骤）见 `artifact-config.md` 第
3 节；不改 user 身份绕过、API 报错如实报告。

## 3. 写作规则与模板

- 现状写可观察行为，不写代码内部实现；目标行为 FEATURE 场景须与 Intent 的
  Outcome 一致，`STANDARD_BUG` 对应 Root Cause 确认的正确行为。
- 范围：In scope 列本次覆盖的行为点；FEATURE 场景 Out of scope 承接 Intent 的
  Out of Scope，可细化不能反悔已排除的内容。
- FR 写业务规则本身，不写实现路径。反例「调用 X 接口查询余额」；正例「余额不足
  时禁止提交订单」。
- AC 用 Given/When/Then，**必须可测试**，禁止「优化体验」这类空话；至少一条
  覆盖本需求风险最高的边界（空/非法/幂等/并发/权限拒绝中选相关性最高的，不
  强求每个维度都有），不能只写 happy path。
- **Contract 是全文最不能含糊的一节**：接口/数据/状态机/权限/Error Code→前端
  行为必须逐条固定，禁止「其他错误统一提示」这类兜底话术；无变化写「无」，不
  省略。本节一旦漂移，实现阶段前后端就会各自猜测契约，返工成本远高于省下的
  篇幅。
- 影响与回滚：数据影响 / 兼容性 / 安全、影响文件（粗列）、回滚方式；FEATURE
  场景用 `get_impact_radius` / `get_affected_flows` 取证，判不出的写 Open
  Questions 不臆测。
- Open Questions：依据冲突项、现状与依据描述不符项、无法从依据/代码/Contract
  推断的技术决策，都写这里并标注，不自己拍板。产品/范围/业务规则类决策：
  FEATURE 场景走第 4 节讨论组的 `product-designer` 裁定，裁定结果直接落正
  文（附裁定依据），不进 Open Questions；`STANDARD_BUG` 场景没有讨论组，仍
  按老规则写 Open Questions 交需求人。
- 不写实现层细节（Controller/字段/接口路径/参数名）、不写 Task Graph/Owner 分
  工/验证命令——这些是 Plan 的职责；不超出 Intent 划定的范围；不发明产品规则。

`<名称>` 用需求主题，FEATURE 场景与 Intent 同名。

```markdown
# Spec: <名称>

> 只保留防止实现 Agent 猜测所需的锚点，不堆砌篇幅。不适用的小节一律写「无」
> （含 Contract）；唯一例外是「前端 / 后端行为」节——非 FULL_STACK 且无可观察
> 行为时可整节删除。

## 现状与目标
- **Current Behavior**：……
- **Expected Behavior**：……

## 范围
- In scope：……
- Out of scope：……

## 功能规则（FR）
- FR-01：……

## 验收标准（AC；Given / When / Then，可测试）
- AC-01：Given …… When …… Then ……
- AC-02：Given 订单已提交且余额不足 When 再次提交 Then 返回错误码且订单状态不变
  （边界：幂等 + 非法）

## 契约（Contract）
> 无变化写「无」。

- 接口 / 数据 / 状态机 / 权限：……
- Error Code → 前端行为：……

## 前端 / 后端行为
- Frontend Behavior：……
- Backend Behavior：……

## 错误与边界
- **Error Behavior**：能否重试、是否留脏数据；用户可见提示（错误码 → 前端行为
  的映射固定在契约一节，不在此重复）。
- **Boundary**：按业务选相关边界（空 / 0 / 上限 / 非法 / 重复 / 并发 / 权限拒绝）。

## 影响与回滚
- 数据影响 / 兼容性 / 安全：……
- 影响文件（粗列）/ 回滚：……

## Open Questions
- 无
```

## 4. FEATURE 场景：产品设计 + Author/Reviewer/Designer 讨论组

FEATURE 场景固定走一次产品设计分析 + 讨论组评审，防止单人写 Spec 时只顾机械
翻译 Intent、不做设计权衡，也防止自我确认偏差。

**角色与派发方式**：用 `TaskCreate` 给 `spec-author`/`spec-reviewer`/
`product-designer` 各建一条任务，再用 Agent 工具依次派成 named agent
（`name` 直接用角色名），同一 session 内三个 named agent 自动构成隐式团队——
组队机制同 `SKILL.md`「IMPLEMENT：单 Agent vs Agent Team」一节的 named agent
用法，但**目的不同**：那节是并行分工，这里是持续讨论——三者轮次内直接互相
`SendMessage`，不必每句话绕回主线程转达。角色职责固定在各自的 agent 定义文
件里，本节不重复：

- **`agents/product-designer.md`**：**Phase 0** 单次产出「产品设计决策点」
  brief 回喂主上下文，标出 Intent 未说清之处的候选方案与用户可感知差异；
  brief 里性质为「业务规则」的条目带**建议裁定**，只是参考起点，不是终局——
  Author 不得未经讨论组确认就直接把 brief 建议当正文定论。**Phase 1** 作为
  讨论组常驻成员随时被 `SendMessage` 唤入，对产品/范围类分歧（含业务规则、
  范围漂移）当场裁定，裁定为终局——不再送 Open Questions/需求人。未派或
  brief 产出为空都不阻塞后续流程，但一旦讨论组内出现产品/范围类分歧，必须
  唤入 designer 裁定，不能因为 Phase 0 没派、或 brief 已给建议就跳过唤入。
- **`agents/spec-author.md`**：吃 brief 当输入之一，起草全部 9 节初稿；讨论
  组内收到 Reviewer 直接发来的 blocking issue，据此修订；遇到需要裁定的业
  务规则/产品范围问题，直接 `SendMessage` designer，不自行采纳、不自行送
  Open Questions。
- **`agents/spec-reviewer.md`**：对抗式评审，起草稿完成后直接 `SendMessage`
  把 blocking issue 发给 Author，不经主线程转达；无 blocking issue = 通过；
  **不接收 product-designer 的 brief**，独立沿文件内写死的两张固定表重新审
  计 Spec 正文；若 blocking issue 是对已有 designer 裁定的异议，直接
  `SendMessage` designer 说明异议与证据。

**讨论组怎么走**：Round 1——Author 起草初稿，直接 SendMessage 给 Reviewer
审；Reviewer 把 blocking issue 直接 SendMessage 回 Author；涉及业务规则/产
品范围的问题，Author 或 Reviewer 直接 SendMessage designer 请其裁定，裁定
结果带回讨论组，Author 据此写入正文。Round 2——Author 修订后直接
SendMessage 通知 Reviewer 复核；Reviewer 直接回复是否解决。硬上限 2 轮，仅
计这段直接对话；designer 的裁定不计入轮次消耗，可随时被唤入。不设 Round
3——两轮内 Author↔Reviewer 的**技术正确性**分歧仍谈不拢的，连同双方主张与
证据一起交回主线程仲裁（见下）；产品/范围/业务规则类分歧不升级主线程，只能
升级给 designer 重新裁定。

**主线程角色收窄，但不退场**：不再逐句转发讨论组内部消息，也不再受理产品/
范围/业务规则类分歧（这两类改判权已下放给 designer，这正是本次改动的目
的）；但仍是**技术正确性分歧**的唯一仲裁者、以及 Spec 正文的唯一执笔人（整
合不外包，见下）。

**分歧仲裁**（按分歧类型分流，Reviewer/Author 均无自行裁决权）：

- 技术正确性争议（能被工具证据查证）→ 主线程。裁决前必须先逐字复述原始
  blocking issue，确认证据恰好回答这句话——防止 Author 把原始争议偷换成一
  个更窄、能被证据回答的问题来假装已裁决。
- 产品/范围取舍（含范围漂移、业务规则）→ `product-designer`。designer 裁
  定为终局，不再送需求人；裁定必须落在 Intent 已给的边界内，且给出依据
  （Intent 原句 / file:line），不能只给结论。
- **验收 Author 修订同一纪律**：不能因「看起来改多了」就签收，必须逐字核对
  修订文字是否精确覆盖原始 issue（技术类）或裁定内容（产品/范围类），仍含
  糊则退回重改。

**整合不外包**：最终 Spec 正文必须由主线程/调用方自己写，不能由讨论组三者
中任何一个代写正文——出问题要能追溯到当时依据哪条证据做的判断，不能指向一
个黑箱。这条约束管的是「谁执笔」，不是「谁决策」：产品/范围/业务规则类内容
的决策权已明确交给 designer，主线程执笔时照录 designer 的裁定与理由，不重
新评议裁定本身的对错；讨论组内部的往来消息本身不是证据，执笔时仍要能指到
Spec 正文/Intent 原文/代码证据/designer 裁定记录，不能以「聊出了共识」作为
落笔依据。

## 5. 收尾

Spec 定稿后**不单独停下**——继续读 `plan.md` 产出 Plan，两者一起在 Gate B 呈现
给需求人（Gate 机制见 `SKILL.md`）。批准后审批人戳记写进本篇 Spec，见
`gate-approval.md` 第 3 节。
