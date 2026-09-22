# Intent Writer

现在做需求定义，不做实现。把模糊需求收敛成一份可审批、不含实现细节的 Intent 文档。
回答「为什么做」，不回答「怎么做」。

何时读本文件：见 `skills/devflow/SKILL.md`「阶段·产物·分工」表。

## 1. 信息优先级

1. 需求人本轮明确表达的原话
2. 已有 Intent 文档（续做场景）
3. 项目 CLAUDE.md 与现有开发规范
4. 现有代码行为与业务规则
5. 代码库中的类似实现

存在冲突：不自行选，写进「待澄清问题」并标注冲突点。

## 2. 先回写任务状态

**产出任何产物之前**，先把飞书任务 `状态` 从 `待评审` 改成 `Intenting`：

```bash
lark-cli task tasks get --task-guid <guid> --as bot --format json
lark-cli task tasks patch --task-guid <guid> --as bot \
  --data '{"task":{"custom_fields":[{"guid":"<状态字段guid>","single_select_value":"<Intenting选项guid>"}]},"update_fields":["custom_fields"]}'
```

- 字段/选项 GUID 按 `name` 匹配，**禁止硬编码**；第一次解析后写进记忆复用。
- **幂等**：已是 `Intenting`（如 Gate A 打回重跑）→ 跳过，不报错、不改成别的值。
- 只改 `状态` 这一个字段。没有 task-guid（口述需求）→ 跳过本步，不是错误。
- 回写失败不阻断产出：如实说明，继续写 Intent。

## 3. 产物落盘

产物落**飞书知识库**：容器节点下的 Intent 文档。本地不留副本，草稿写 `/tmp`。

- 未初始化（`~/.ai-native/config.json` 缺失或 `artifact_backend` 不对）→ 先走
  `skills/devflow/artifact-config.md` 初始化，**必须问用户**存哪，不自行挑知识空间。
- 只写 Intent，不碰 Spec / Plan，不改业务代码。

### 3.1 身份

**统一 `--as bot`**：token 不过期，bot 建的文档用户也能直接看到并编辑；前提是
bot 已在知识空间（`artifact-config.md` 初始化第 4 步），否则建不了容器节点/子文档。

### 3.2 定位或新建容器节点 + Intent 文档

按 `[<task-id>]` 前缀在全局父节点下查找容器节点：

- **命中** → 续做。找容器节点下 `Intent:` 开头的文档，命中则 `docs +fetch` 读回
  增量修订；没有则新建（走下面新建流程）。
- **未命中** → 新建容器节点：

  ```bash
  lark-cli wiki +node-create --as bot --obj-type docx \
    --title "[<task-id>] <需求名称>" --parent-node-token <parent_node_token> --format json
  ```

  飞书 wiki 没有纯目录节点类型，容器节点本身也是一篇空 docx，只当挂载点用——
  **有飞书任务链接时**，正文贴完整链接（方便反查）：

  ```bash
  lark-cli docs +update --as bot --doc <容器节点token> \
    --command overwrite --doc-format markdown \
    --content "https://applink.feishu.cn/client/todo/detail?guid=<task_id>"
  ```

  没有链接（口述需求）→ 跳过本条。再建 Intent 文档：

  ```bash
  lark-cli docs +create --as bot --title "Intent: <需求名称>" --doc-format markdown \
    --content @./draft.md --parent-token <容器节点token> --format json
  ```

返回的容器节点 token 与 Intent 文档 token/URL **只在本次会话内传递**，不落本地
文件。不在这一步建 Spec / Plan 占位——那由 `spec.md` / `plan.md` 各自新建。

续做时整篇覆盖即可：

```bash
lark-cli docs +update --as bot --doc <doc_token> \
  --command overwrite --doc-format markdown --content @./section.md
```

小改可用 `--command str_replace --pattern "<原文>"`，不强制。

**失败处理**：缺 scope → 走 `artifact-config.md` 授权流程，不静默降级到本地文件；
`permission_denied` → 先查 bot 是否还在知识空间里，不改 user 身份绕过；API 报错
如实报告，不假装写入成功。

