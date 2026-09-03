# harness.yaml 规范文档化 + PITFALLS.md 踩坑记录机制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把插件自建的 `harness.yaml` 最小字段集写成正式文档（`docs/harness-schema.md`），供两个主入口在"首次在某仓库运行且缺失harness.yaml"时引导用户参照；新增 `PITFALLS.md`（随插件分发的外部工具踩坑记录），并把"读取触发"规则接入两个主入口 SKILL.md（调用lark-cli/glab/owl前先查一遍）。

**Architecture:** 本 Plan 全部是文档新增 + 现有SKILL.md的小段引用补充，**不涉及任何脚本行为改动**——`harness.yaml`的字段本身已经在Plan 1/2/3引用的 `verify_runner.py`/`contract_checker.py` 里被实际使用，本Plan只是把这些散落在代码注释里的字段含义正式整理成一份用户能读的规范文档。`PITFALLS.md`是纯数据文件（表格），写入靠"任务收尾时agent主动询问用户是否记录"这一行为规则（写进两个主入口SKILL.md的收尾环节），不是自动化脚本。

**Tech Stack:** Markdown。无新脚本、无新测试框架依赖。

**Spec:** `docs/superpowers/specs/2026-09-03-devflow-v2-redesign.md` 第9节（harness.yaml）、第10节（PITFALLS.md）。

**依赖:** 假设 Plan 1（`docs/superpowers/plans/2026-09-03-verify-foundation.md`）、Plan 2（`docs/superpowers/plans/2026-09-03-entry-points-refactor.md`）已执行完毕——本Plan会在两个主入口SKILL.md里追加"首次运行检查harness.yaml"与"PITFALLS读取触发"的引用段落。若Plan 3未执行也不影响本Plan（本Plan不涉及机器人协作内容）。

## Global Constraints

- `docs/harness-schema.md` 的字段集**必须与spec第9节完全一致**：`project.stack.type`、`paths.business_code`/`paths.test_code`、`gates.fast`/`gates.full`、`commands.<layer>`——不额外新增字段，不删减已在`verify_runner.py`/`contract_checker.py`代码里实际读取的字段。
- `PITFALLS.md` 的表格字段固定为四列：`工具/场景 | 已知问题 | 规避方法 | 发现时间`。
- 写入规则**必须是"事后确认追加"**（任务收尾时主动问用户，用户确认才写），不得设计成自动无确认写入。
- 每次PITFALLS.md的追加**必须是独立commit**，不与业务改动的commit混在一起。
- 不引入自动过期检测/定期核查机制（spec已明确排除，Global Constraints承接这条排除决策）。

---

### Task 1: `docs/harness-schema.md` — harness.yaml 规范文档

**Files:**
- Create: `docs/harness-schema.md`
- Test: `scripts/test/test_harness_schema_doc.sh`

**Interfaces:**
- Consumes: 无（纯文档整理，字段定义来自已存在的 `scripts/verify/verify_runner.py` 的 `layer_command()`/`read_harness()` 函数逻辑与 `scripts/verify/contract_checker.py` 的 `load_repo_context()` 函数逻辑——这两个函数已在代码中实际读取这些字段，本任务只是把隐含在代码里的契约显式写成文档）
- Produces: 无程序化接口——纯文档，供 Task 3 在SKILL.md里引用路径

- [ ] **Step 1: 写测试（先写测试，红）**

