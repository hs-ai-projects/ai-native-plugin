# Spec Writer

现在做验收标准定义，不做实现方案（Plan 是下一步）。把已批准的 Intent（FEATURE）
或已确认的 Root Cause（`STANDARD_BUG`）收敛成一份可测试、防止实现 Agent 猜测契约
的 Spec 文档。回答「什么叫正确」，不回答「代码怎么写」。

何时读本文件：见 `skills/devflow/SKILL.md`「阶段·产物·分工」表。FEATURE 场景带
容器节点 token/URL；`STANDARD_BUG` 场景容器节点可能不存在，需先新建（见第 2 节）。

## 1. 信息优先级

1. FEATURE：已批准的 Intent（边界不能突破）；`STANDARD_BUG`：已确认的 Root Cause 与复现路径
2. 已有 Spec 文档（续做场景）
3. 已有 API / Domain Contract
4. 项目 CLAUDE.md 与现有开发规范
5. 现有代码行为

存在冲突：不自行选，写进 Open Questions 并标注冲突点。

## 2. 产物落盘

产物落**飞书知识库**：容器节点下的 Spec 文档。本地不留副本，草稿写 `/tmp`。

- 未初始化 → 先走 `skills/devflow/artifact-config.md` 初始化。FEATURE 场景理论上
  Intent 阶段已做过，这里是兜底；`STANDARD_BUG` 可能是首次接触产物后端，未初始化
  必须先问用户。
- 只写 Spec，不碰 Intent / Plan，不改业务代码。
- 身份统一 `--as bot`，理由见 `skills/devflow/intent.md` 3.1 节。

**定位或新建**：

- **FEATURE**：容器节点必然已存在（Intent 阶段已建），按 `Intent:` 前缀读回全文——
  **写 Spec 前必须先读 Intent**（见第 3 节）。
- **`STANDARD_BUG`**：容器节点可能不存在，按 `[<task-id>]` 前缀查找，未命中则新建：

  ```bash
  lark-cli wiki +node-create --as bot --obj-type docx \
    --title "[<task-id>] <需求名称>" --parent-node-token <全局父节点token> --format json
  ```

  新建后正文贴完整任务链接（规则见 `intent.md` 3.2 节）。该场景没有 Intent 文档，
  跳过读 Intent，直接依据已确认的 Root Cause。

再按 `Spec:` 前缀找 Spec 文档：命中则 `docs +fetch` 读回增量修订；未命中则新建：

```bash
lark-cli docs +create --as bot --title "Spec: <需求名称>" --doc-format markdown \
  --content @./draft.md --parent-token <容器节点token> --format json
```

写入整篇覆盖：`lark-cli docs +update --as bot --doc <doc_token> --command overwrite --doc-format markdown --content @./section.md`（小改可用 `--command str_replace`）。

FEATURE 场景没有容器节点 token → 停下报错，不自行按 task-id 猜测。

**失败处理**：缺 scope → 走 `artifact-config.md` 授权流程；`permission_denied` →
先查 bot 是否还在知识空间里，不改 user 身份绕过；API 报错如实报告。

## 3. 写之前必须核对上游依据

禁止脱离依据写 Spec：

- **FEATURE**：Intent 的 Outcome、Out of Scope 是否已框定边界，不能超出；仍
  `BLOCKING` 的待澄清问题不能自行拍板。
- **`STANDARD_BUG`**：Root Cause 是否已确认（不是猜测），复现路径是否明确。
- 涉及已有 API / Contract 时，现有实现是否与依据描述的现状一致。

核对结论只用于判断是否偷偷扩大范围，不写进 Spec 正文。

## 4. Spec 写作规则

- **现状与目标**：现状写可观察行为，不写代码内部实现；目标行为 FEATURE 场景须与
  Intent 的 Outcome 一致，`STANDARD_BUG` 对应 Root Cause 确认的正确行为。
- **范围**：In scope 列本次覆盖的行为点；FEATURE 场景 Out of scope 承接 Intent
  的 Out of Scope，可细化但不能反悔已排除的内容。
- **功能规则（FR）**：业务规则本身，不描述实现路径。反例「调用 X 接口查询余额」；
  正例「余额不足时禁止提交订单」。
- **验收标准（AC）**：Given/When/Then，**必须可测试**。禁止「优化体验」这类空话，
  每条覆盖至少一种边界（空/非法/幂等/并发），不能只写 happy path。
- **契约（Contract）**：前后端共用的接口、数据结构、状态机、权限、Error Code →
  前端行为必须固定，**禁止让实现方各自猜测**——本节最容易漂移，宁可详细不要含糊。
  无变化写「无」，不要省略。
- **前端/后端行为**：FULL_STACK 或涉及可观察行为时必填，否则删掉不留空。
- **错误与边界**：错误码 → 用户可见行为、能否重试、是否留脏数据；按业务选相关边界。
- **影响与回滚**：数据/兼容性/安全影响，无则写「无」。
- **Open Questions**：无法从依据/代码/Contract 推断的产品或技术决策，写这里不自己拍板。

## 5. 模板（产物必须严格按此结构，一字不改）

`<名称>` 用需求主题，FEATURE 场景与 Intent 同名。

```markdown
# Spec: <名称>

> 只保留防止实现 Agent 猜测所需的锚点，不堆砌篇幅。不适用的小节写「无」或删除。

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
- AC-02：（含边界：空 / 非法 / 幂等 / 并发）

## 契约（Contract）
> 前后端或外部依赖共用的契约必须在此固定，禁止实现方各自猜测。无变化写「无」。

- 接口 / 数据 / 状态 / 权限：……
- Error Code → 前端行为：……

## 前端 / 后端行为（FULL_STACK 或涉及可观察行为时必填，否则删）
- Frontend Behavior：……
- Backend Behavior：……

## 错误与边界
- **Error Behavior**：错误码 → 用户可见行为；能否重试、是否留脏数据。
- **Boundary**：按业务选相关边界（空 / 0 / 上限 / 非法 / 重复 / 并发 / 权限拒绝）。

## 影响与回滚
- 数据影响 / 兼容性 / 安全：……（无则写「无」）
- 影响文件（粗列）/ 回滚：……

## Open Questions
- 无
```

## 6. 禁止事项

- 禁止写实现层（Controller/字段/接口路径/参数名）——那是 Plan 展开的细节。
- 禁止写 Task Graph、Owner 分工、验证命令——那是 Plan 的职责。
- 禁止超出 Intent 划定的范围；禁止把 AC 写成不可测试的空话。
- 禁止发明产品规则；无法推断的写进 Open Questions。
- 禁止改业务代码、碰 Intent / Plan 文档、改容器节点标题。
- 禁止在未初始化时自行挑知识空间，或把产物改写到本地文件。
- 禁止在容器节点下已有 Spec 文档时再新建第二篇。

## 7. 收尾

Spec 定稿后**不单独停下**——继续读 `plan.md` 产出 Plan，两者一起在 Gate B 呈现给
需求人。FEATURE 与 `STANDARD_BUG` 场景都过 Gate B，没有特例。
**禁止自行批准 Gate B、禁止自行进入 IMPLEMENT**。