### 3.3 回帖到任务

Intent 文档**新建**完成后，若有飞书任务链接（task-id 来自任务 guid），把文档 URL
回帖到任务，方便协作者从任务直接跳转：

```bash
lark-cli task +comment --task-id <task_id> --as bot --content "Intent 文档：<intent_doc_url>"
```

- 口述需求（无对应任务）→ 跳过，不是错误。
- 只在**新建**时回帖一次；续做覆盖同一篇文档时链接不变，不重复回帖。
- 回帖失败不阻断产出：如实说明，继续往下走，不假装已回帖。

## 4. 写之前必须调研

禁止只读一两个文件就下笔。至少弄清楚：用户现有的绕行方案、需求指向的实现是否
存在、是否与现有业务规则冲突、影响面涉及哪些模块/角色、能否复用现有功能。
调研结论只用于判断范围，不写进 Intent 文档。

## 5. 需求澄清

识别模糊词、隐含前提、未说明的状态/错误处理/权限/边界/兼容性。

- 能靠代码、规范、已有 Pattern 可靠确定的 → 直接定，不写进待澄清问题。
- 无法可靠推断、且属于产品决策的 → 直接问需求人，或写进「待澄清问题」留给 Gate A。
- 不允许把「我不确定」包装成「假设 X 成立」写死在正文里。

每条待澄清问题必须**可一句话回答**，禁止空话；阻塞定稿的标 `BLOCKING`。

## 6. 模板（产物必须严格按此结构，一字不改）

`<名称>` 用需求主题，不用 task-id；容器节点标题 `[<task-id>] <名称>` 是另一层。

```markdown
# Intent: <名称>

- **要解决什么**（Problem）：
- **为什么现在做**（Why）：
- **预期结果**（Outcome）：
- **影响谁 / 影响什么系统**：
- **约束 & 明确不做**（Out of Scope）：
- **怎么算完成**（可验证，Success Metrics）：
- **待澄清问题**：
```

## 7. 填写要点

- **Problem**：业务/用户视角的真实痛点，不写技术现象。反例「接口返回 500」；
  正例「用户在支付回调延迟时看到订单卡在待支付，会重复下单」。原始任务里如果有
  图片或其他资源链接且和需求相关，可以贴进本段作为佐证。
- **Why**：给出触发时机——业务节点、用户量、故障频率、合规要求。禁止「因为用户提了」。
- **Outcome**：外部可观察的变化，不写「实现 X 功能」。
- **影响谁/系统**：角色+系统，确定的写具体，不确定标「待确认」。
- **Out of Scope**：写出**被主动排除的相邻需求**——本文件最有价值的一段，空着等于没定范围。
- **Success Metrics**：必须可验证。禁止「体验更好」「确保稳定」这类空话。
- **待澄清问题**：见第 5 节，无则写「无」。

## 8. 禁止事项

- 禁止写实现层（Controller/字段/接口路径/参数名）、验收标准正文、技术方案/库选型。
- 禁止发明产品规则、禁止把待澄清问题自行拍板后删掉。
- 禁止扩写需求人没提的相邻功能。
- 禁止改业务代码、碰 Spec / Plan 文档、改容器节点标题。
- 禁止在未初始化时自行挑知识空间，或把产物改写到本地文件。
- 禁止改飞书任务除 `状态` 外的任何字段；`状态` 只许做 `待评审 → Intenting` 这一跃迁。

## 9. 收尾：Gate A

定稿后**停下**，给 Intent 文档 URL + Problem/Outcome/Out of Scope/待澄清问题，
标注哪些是 `BLOCKING`，一并问出去。**禁止自行批准、自行续跑**——批准后才进入
SPEC；打回则按反馈修订后重新提交。批准后把状态推到 `待开发`（见
`skills/devflow/state-transitions.md`），并把审批人记进 Intent 文档（见
`skills/devflow/gate-approval.md`）。
