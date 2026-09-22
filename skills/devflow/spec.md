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
  推断的产品或技术决策，都写这里并标注，不自己拍板。
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

## 4. FEATURE 场景：产品设计 + Author/Reviewer 对抗式评审

FEATURE 场景固定走一次产品设计分析 + 对抗式评审，防止单人写 Spec 时只顾机械
翻译 Intent、不做设计权衡，也防止自我确认偏差。

**角色**：3 个（1 个前置产出 + 2 个对抗），不按 Spec 章节分工。启动方式：用
Agent 工具依次派 named agent，写法见 `SKILL.md`「IMPLEMENT：单 Agent vs Agent
Team」一节。角色职责固定在各自的 agent 定义文件里，本节不重复：

- **`agents/product-designer.md`**：先跑，产出「产品设计决策点」brief（不落
  盘，回喂主上下文），标出 Intent 未说清之处的候选方案与用户可感知差异。不
  参与对抗轮次，不重置轮次预算，未派或产出为空都不阻塞后续流程。
- **`agents/spec-author.md`**：吃 brief 当输入之一，起草全部 9 节初稿。
- **`agents/spec-reviewer.md`**：对抗式评审，只输出 blocking issue 列表；无
  blocking issue = 通过；**不接收 product-designer 的 brief**，独立沿文件内
  写死的两张固定表重新审计 Spec 正文。

**轮次**：硬上限 2 轮，仅计 Author↔Reviewer 的对抗轮次；`product-designer`
的前置产出不计入。Round 1 初稿+挑刺，Round 2 只复核 blocking issue 是否真解
决，不设 Round 3。

**分歧仲裁**（裁决权在主线程，不在 Reviewer）：
- 技术正确性争议（能被工具证据查证）：主线程裁决前必须先逐字复述原始
  blocking issue，确认证据恰好回答这句话——防止 Author 把原始争议偷换成一个
  更窄、能被证据回答的问题来假装已裁决。
- 产品/范围取舍（含范围漂移）：Reviewer 无权自行判断「可接受」就放行，无条
  件写入 Open Questions 交需求人决策。
- **验收 Author 修订同一纪律**：不能因「看起来改多了」就签收，必须逐字核对
  修订文字是否精确覆盖原始 issue，仍含糊则退回重改。

**整合不外包**：最终 Spec 正文必须由主线程/调用方自己写，不能由三者中任何
一个代写或裁决正文——出问题要能追溯到主线程当时依据哪条证据做的判断，不能
指向一个黑箱。

## 5. 收尾

Spec 定稿后**不单独停下**——继续读 `plan.md` 产出 Plan，两者一起在 Gate B 呈现
给需求人（Gate 机制见 `SKILL.md`）。批准后审批人戳记写进本篇 Spec，见
`gate-approval.md` 第 3 节。