```bash
#!/bin/bash
# docs/harness-schema.md 结构校验：字段集完整 + 与verify_runner.py/contract_checker.py
# 实际读取的字段名一致（防止文档字段名和代码字段名不同步）。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOC="$ROOT/docs/harness-schema.md"
[ -f "$DOC" ] || { echo "docs/harness-schema.md missing"; exit 1; }

# 字段集完整性
for field in "project.stack.type" "paths.business_code" "paths.test_code" \
             "gates.fast" "gates.full"; do
  grep -qF "$field" "$DOC" || { echo "field missing in doc: $field"; exit 1; }
done

# "怎么生效"章节存在（不只是罗列字段，要说明谁在什么时候读它）
grep -qi '生效\|谁在.*读\|栈判定' "$DOC" || { echo "missing 'how it takes effect' section"; exit 1; }

# 明确"不猜测/不探测"原则（呼应spec决策：拒绝探测猜测路线）
grep -qi '不猜\|不探测\|不做.*猜测' "$DOC" || { echo "missing no-guessing principle statement"; exit 1; }

# 交叉核对：文档提到的字段名确实是 verify_runner.py / contract_checker.py 代码里
# 实际读取的字段（防止文档虚构了代码不支持的字段）
RUNNER="$ROOT/scripts/verify/verify_runner.py"
CHECKER="$ROOT/scripts/verify/contract_checker.py"
grep -q 'stack.get("type"' "$RUNNER" 2>/dev/null || grep -q "stack\['type'\]\|stack.get('type'" "$RUNNER" || \
  { echo "verify_runner.py does not actually read stack.type as documented"; exit 1; }
grep -q 'business_code' "$CHECKER" || { echo "contract_checker.py does not actually read paths.business_code as documented"; exit 1; }

echo "test_harness_schema_doc: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_harness_schema_doc.sh`
Expected: `docs/harness-schema.md missing`（exit 1）

- [ ] **Step 3: 写 `docs/harness-schema.md`**

```markdown
# harness.yaml 规范

> 插件与目标仓库之间的显式合同：仓库声明"测试命令是什么/源码测试路径在哪"，
> 插件承诺"不猜，只按你说的做"。没有这份文件，插件无法知道该跑哪条验证命令，
> 只能停下来问，**不做探测猜测**——猜错比停下问更糟（这是本插件的既定原则，
> 不同于某些工具"看到package.json就跑npm test"的自动探测做法）。

## 为什么需要它

不同团队仓库的测试命令五花八门：有的用 `npm run test`，有的用 `pytest`，
有的前端用 `vitest`、后端用 `pytest tests/`。插件不可能硬编码猜测，只能靠
仓库自己声明一次、插件永久复用。写一次，以后每个任务都读这份声明，不用
每次都问。

## 字段集

```yaml
project:
  stack:
    type: frontend | backend      # 决定加载哪个 persona
paths:
  business_code: ["src/**"]       # 源码路径（glob模式列表）
  test_code: ["test/**", "tests/**"]  # 测试路径
gates:
  fast: [unit]                    # commit前自查跑哪些层
  full: [unit, contract]          # 汇总验证/独立verifier跑哪些层，contract层可选
commands:
  unit: "npm run test:unit"       # 具体命令，按仓库自己的栈填
  contract: "python3 <checker> ."  # 仅命中跨仓库协作任务时使用
```

（`commands.<layer>` 在现有 `verify_runner.py` 实现中对应
`project.stack.<type>_unit_cmd`/`<layer>_cmd` 的历史命名约定，例如
`backend_unit_cmd`/`frontend_unit_cmd`/`contract_cmd`——本文档描述的
`commands.unit` 是概念名，实际字段名以 `verify_runner.py` 的
`layer_command()` 函数为准，见"怎么生效"一节的具体路径。）

## 怎么生效（谁在什么时候读它）

- **栈判定**：两个主入口（`devflow-start-task`/`devflow-fix-bug`）起步第一
  步用YAML解析器读 `project.stack.type`，决定这次Task工具该派给
  `agents/frontend.md` 还是 `agents/backend.md`。
- **测试同步自查**：`skill:verify --self-check`（frontend/backend agent
  commit前调用）用 `paths.business_code`/`paths.test_code` 两个字段做路径
  匹配，判断"改了业务代码有没有同步改测试"，不是瞎猜"这个文件是不是源码"。
- **验证命令执行**：`skill:verify` 三种模式（`--self-check`/`--independent`/
  `--full`）分别读 `gates.fast`/`gates.full` 声明要跑哪些层，再从
  `project.stack` 里取每层对应的实际shell命令字符串，拼进
  `scripts/verify/verify_runner.py`/`fast-verify.sh` 执行。
- **契约检查（可选）**：命中跨仓库协作任务时，`contract`层的命令由
  `scripts/verify/contract_checker.py` 读取，同时该脚本会用
  `paths.business_code` 判断契约端点是否在本仓库代码里被实际引用（字段级
  漂移检测，见spec 7.15）。

## 缺失时的处理

两个主入口首次在某仓库运行且缺失 `harness.yaml` → **停下询问用户是否要
生成向导**，不强行探测猜测项目结构。这条规则的理由：猜测项目类型/测试命令
出错的代价（在错误的路径上跑了一堆本不该跑的命令）远高于停下来问一句的
代价。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_harness_schema_doc.sh`
Expected: `test_harness_schema_doc: ALL OK`

