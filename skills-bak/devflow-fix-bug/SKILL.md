---
name: devflow-fix-bug
description: >
  处理bug修复。触发词：报错、坏了、不对、显示错误、点了没反应、XX失败、
  复现步骤、截图里的异常。飞书任务ID也可触发（先按语义判断任务性质，
  若判定为新需求应转由 devflow-start-task 处理）。
  走简化5步：理解→排查→修复方案→开发→验证，不生成SPEC/plan重工件。
  不需要用户手动选择本skill，Claude按对话内容自动路由。
---

# DevFlow Fix Bug

处理bug修复的简化流程，只处理**当前仓库**的任务。与 `devflow-start-task` 的
区别：不生成 intent.md/SPEC.md 这类需求流程重工件，判定为高风险时只报告不动手。

## 前置依赖探测

```bash
command -v git && command -v glab || echo "缺失依赖请先安装（见插件README前置依赖表）"
```

## 栈判定

```bash
stack_type=$(python3 -c "import yaml; print(yaml.safe_load(open('harness.yaml'))['project']['stack']['type'])")
```

`frontend` → 用 `agents/frontend.md`；`backend` → 用 `agents/backend.md`。没有
harness.yaml则停下询问——不强行猜测项目结构；引导用户参照
`${CLAUDE_PLUGIN_ROOT}/docs/harness-schema.md` 的字段规范生成一份。

## 外部工具调用前置检查

本次会话第一次调用 `lark-cli`/`glab`/`owl` 之前，先grep一下
`${CLAUDE_PLUGIN_ROOT}/PITFALLS.md` 有没有该工具的已知问题记录，有就提前
应用规避方法。任务收尾时若发生过工具使用纠偏，按 `PITFALLS.md` 的写入规则
主动问用户是否要记录。

## 转机器人交接前的协作配置（复用 devflow-start-task 的引导）

步骤2按 `rules/severity.md` 判定为"涉及跨仓库+需要对方开发"、要发起机器人任务
交接时，先确认本地协作配置齐了（`partner.py check $PWD`）；缺失/不完整按
`devflow-start-task` 的「协作配置按需初始化」小节引导用户补齐（提供对方 bot 名
+ 共同群 chat_id，用 `partner.py init` 写入）后再发交接消息——同一份引导逻辑，
不重复定义。配置齐之前不交接、不当纯本仓库硬修。

## 5步流程

1. **理解**：
   - **输入来源二选一**（同devflow-start-task）：
     - 传了task-id → `lark-cli`拉取全字段，记录触发消息sender
     - 直接对话描述bug → 用这段描述当输入，不产生飞书通知
   - 额外识别：复现路径/报错信息/截图（截图优先作为定位依据，含Network面板/
     URL栏/错误信息中的接口路径时直接提取完整路径）

2. **排查**：
   - 代码定位：按截图URL > 任务描述 > grep关键词的优先级定位候选文件
   - **观测云辅助**（可选）：检测目标仓库是否配置了观测云（`owl` cli是否在
     PATH + 项目是否声明观测云workspace）。
     - **配置了** → 按时间窗口推断（P1截图时间戳 > P2描述短语 > P3任务
       创建时间fallback）+ 接口路径过滤，查询错误/全量日志辅助定位
     - **未配置** → 跳过日志辅助，纯代码grep定位，不报错、不阻塞
   - 按 `rules/severity.md` 决策树判定风险等级：
     - **高风险** → 只输出排查报告（问题定位/涉及范围/建议），到此止步，
       不进入步骤3-5
     - **普通/中风险** → 继续

3. **修复方案**：写清楚要改什么/不改什么（轻量文字说明，**不生成**
   SPEC.md/plan.md）

4. **开发**：派给对应agent（frontend/backend.md）直接改代码（bug场景不需要
   Task Breakdown那套结构）

5. **验证**：
   - agent调用`skill:verify --self-check`自查
   - 调用`skill:review`（内部调用模式）生成review包并判断verdict
   - 若步骤2判定为"中风险"，可选触发`agents/verifier.md`独立复核
     （Task工具派发，同devflow-start-task步骤6-7的verifier调用方式）
   - verdict=PASS → 建MR，飞书通知（@回步骤1记录的触发者，若有）
   - verdict=FAIL → 回步骤4修复

## 异常处理

见 `failure-modes.md`。
