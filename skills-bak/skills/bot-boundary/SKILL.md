---
name: bot-boundary
description: >
  飞书群里"被另一个bot @"场景的行为边界。仅在触发消息的sender是另一个bot
  身份时生效，与人类用户直接@机器人的场景完全区分——人类@机器人时走正常的
  devflow-start-task/devflow-fix-bug自动路由，不受本skill约束。
---

# Bot Boundary

## 触发条件

飞书群消息的 sender 是另一个 bot 身份（而非人类用户）。这是本skill生效的
唯一前提——**人类用户@机器人的场景不受本skill任何规则约束**，那部分走
`devflow-start-task`/`devflow-fix-bug` 现有的自动路由逻辑，完全不变。

## 三分支路由

收到bot消息后，先判断消息内容命中哪种前缀：

1. **消息带 `[cc-task <id>][contract <M.m>]` 前缀** → 这是机器人对齐协议消息，
   用 `${CLAUDE_PLUGIN_ROOT}/scripts/collab/partner.py` 的 `parse_collab_message`
   解析，按对齐协议处理（确认/拒绝/漂移重确认，见spec 5.1）。

2. **消息带 `[cc-task <id>][handoff]` 前缀** → 这是机器人任务交接协议消息，
   用 `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py` 的 `parse_handoff_message`
   解析，按交接协议处理（接收方走自己完整的devflow-start-task判断，见spec 5.2）。

3. **消息不带任何已知前缀** → **只输出分析性回复，不执行任何写操作**：
   不改代码、不建sandbox、不建MR、不merge、不touch任何 `.ai-devflow/` 产物。
   这条规则的目的是避免机器人之间的闲聊式@（比如另一个bot只是提了一句
   "你那边最近还好吗"）意外触发完整的devflow流程。

## 为什么需要这条边界

带前缀的消息（分支1/2）已经在各自协议里定义好该做什么，本skill不重复定义
它们的处理逻辑，只负责"分发到哪个协议"。分支3才是本skill真正新增的约束——
没有这条边界，bot收到另一个bot发来的任意消息都会按正常的"被@了"逻辑走
自动路由，可能对一句无意义的寒暄发起完整需求处理流程。

## 不做的事

- 不判断"这个bot身份是否可信"——只要sender是bot身份就适用本skill的三分支
  路由，不做额外的白名单/黑名单校验（那是另一个层面的安全问题，不在本skill
  范围）。
- 不缓存"之前跟这个bot聊过什么"——每条消息独立判断前缀，不依赖会话历史推断
  意图。