- [ ] **Step 5: Commit**

```bash
git add docs/harness-schema.md scripts/test/test_harness_schema_doc.sh
git commit -m "docs: add harness.yaml schema specification"
```

---

### Task 2: `PITFALLS.md` — 踩坑记录机制骨架

**Files:**
- Create: `PITFALLS.md`
- Test: `scripts/test/test_pitfalls_doc.sh`

**Interfaces:**
- Consumes: 无
- Produces: `PITFALLS.md` 文件本身（表格结构），供 Task 3 在两个主入口SKILL.md里引用"读取触发"/"写入触发"规则

- [ ] **Step 1: 写测试（先写测试，红）**

```bash
#!/bin/bash
# PITFALLS.md 结构校验：四列表头 + 空表体（骨架阶段无实际踩坑记录）+
# 写入/读取规则说明存在。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="$ROOT/PITFALLS.md"
[ -f "$FILE" ] || { echo "PITFALLS.md missing"; exit 1; }

# 四列表头
grep -qE '\|\s*工具/场景\s*\|\s*已知问题\s*\|\s*规避方法\s*\|\s*发现时间\s*\|' "$FILE" \
  || { echo "table header missing or wrong columns"; exit 1; }

# 写入规则说明：事后确认追加，不自动写
grep -qi '事后确认\|确认.*追加\|用户确认' "$FILE" || { echo "write-trigger rule (confirm-after-task) missing"; exit 1; }
grep -qi '独立.*commit\|单独.*commit' "$FILE" || { echo "independent-commit rule missing"; exit 1; }

# 读取规则说明：调用前先查
grep -qi '调用.*之前.*先\|先查\|提前应用' "$FILE" || { echo "read-trigger rule (check-before-call) missing"; exit 1; }

# 明确不做自动过期检测
grep -qi '不.*自动过期\|不.*定期核查' "$FILE" || { echo "no-auto-expiry statement missing"; exit 1; }

echo "test_pitfalls_doc: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_pitfalls_doc.sh`
Expected: `PITFALLS.md missing`（exit 1）

- [ ] **Step 3: 写 `PITFALLS.md`**

```markdown
# 踩坑记录

外部工具（lark-cli/glab/owl等）在实际使用中反复出现的已知问题，随插件分发
给所有装这个插件的团队，不是存在某个人的私有笔记里。

## 写入规则

**不自动写**。某次任务里调用lark-cli/glab/owl等外部工具时踩坑（命令报错、
返回格式出乎意料、或被用户当场纠正了错误用法），任务收尾时若发生过这类
纠偏，主动问用户"这次踩了个坑，要不要记进PITFALLS.md"，用户确认后才追加
一行。**每次追加都是独立commit**，不与业务改动的commit混在一起——避免污染
功能提交历史。

## 读取规则

任何skill在当次会话里第一次调用lark-cli/glab/owl之前，先grep一下本文件里
有没有该工具的记录，有就提前应用"已知问题+规避方法"，不等报错了才后知
后觉。

## 维护原则

不引入自动过期检测/定期核查机制——记录只会越攒越多，若某条后来发现工具已
修复不再适用，靠人工任务中偶然发现顺手改/删，不为一次性问题加自动化复杂度。

## 记录表

| 工具/场景 | 已知问题 | 规避方法 | 发现时间 |
|---|---|---|---|
| （暂无记录，首次遇到坑时按上述写入规则追加） | | | |
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_pitfalls_doc.sh`
Expected: `test_pitfalls_doc: ALL OK`

