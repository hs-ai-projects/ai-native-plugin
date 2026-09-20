# 产物后端配置：飞书知识库

规定 devflow 产物（intent / spec / plan）存到哪、怎么初始化、落盘模型。
具体的文档读写操作命令（定位文档、新建、改章节）按阶段分散在
`skills/devflow/intent.md`（Intent）、`skills/devflow/spec.md`（Spec）、
`skills/devflow/plan.md`（Plan），不在此重复。

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
- 模板、写作规则、写入命令：内嵌在对应文件自身——`skills/devflow/intent.md` /
  `spec.md` / `plan.md`（按阶段各管各的）。

## 配置

路径：`~/.ai-native/config.json`

```json
{
  "artifact_backend": "feishu-wiki",
  "parent_node_token": "wikcn...",
  "parent_url": "https://<域>.feishu.cn/wiki/wikcn...",
  "space_id": "7123...",
  "initialized_at": "2026-09-19T12:00:00+08:00"
}
```

文件不存在，或 `artifact_backend` 不是 `feishu-wiki` → **未初始化**，写第一份产物前必须先走下面的初始化。

## 初始化（首次必做，必须人工参与）

### 1. 问用户存到哪个节点

把这句话原样问出去，不要自行猜测目标：

> 产物要落到飞书知识库。请给我一个用于存放产物的**知识库节点 URL**
> （形如 `https://xxx.feishu.cn/wiki/wikcnXXXX`）。每个需求会在它下面建一个容器节点。

用户可以给知识空间 URL，也可以给空间内任意一个节点 URL——该节点即成为所有需求文档的父节点。

### 2. 解析 space_id（`--as user`）

```bash
lark-cli wiki +node-get --as user --node-token "<用户给的URL>" --format json
```

从返回取 `data.space_id` 与 `data.node_token`。报错按类型处理：

- `missing_scope` → 走第 3 步补授权，补完重跑本步。
- `not_found` / `permission_denied` → 把原始报错告诉用户，让用户换一个 URL 或补权限；**不要**自行改 URL 重试。
- `rate_limit` → 退避重试。

### 3. 按需补 user scope

只在第 2 步或第 4 步报 `missing_scope` 时才授权，不要预先一次性要全。可能缺：

| scope                | 用途                                       |
| -------------------- | ------------------------------------------ |
| `wiki:node:retrieve` | 解析父节点、校验 bot 可见性                |
| `wiki:member:create` | 把 bot 应用加进知识空间（第 4 步自动路线） |

```bash
lark-cli auth login --scope "<缺的scope>" --no-wait --json
```

拿到 `device_code` 和 `verification_url` 后，**把 verification_url 原样给用户并结束本轮**，等用户确认授权后再：

```bash
lark-cli auth login --device-code <device_code>
```

### 4. 让 bot 进入知识空间

bot 必须在目标知识空间里，否则无法在该父节点下建容器节点。先用 bot 身份探一次：

```bash
lark-cli wiki +node-list --as bot --space-id <space_id> \
  --parent-node-token <parent_node_token> --page-all --format json
```

- **通过** → bot 已在空间内，跳到第 5 步。
- **`permission_denied` / 空结果** → bot 还没进空间，给用户两条路，让用户选：
  - **自动**（需补 `wiki:member:create`，走第 3 步授权后执行）：
    ```bash
    lark-cli wiki +member-add --as user --space-id <space_id> \
      --member-type appid --member-id <bot app_id> --member-role member
    ```
    bot app_id 从 `lark-cli auth status` 的 `appId` 取。
  - **手动**：让用户在飞书知识空间「设置 → 成员管理 → 添加成员 → 应用」里加上该应用，加完回报。

    加完重跑本条 `+node-list` 验证，通过才继续。**不要**跳过验证直接往下走。

### 5. 写配置并回报

写入 `config.json`，然后向用户回报：父节点名称、URL、bot 已就位、后续每个需求会在此新建容器节点。等用户确认。

配置里记下 bot app_id，后续排查「文档用户看不到」时要用：

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

### 禁止

- 禁止在用户未明确指定节点时自行 `wiki +node-create` 或 `wiki +space-create`。
- 禁止把仓库名 / 项目名当作父节点名去搜索。
- 禁止猜 token、禁止把知识空间名称直接当 `--space-id`。bot 身份**不支持** `--space-id my_library`，必须显式给 `--space-id` 或 `--parent-node-token`。
- 禁止在初始化未完成时把产物静默写到本地文件——那是绕过用户决策，不是降级。

## 待实测（首次真实初始化后回填本节）

- [x] bot 在未加入知识空间时，`wiki +node-list --as bot` 到底报 `permission_denied` 还是返回空列表。
      实测（2026-09-19）：返回空列表（`nodes: []`），**不报错**。但目标节点本身 `has_child: false`，
      空列表无法区分「bot 没权限」和「节点确实没有子节点」——`node-list` 不能当判定依据。
      真正能判定的是试建文档：`docs +create --as bot` 直接报 `permission_denied`
      （code 3380004: you do not have permission to create the document under the target wiki node）。
      **结论**：第 4 步判定 bot 是否已在空间内，应该用「试建一个探测文档」而不是 `node-list` 空结果，
      或者用其他专门查空间成员的接口，`node-list` 返回空不能当作「未加入空间」的信号。
- [x] `wiki +node-get --as bot` 是否需要授权：实测（2026-09-19）不需要，bot 直接读成功，
      拿到了 `space_id`。第 2 步用 `--as user` 的真实原因不是 node-get 本身要 user 权限，
      而是第 4 步「把 bot 加进空间」（`wiki +member-add`）必须 user 身份操作，bot 无法自己加自己。
- [ ] `wiki +node-create --as bot --obj-type docx` 建容器节点是否真的可行、返回结构里新节点
      token 的字段路径。目前只做过 `--dry-run`（两步编排：resolve parent space → create wiki
      node），未实建验证；容器节点本质是空 docx（飞书 wiki 无纯目录节点类型），需要确认这个
      降级方案在真实执行时没有额外限制（比如空 docx 标题能否正常显示、后续在其下建子文档是否
      顺畅）。
- [ ] `docs +create --as bot --parent-token <wiki 节点 token>` 是否真把文档建成该节点的子节点。
      dry-run 通过（`POST /open-apis/docs_ai/v1/documents`），但未实建验证。
- [ ] bot 建文档后，CLI 自动授予 CLI 用户 `full_access` 是否真的生效（用户在知识库里能否直接看到并编辑）。
- [ ] `wiki +node-list` 返回 item 里标题字段名与 `obj_token` 字段名。
- [ ] `docs +create` 返回结构中新文档 token 的字段路径。
- [ ] `docs +update --command overwrite` 在只有单一内容的独立文档上是否如预期整篇覆盖、无副作用。
