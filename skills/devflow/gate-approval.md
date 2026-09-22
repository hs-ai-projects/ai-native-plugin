# Gate 审批人记录

Gate A / Gate B 通过时，把「谁批的」写进对应文档，不能只留在对话里——具体见
`skills/devflow/intent.md` 第 9 节、`skills/devflow/plan.md` 第 8 节。

## 1. 拿 open_id / 姓名

cc-connect 开了 `inject_sender` 时，飞书用户发来的消息会被自动加前缀：

```
[cc-connect sender_id=ou_xxx sender_name="张三" platform=feishu chat_id=oc_xxx]
<用户原话>
```

批准 Gate 那条消息带这个前缀 → 直接取 `sender_id` / `sender_name`。

- 前缀缺失（未开 `inject_sender`，或非飞书会话/本地终端）→ 拿不到 open_id，
  只记文字姓名或干脆写「审批人：<对话中确认的姓名，未采集 open_id>」，不编造、
  不静默留空。
- `sender_id` 是 `ou_` 开头才能用于下面的 `<cite>` 标签；不是这个格式（如本地
  终端场景没有该字段）→ 只写姓名，不硬套 `<cite>`。

## 2. 写进文档：飞书文档 @人用 `<cite>`，不是 `<at>`

**不要混用**：聊天回复里 @人用 `<at user_id="...">名字</at>`（见
`rules/feishu-group-collab.md`），那是消息层语法；写进 docx 正文用
`<cite type="user" user-id="ou_xxx"/>`，这是文档层语法，两者标签名和属性名都不同。

在 Gate 收尾段落追加一行（`docs +update --command block_insert_after` 或
`str_replace`，不要 `overwrite` 整篇）：

```
审批人：<cite type="user" user-id="ou_xxx"/> · 2026-09-21
```

只有 `sender_id` 时才用 `<cite>`；只有姓名时纯文字写「审批人：张三（口头确认，未采集 open_id）」。

## 3. Gate B 覆盖 Spec+Plan 两篇文档，都要写

Gate B 一次批准同时定稿 Spec 和 Plan——审批人戳记**两篇都写**，同一行内容、同
一个 `sender_id`/时间，各自追加到自己文档的收尾段落。只写 Plan 会导致单独打开
Spec 文档时看不出它已经过审批，审计链路不完整。