- [ ] **Step 5: Commit**

```bash
git add PITFALLS.md scripts/test/test_pitfalls_doc.sh
git commit -m "docs: add PITFALLS.md skeleton with write/read trigger rules"
```

---

### Task 3: 把 harness-schema.md 引导 + PITFALLS 读取触发接入两个主入口

**Files:**
- Modify: `skills/devflow-start-task/SKILL.md`
- Modify: `skills/devflow-fix-bug/SKILL.md`
- Modify: `scripts/test/test_skill.sh`
- Modify: `scripts/test/test_fix_bug_skill.sh`

**Interfaces:**
- Consumes: Task 1的 `docs/harness-schema.md`；Task 2的 `PITFALLS.md`
- Produces: 无新接口，追加引用段落到现有文件

- [ ] **Step 1: 先改两个测试文件的断言（红）**

在 `scripts/test/test_skill.sh` 追加：

```bash
# harness.yaml缺失时引导用户参照规范文档（不强行猜测）
grep -q 'harness-schema.md' "$SKILL" || { echo "must reference docs/harness-schema.md when harness.yaml missing"; exit 1; }

# 调用lark-cli/glab前先查PITFALLS.md
grep -q 'PITFALLS.md' "$SKILL" || { echo "must reference PITFALLS.md read-trigger"; exit 1; }
```

在 `scripts/test/test_fix_bug_skill.sh` 追加：

```bash
# 调用owl/glab前先查PITFALLS.md
grep -q 'PITFALLS.md' "$SKILL" || { echo "must reference PITFALLS.md read-trigger"; exit 1; }
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_skill.sh && bash scripts/test/test_fix_bug_skill.sh`
Expected: `must reference docs/harness-schema.md when harness.yaml missing`（第一个失败点）

- [ ] **Step 3: 改写 `devflow-start-task` 的"栈判定"章节**（原文件第19-25行）

原文本：

```markdown
## 栈判定（决定 persona 与验证层）

```bash
stack_type=$(python3 -c "import yaml; print(yaml.safe_load(open('harness.yaml'))['project']['stack']['type'])")
```

`frontend` → 用 `agents/frontend.md`，验证层跑 frontend_unit_cmd/e2e；`backend` → 用 `agents/backend.md`，验证层跑 backend_unit_cmd/api。没有 harness.yaml 则停下询问。
```

改为（把"没有harness.yaml则停下询问"细化为"引导用户参照规范文档"）：

```markdown
## 栈判定（决定 persona 与验证层）

```bash
stack_type=$(python3 -c "import yaml; print(yaml.safe_load(open('harness.yaml'))['project']['stack']['type'])")
```

`frontend` → 用 `agents/frontend.md`，验证层跑 frontend_unit_cmd/e2e；`backend`
→ 用 `agents/backend.md`，验证层跑 backend_unit_cmd/api。**没有 harness.yaml
则停下询问**——不强行猜测项目结构；引导用户参照
`${CLAUDE_PLUGIN_ROOT}/docs/harness-schema.md` 的字段规范生成一份。

## 外部工具调用前置检查

本次会话第一次调用 `lark-cli`/`glab` 之前，先grep一下
`${CLAUDE_PLUGIN_ROOT}/PITFALLS.md` 有没有该工具的已知问题记录，有就提前
应用规避方法。任务收尾时若发生过工具使用纠偏，按 `PITFALLS.md` 的写入规则
主动问用户是否要记录。
```

