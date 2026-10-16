# 产物后端配置：飞书知识库

规定 devflow 产物（intent / spec / plan）存到哪、怎么初始化、落盘模型。
具体的文档读写命令（定位文档、新建、改章节）按阶段分散在
`skills/devflow/intent.md`（Intent）、`spec.md`（Spec）、`plan.md`（Plan），不在此重复。

## 身份：全程用应用身份，不需要 user 授权

初始化和落盘的所有操作——解析父节点、建容器节点、建三篇文档、读写内容、回写任务字段——
**一律 `--as bot`**。不要发起 user 授权流程，本流程用不上。

前提是飞书侧配好两件事，缺哪件都在对应步骤报错、找用户处理：

1. 应用在开发者后台申请了对应的 **app scope**（见第 3 步）
2. 应用被加为该**知识空间的成员**（见第 4 步）

两件都是用户侧的一次性配置，配完不用再管。

## 产物落在哪

一个需求 = 飞书知识库里的**一个容器节点 + 3 篇独立文档**，容器节点挂在用户指定的父节点下：

```
知识空间
└── <用户选定的父节点>
      └── [<task-id>] <需求名称>          ← 容器节点
            ├── Intent: <名称>             ← 独立文档
            ├── Spec: <名称>               ← 独立文档
            └── Plan: <名称>               ← 独立文档
```

- 容器节点本身也是一篇 docx——飞书 wiki 没有纯目录节点类型，只当挂载点用。
  **有飞书任务链接时**，正文贴完整任务链接（方便从飞书任务反查容器节点）；
  口述需求没有链接可贴，正文不写内容。
- 三篇文档按阶段各自新建：`intent.md` 建容器 + Intent；Gate A 通过后（或 DISCOVER
  判定 `STANDARD_BUG` 后）`spec.md` 在容器下建 Spec；`plan.md` 建 Plan。不再一次性
  建三篇占位。`STANDARD_BUG` 场景可能没有 Intent 文档，容器节点下只有 Spec+Plan，
  这是正常状态。
- **本地不保留副本**，飞书文档是唯一 Source of Truth。
- task-id：带任务链接时取链接 guid；口述需求用 `<YYYY-MM-DD>-<短slug>`。**容器节点**标题带 `[<task-id>]` 前缀；三篇子文档标题不带前缀（容器已承担定位职责），直接 `Intent: <名称>` / `Spec: <名称>` / `Plan: <名称>`。
- 父节点下已有同 task-id 前缀的容器节点 → 续做，不要新建第二个容器。

### 两条等价的建文档路径

| 路径 | 实际 API | 需要的 app scope | URL 形态 |
|---|---|---|---|
| `docs +create --parent-token <容器 node_token>` | `POST /open-apis/docs_ai/v1/documents` | docx 域：`docx:document`、`docx:document:create` | `/docx/xxx` |
| `wiki +node-create --obj-type docx --parent-node-token <容器 node_token>` | `POST /open-apis/wiki/v2/spaces/{space_id}/nodes` | wiki 域：`wiki:wiki`、`wiki:node:create` | `/wiki/xxx` |

`docs +create` 被 scope 卡住时不要停——改走 `wiki +node-create` 建节点、再用
`docs +update` 写内容，效果等价。`docs +update` / `docs +fetch` 不需要 `docx:document:create`。

## 配置

路径：`~/.ai-native/config.json`

```json
{
  "artifact_backend": "feishu-wiki",
  "parent_node_token": "wikcn...",
  "parent_url": "https://<域>.feishu.cn/wiki/wikcn...",
  "space_id": "7123...",
  "bot_app_id": "cli_...",
  "initialized_at": "2026-09-19T12:00:00+08:00"
}
```

文件不存在，或 `artifact_backend` 不是 `feishu-wiki` → **未初始化**，写第一份产物前必须先走下面的初始化。

## 初始化（首次必做，必须人工参与）

初始化总共向用户要 **1 个输入**（节点 URL）和 **最多 1 次后台操作**（申请 app scope）。
尽量压缩成一次沟通，不要来回挤牙膏。

### 1. 问用户存到哪个节点

把这句话原样问出去，不要自行猜测目标：

> 产物要落到飞书知识库。请给我一个用于存放产物的**知识库节点 URL**
> （形如 `https://xxx.feishu.cn/wiki/wikcnXXXX`）。每个需求会在它下面建一个容器节点。

用户可以给知识空间 URL，也可以给空间内任意一个节点 URL——该节点即成为所有需求文档的父节点。

### 2. 解析父节点