- [ ] **Step 4: 改写 `devflow-fix-bug` 的"前置依赖探测"章节**

原文本（Plan 2 Task 3产出）：

```markdown
## 前置依赖探测

```bash
command -v git && command -v glab || echo "缺失依赖请先安装（见插件README前置依赖表）"
```
```

改为：

```markdown
## 前置依赖探测

```bash
command -v git && command -v glab || echo "缺失依赖请先安装（见插件README前置依赖表）"
```

## 外部工具调用前置检查

本次会话第一次调用 `lark-cli`/`glab`/`owl` 之前，先grep一下
`${CLAUDE_PLUGIN_ROOT}/PITFALLS.md` 有没有该工具的已知问题记录，有就提前
应用规避方法。任务收尾时若发生过工具使用纠偏，按 `PITFALLS.md` 的写入规则
主动问用户是否要记录。
```

- [ ] **Step 5: 跑测试确认通过**

Run: `bash scripts/test/test_skill.sh && bash scripts/test/test_fix_bug_skill.sh`
Expected: 两者都输出 `ALL OK`

- [ ] **Step 6: Commit**

```bash
git add skills/devflow-start-task/SKILL.md skills/devflow-fix-bug/SKILL.md \
        scripts/test/test_skill.sh scripts/test/test_fix_bug_skill.sh
git commit -m "docs: wire harness-schema.md guidance and PITFALLS.md read-trigger into both entry skills"
```

---

## Self-Review

**1. Spec coverage**：spec第9节"harness.yaml插件自建最小契约"（字段集/作用/生效点/缺失处理）→ Task 1全覆盖；spec第10节"PITFALLS.md写入触发/读取触发/不做自动过期"→ Task 2全覆盖；两者接入两个主入口的引用点 → Task 3覆盖。

**2. Placeholder scan**：所有文档均为完整内容。`PITFALLS.md`的"记录表"章节故意只有一行占位说明文字（"暂无记录，首次遇到坑时按上述写入规则追加"）——这**不是**违反"无占位符"规则的TBD，是该文档设计上的合理初始状态（骨架文件，内容由后续实际使用中动态追加，这是文档的正常生命周期起点，不是本Plan该完成而未完成的工作）。

**3. 类型/接口一致性**：Task 1文档里"怎么生效"章节描述的字段读取路径（`verify_runner.py`的`layer_command()`、`contract_checker.py`的`load_repo_context()`）与Plan 1 Task 1 `skills/verify/SKILL.md`里"具体命令执行委托给fast-verify.sh/full-verify.sh"的描述一致，没有引入与Plan 1矛盾的新说法。

**4. 与Plan1/2/3的边界**：本Plan不修改任何脚本的实际行为（`verify_runner.py`/`contract_checker.py`/`handoff.py`/`partner.py`一行代码都不动），纯粹是给已存在的隐式契约（代码里已经在用的字段名）补一份显式文档，以及新增一份此前完全不存在的记录机制。Task 3修改的两个SKILL.md文件都是Plan 2/3已经产出的文件，本Plan只追加两小段引用，不改动Plan 2/3已写好的其他内容——Step 3/4的编辑范围都精确限定在"栈判定"和"前置依赖探测"章节之后追加新内容，不touch其他章节。

**5. 依赖顺序**：Task 1和Task 2互相独立，可并行；Task 3依赖两者都完成。三个任务均可独立commit验证。本Plan是四份Plan里风险最低的一份（纯文档，无脚本逻辑变更），按spec建议顺序放在最后执行，但技术上也可以提前到Plan 1之后就做——之所以仍放最后，是因为"哪些字段真正被用到"这件事在Plan 1/2/3的脚本引用点全部落地后才能最终确认文档没有遗漏或多余，提前写容易文档与代码脱节。