```bash
lark-cli wiki +node-get --as bot --node-token "<用户给的URL>" --format json
```

返回里取 `data.space_id` 和 `data.node_token`，分别作为后续的 `--space-id` 和 `--parent-node-token`。

报错按类型处理：

- `app_scope_not_applied` → 见第 3 步
- `not_found` / `permission_denied` → 把原始报错告诉用户，让用户换一个 URL 或补权限；**不要**自行改 URL 重试
- `rate_limit` → 退避重试

### 3. 处理权限报错

两类报错处置完全不同，认错类型会白忙一轮：

| 子类型 | code | 含义 | 处置 |
|---|---|---|---|
| `app_scope_not_applied` | 99991672 | **应用本身**没在开发者后台申请该权限 | 用户去后台开，没有别的绕法 |
| `permission_denied` | 131006 | 有应用权限，但应用不是该资源/空间的成员 | 把应用加进知识空间（第 4 步） |

初始化涉及的 app scope 分属两个域，飞书**不会一次报全**，是走到哪报到哪：

| 用途 | 需要的 scope |
|---|---|
| 解析父节点（读） | `wiki:node:retrieve` |
| 建容器节点 / 三篇文档 | `wiki:wiki`、`wiki:node:create` |
| 走 `docs +create` 标准路建文档 | `docx:document`、`docx:document:create` |

被 `app_scope_not_applied` 挡住时，一次性把上表剩下的都让用户开了，别开一轮试一轮。
报错体里直接带 `console_url`，把这一整行原样给用户最快：

```
https://open.feishu.cn/page/scope-apply?clientID=<app_id>&scopes=<urlencoded scopes>
```

### 4. 把应用加进知识空间

**不要用 `wiki +node-list` 判断应用是否在空间内。** 应用不在空间时它返回
`{"ok": true, "data": {"has_more": false, "nodes": []}}`——不报错、纯空列表；
而目标节点本来就没有子节点时，返回一模一样，两种情况无法区分。

判定方式是**直接试建一次容器节点**：

```bash
lark-cli wiki +node-create --as bot --obj-type docx \
  --title "[<task-id>] <需求名称>" --parent-node-token <parent_node_token> --format json
```

- 返回 `node_token` / `obj_token` / `url` → 应用已就位，容器节点同时建好，不用再单独探一次
- 报 `permission_denied`（131006）→ 应用还没进空间，让用户在飞书侧加：

  知识空间「设置 → 成员管理 → 添加成员 → 应用」，搜应用名或 app id
  （`lark-cli auth status` 的 `appId`），加为**可编辑**。

  跟用户说明清楚：Intent / Spec / Plan 三篇文档都靠这个应用写，加一次以后不用再管。

  加完重跑试建验证，通过才继续。**不要**跳过验证直接往下走。

### 5. 写配置并回报

写入 `config.json`，向用户回报：父节点名称、URL、应用已就位、后续每个需求会在此新建容器节点。等用户确认。
配置里记下 `bot_app_id`，后续排查「文档用户看不到」时要用。

### 6. 让用户确认能打开文档

应用建文档时不会自动把 `full_access` 授给任何人，返回体里 `permission_grant.status` 会是 `skipped`。
这意味着用户不一定打得开你建的文档，取决于知识空间自身的权限设置。

所以每轮交付产物后，**主动让用户点一下链接确认能打开**；打不开就在知识空间里给对应用户或群组加权限。

## 读写操作的权限边界

| 操作 | 命令 | 说明 |
|---|---|---|
| 读节点元信息 | `wiki +node-get --as bot` | 需 `wiki:node:retrieve` |
| 建节点 | `wiki +node-create --as bot --obj-type docx` | 需 `wiki:wiki`、`wiki:node:create`，且应用在空间内 |
| 建独立文档 | `docs +create --parent-token <node_token>` | 需 `docx:document:create`；缺则走 `wiki +node-create` |
| 覆盖写内容 | `docs +update --command overwrite --content @file` | 不需要 `docx:document:create` |
| 读回内容 | `docs +fetch --doc <obj_token>` | — |

- `docs +update` 首次覆盖一个新建的空文档，可能返回 `result: "partial_success"` 加
  warning `degrade_code=1011, msg=Instruction produced no document changes`，`revision_id` 不变。
  **这不是"内容已存在"**——把同一条命令原样重跑一次就成功了。遇到 1011 先重试，别去改内容。
- `--parent-token` / `--parent-node-token` 传容器节点的 `node_token`（不是 `obj_token`）；
  `--doc` 传文档的 `obj_token`。返回体里两个都有，别拿错。
