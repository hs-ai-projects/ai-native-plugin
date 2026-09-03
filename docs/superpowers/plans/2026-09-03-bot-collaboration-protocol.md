# 机器人协作协议扩展：任务交接 + bot-boundary + 飞书通知对象 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增机器人任务交接协议（`[handoff]` 消息类型 + `scripts/collab/handoff.py` 状态机），补上原有"机器人对齐"协议（只能对齐字段，不能真正转交开发工作）的缺口；新增 `skills/bot-boundary/SKILL.md`（限定"被另一个bot@"场景的行为边界）；把 Plan 2 中预留占位的 `devflow-start-task` 步骤1.4"机器人任务交接"分支补齐为可执行描述。

**Architecture:** `handoff.py` 与已存在的 `scripts/collab/partner.py` 平级、风格一致（同样的 `--dir` 参数约定、同样的本地状态机JSON落盘方式、同样的消息前缀正则解析思路），但语义完全独立——`partner.py` 管"对齐"（confirm/reject/drift三态），`handoff.py` 管"交接"（accept/reject/defer/done四态，且交接是单向转移而非双向确认）。两个脚本不共享状态文件，`contract-state.json` 和新增的 `handoff-state.json` 分别落在 `.ai-devflow/<task_id>/` 下互不干扰。`skills/bot-boundary/SKILL.md` 是纯行为契约文档（不含可执行脚本），复用 `handoff.py`/`partner.py` 已有的消息前缀解析函数来判断"这条bot消息该走哪个协议"。

**Tech Stack:** Python 3（沿用 `partner.py` 的 argparse 子命令模式，无新依赖）+ Markdown + bash/pytest 混合测试（`handoff.py` 用 pytest 风格测试，与 `test_partner.py` 保持一致；SKILL.md用bash grep断言，与既有skill测试风格一致）。

**Spec:** `docs/superpowers/specs/2026-09-03-devflow-v2-redesign.md` 第5.2节（机器人任务交接）、第8节（飞书通知与机器人边界）。

**依赖:** 假设 `docs/superpowers/plans/2026-09-03-entry-points-refactor.md`（Plan 2）已执行完毕——`devflow-start-task` 的步骤1.4已存在"涉及跨仓库·需要对方真正开发"分支的占位引用（当前占位文本："触发机器人任务交接协议（见 `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py`，具体消息格式与接收方处理逻辑见插件文档）"），本 Plan 把这个占位补成完整可执行描述。

## Global Constraints

- 新消息前缀协议固定为 `[cc-task <task-id>][handoff] <action>`，action 枚举值固定为：`交接请求：<摘要> | 触发原因：<理由> | 原始发起人：<@某人 或 无>`、`接受`、`拒绝：<理由>`、`延后：<理由>`、`已完成：<MR链接>`——**不得**与现有 `[contract]` 前缀协议的action词汇（确认/拒绝/契约漂移）混用，两套协议靠前缀关键字（`contract` vs `handoff`）区分，解析函数必须能正确路由，不能把一种消息误判成另一种。
- 接收方收到交接消息后**必须**走自己独立的 Accept/Reject/Defer 判断（复用 `devflow-start-task` 步骤1现有的intent.md Decision逻辑），**不得**因为交接方是可信bot就跳过判断直接开工。
- 交接完成通知的对象规则：接收方Accept后直接通知"原始发起人"字段（若交接消息里该字段非空）；接收方Reject/Defer时回复给交接方bot，交接方**必须**转告原始发起人（这一步不能省略）。
- `handoff.py` 的本地状态文件（`.ai-devflow/<task_id>/handoff-state.json`）只做断点缓存，不是同步源——与 `partner.py` 现有的"文件系统隔离，真值在飞书群消息里"的设计原则一致（沿用spec 3.2.0已定的架构约束）。
- `skills/bot-boundary/SKILL.md` 的边界规则**只适用于**"飞书群消息sender是另一个bot身份"这一种场景，不得影响"人类用户直接@机器人"的现有行为（那部分逻辑不变）。

---

### Task 1: `scripts/collab/handoff.py` — 任务交接本地状态机

**Files:**
- Create: `scripts/collab/handoff.py`
- Test: `scripts/test/test_handoff.py`

**Interfaces:**
- Consumes: 无（新脚本，不依赖其他新建文件；风格参考已存在的 `scripts/collab/partner.py` 但不导入它——两者职责独立，各自维护自己的状态文件）
- Produces:
  - `parse_handoff_message(text) -> dict|None`：解析 `[cc-task <id>][handoff] <action>` 前缀消息，返回 `{"task_id": str, "action": "request"|"accept"|"reject"|"defer"|"done", "summary": str|None, "reason": str|None, "requester": str|None, "mr_url": str|None}`，供 Task 3 的 `bot-boundary` skill 引用其路由逻辑
  - `main()` CLI 子命令：`state <task_id> <status> [--requester R] [--reason R] [--mr-url U] [--dir REPO]`（status ∈ draft|requested|accepted|rejected|deferred|done）、`get <task_id> [--dir REPO]`

- [ ] **Step 1: 写测试（先写测试，红）**

```python
"""Unit tests for scripts/collab/handoff.py: 消息解析 + 本地状态机。

任务交接协议与 partner.py 的"机器人对齐"协议独立——对齐是双向确认字段定义，
交接是单向转移整块开发工作，接收方走自己完整的Accept/Reject/Defer判断。
"""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "collab", "handoff.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(SCRIPT)))


def run(*args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), *[str(a) for a in args]],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=e,
    )


# ── 消息解析 ────────────────────────────────────────────────────────────

def test_parse_handoff_request():
    from handoff import parse_handoff_message
    text = ("[cc-task T1][handoff] 交接请求：新增订单状态查询接口 | "
            "触发原因：前端页面需要后端提供该接口，当前不存在 | "
            "原始发起人：@张三")
    p = parse_handoff_message(text)
    assert p["task_id"] == "T1"
    assert p["action"] == "request"
    assert "订单状态查询" in p["summary"]
    assert "前端页面需要" in p["reason"]
    assert p["requester"] == "@张三"


def test_parse_handoff_request_no_requester():
    from handoff import parse_handoff_message
    text = "[cc-task T2][handoff] 交接请求：加个缓存 | 触发原因：性能问题 | 原始发起人：无"
    p = parse_handoff_message(text)
    assert p["requester"] is None


def test_parse_handoff_accept():
    from handoff import parse_handoff_message
    p = parse_handoff_message("[cc-task T1][handoff] 接受")
    assert p == {"task_id": "T1", "action": "accept", "summary": None,
                 "reason": None, "requester": None, "mr_url": None}


def test_parse_handoff_reject():
    from handoff import parse_handoff_message
    p = parse_handoff_message("[cc-task T1][handoff] 拒绝：这块不需要后端改")
    assert p["action"] == "reject"
    assert p["reason"] == "这块不需要后端改"


def test_parse_handoff_defer():
    from handoff import parse_handoff_message
    p = parse_handoff_message("[cc-task T1][handoff] 延后：本周排期已满")
    assert p["action"] == "defer"
    assert p["reason"] == "本周排期已满"


def test_parse_handoff_done():
    from handoff import parse_handoff_message
    p = parse_handoff_message("[cc-task T1][handoff] 已完成：https://gitlab.example.com/mr/1")
    assert p["action"] == "done"
    assert p["mr_url"] == "https://gitlab.example.com/mr/1"


def test_parse_no_handoff_prefix_returns_none():
    from handoff import parse_handoff_message
    assert parse_handoff_message("普通消息") is None


def test_parse_contract_prefix_not_confused_with_handoff():
    """[contract]前缀消息不应被handoff解析器误判——两套协议靠前缀关键字区分。"""
    from handoff import parse_handoff_message
    assert parse_handoff_message("[cc-task T1][contract 1.0] 确认") is None


# ── 本地状态机 ──────────────────────────────────────────────────────────

def test_state_write_then_get(tmp_path):
    r = run("state", "T1", "requested", "--requester", "@张三", "--dir", tmp_path)
    assert r.returncode == 0, r.stderr
    st = json.loads(r.stdout)
    assert st["status"] == "requested" and st["requester"] == "@张三"
    r2 = run("get", "T1", "--dir", tmp_path)
    assert json.loads(r2.stdout)["status"] == "requested"


def test_state_bad_status_fails(tmp_path):
    r = run("state", "T1", "nope", "--dir", tmp_path)
    assert r.returncode == 1
    assert "bad status" in r.stderr


def test_get_missing_returns_draft(tmp_path):
    r = run("get", "nope", "--dir", tmp_path)
    assert r.returncode == 0
    assert json.loads(r.stdout)["status"] == "draft"


def test_state_reject_records_reason(tmp_path):
    run("state", "T1", "requested", "--dir", tmp_path)
    r = run("state", "T1", "rejected", "--reason", "不需要后端改", "--dir", tmp_path)
    st = json.loads(r.stdout)
    assert st["status"] == "rejected" and st["reason"] == "不需要后端改"


def test_state_done_records_mr_url(tmp_path):
    run("state", "T1", "accepted", "--dir", tmp_path)
    r = run("state", "T1", "done", "--mr-url", "https://x/mr/1", "--dir", tmp_path)
    st = json.loads(r.stdout)
    assert st["status"] == "done" and st["mr_url"] == "https://x/mr/1"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `cd scripts/test && python3 -m pytest test_handoff.py -v`
Expected: `ModuleNotFoundError` 或 `FileNotFoundError`（`scripts/collab/handoff.py` 不存在）

- [ ] **Step 3: 写 `scripts/collab/handoff.py`**

```python
#!/usr/bin/env python3
"""handoff.py — spec 5.2 机器人任务交接协议的本地状态机 + 消息解析。

背景：原有 partner.py 承载的"机器人对齐"协议只解决"确认接口字段定义"，
不解决"把一整块开发工作真的转交给对方仓库独立完成"。本脚本承载后者——
交接不是双向确认，是单向转移：发起方发交接请求，接收方走自己完整的
devflow-start-task 的 Accept/Reject/Defer 判断（不因为交接方是可信bot就
默认接受），Accept后接收方独立跑完整流程，完成后回报。

两套协议靠消息前缀关键字区分（[contract ...] vs [handoff]），互不干扰，
不共享状态文件——本脚本的状态落在 <dir>/.ai-devflow/<task_id>/handoff-state.json，
partner.py 的状态落在同目录的 contract-state.json。

子命令：
  state <task_id> <status> [--requester R] [--reason R] [--mr-url U] [--dir REPO]
      status ∈ draft|requested|accepted|rejected|deferred|done。
  get <task_id> [--dir REPO]
      读状态，文件不存在时输出 status=draft 的空状态（不报错）。
"""
import argparse
import json
import os
import re
import sys
import time

STATE_STATUSES = ("draft", "requested", "accepted", "rejected", "deferred", "done")
DEFAULT_DIR = os.getcwd()

# 机器可读交接消息前缀：[cc-task <task-id>][handoff] <action 描述>
# 与 partner.py 的 [contract <M.m>] 前缀用不同的中括号内容区分，避免误判。
MSG_PREFIX_RE = re.compile(r"\[cc-task\s+([^\]]+?)\]\s*\[handoff\]\s*(.*)", re.S)


def state_path(task_id, base):
    return os.path.join(base, ".ai-devflow", task_id, "handoff-state.json")


def empty_state(task_id):
    return {
        "task_id": task_id,
        "status": "draft",
        "requester": None,
        "reason": None,
        "mr_url": None,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def read_state(task_id, base):
    p = state_path(task_id, base)
    if not os.path.isfile(p):
        return empty_state(task_id)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return empty_state(task_id)


def write_state(state, base):
    p = state_path(state["task_id"], base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return p


def parse_handoff_message(text):
    """解析带 [handoff] 前缀的交接消息 → dict | None。

    action ∈ request|accept|reject|defer|done（按正文关键词判定）。
    request 额外解析 summary/reason/requester（"原始发起人：无" → requester=None）。
    reject/defer 解析 reason。done 解析 mr_url。
    """
    if not text:
        return None
    m = MSG_PREFIX_RE.search(text)
    if not m:
        return None
    task_id, rest = m.group(1).strip(), m.group(2).strip()

    result = {"task_id": task_id, "action": None, "summary": None,
              "reason": None, "requester": None, "mr_url": None}

    if rest.startswith("交接请求"):
        result["action"] = "request"
        # 格式：交接请求：<摘要> | 触发原因：<理由> | 原始发起人：<@某人 或 无>
        parts = rest.split("|")
        for part in parts:
            part = part.strip()
            if part.startswith("交接请求："):
                result["summary"] = part[len("交接请求："):].strip()
            elif part.startswith("触发原因："):
                result["reason"] = part[len("触发原因："):].strip()
            elif part.startswith("原始发起人："):
                requester = part[len("原始发起人："):].strip()
                result["requester"] = None if requester == "无" else requester
    elif rest == "接受":
        result["action"] = "accept"
    elif rest.startswith("拒绝："):
        result["action"] = "reject"
        result["reason"] = rest[len("拒绝："):].strip()
    elif rest.startswith("延后："):
        result["action"] = "defer"
        result["reason"] = rest[len("延后："):].strip()
    elif rest.startswith("已完成："):
        result["action"] = "done"
        result["mr_url"] = rest[len("已完成："):].strip()
    else:
        return None

    return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="handoff.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("state")
    sp.add_argument("task_id")
    sp.add_argument("status")
    sp.add_argument("--requester", default=None)
    sp.add_argument("--reason", default=None)
    sp.add_argument("--mr-url", default=None)
    sp.add_argument("--dir", default=DEFAULT_DIR)

    sp = sub.add_parser("get")
    sp.add_argument("task_id")
    sp.add_argument("--dir", default=DEFAULT_DIR)

    args = p.parse_args()

    if args.cmd == "state":
        if args.status not in STATE_STATUSES:
            sys.stderr.write(f"handoff: bad status {args.status!r}; one of {STATE_STATUSES}\n")
            sys.exit(1)
        state = read_state(args.task_id, args.dir)
        state["status"] = args.status
        if args.requester is not None:
            state["requester"] = args.requester
        if args.reason is not None:
            state["reason"] = args.reason
        if args.mr_url is not None:
            state["mr_url"] = args.mr_url
        write_state(state, args.dir)
        print(json.dumps(state, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "get":
        print(json.dumps(read_state(args.task_id, args.dir), ensure_ascii=False))
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd scripts/test && python3 -m pytest test_handoff.py -v`
Expected: 全部测试通过（12个test函数）

- [ ] **Step 5: Commit**

```bash
git add scripts/collab/handoff.py scripts/test/test_handoff.py
git commit -m "feat: add scripts/collab/handoff.py for bot task-handoff protocol"
```

---

### Task 2: `skills/bot-boundary/SKILL.md` — 机器人边界

**Files:**
- Create: `skills/bot-boundary/SKILL.md`
- Test: `scripts/test/test_bot_boundary_skill.sh`

**Interfaces:**
- Consumes: Task 1 的 `handoff.py`（`parse_handoff_message`函数名，正文引用）；现有 `partner.py`（`parse_collab_message`函数名，正文引用）
- Produces: 无程序化接口——供 `devflow-start-task`（Plan 2已存在，本Plan Task 3会更新其步骤1.4引用点）在"协作消息识别"环节引用

- [ ] **Step 1: 写测试（先写测试，红）**

```bash
#!/bin/bash
# skills/bot-boundary/SKILL.md 结构校验：仅限bot@bot场景 + 三分支路由完整 +
# 不影响人类用户@机器人场景的措辞存在。
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/skills/bot-boundary/SKILL.md"
[ -f "$SKILL" ] || { echo "skills/bot-boundary/SKILL.md missing"; exit 1; }

grep -q '^name: bot-boundary' "$SKILL" || { echo "frontmatter name missing"; exit 1; }

# 触发条件限定：sender是另一个bot
grep -qi 'sender.*bot\|另一个bot\|被.*bot.*@' "$SKILL" || { echo "trigger condition (bot sender) missing"; exit 1; }

# 三分支路由：contract/handoff/无前缀
grep -q '\[contract\]' "$SKILL" || { echo "contract branch missing"; exit 1; }
grep -q '\[handoff\]' "$SKILL" || { echo "handoff branch missing"; exit 1; }
grep -qi '不带.*前缀\|无.*前缀' "$SKILL" || { echo "no-prefix branch missing"; exit 1; }

# 无前缀分支：只分析不动手
grep -qi '只输出分析性回复\|不执行任何写操作' "$SKILL" || { echo "analyze-only rule missing"; exit 1; }
grep -qi '不改代码\|不建sandbox\|不建MR\|不merge' "$SKILL" || { echo "no-write-action specifics missing"; exit 1; }

# 明确不影响人类用户场景
grep -qi '人类用户\|与.*人类.*区分\|区分.*人类' "$SKILL" || { echo "human-user distinction missing"; exit 1; }

# 引用两个解析函数
grep -qi 'parse_handoff_message\|handoff.py' "$SKILL" || { echo "handoff.py reference missing"; exit 1; }
grep -qi 'parse_collab_message\|partner.py' "$SKILL" || { echo "partner.py reference missing"; exit 1; }

echo "test_bot_boundary_skill: ALL OK"
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_bot_boundary_skill.sh`
Expected: `skills/bot-boundary/SKILL.md missing`

- [ ] **Step 3: 写 `skills/bot-boundary/SKILL.md`**

```markdown
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash scripts/test/test_bot_boundary_skill.sh`
Expected: `test_bot_boundary_skill: ALL OK`

- [ ] **Step 5: Commit**

```bash
git add skills/bot-boundary/SKILL.md scripts/test/test_bot_boundary_skill.sh
git commit -m "feat: add skills/bot-boundary SKILL.md for bot-to-bot message routing"
```

---

### Task 3: 补齐 `devflow-start-task` 步骤1.4 的任务交接分支为完整可执行描述

**Files:**
- Modify: `skills/devflow-start-task/SKILL.md`
- Modify: `scripts/test/test_skill.sh`

**Interfaces:**
- Consumes: Task 1 的 `handoff.py`；Task 2 的 `bot-boundary` skill
- Produces: 无新接口，改写现有占位文本

- [ ] **Step 1: 先改测试断言（红）**

新增断言到 `test_skill.sh`：

```bash
# 步骤1.4任务交接分支：必须给出完整可执行描述（不能是Plan2留下的占位引用），
# 含发起方发交接消息格式 + 接收方独立判断 + 通知原始发起人的规则
grep -q 'handoff.py' "$SKILL" || { echo "step1.4 must reference handoff.py"; exit 1; }
grep -qi '接收方.*独立.*判断\|独立走.*Accept/Reject/Defer' "$SKILL" || { echo "step1.4 missing receiver-independent-judgment rule"; exit 1; }
grep -qi '原始发起人' "$SKILL" || { echo "step1.4 missing original-requester notification rule"; exit 1; }

# 协作消息识别前置规则要能路由到bot-boundary
grep -qi 'bot-boundary\|skills/bot-boundary' "$SKILL" || { echo "must reference skills/bot-boundary for collab message routing"; exit 1; }
```

- [ ] **Step 2: 跑测试确认失败（红）**

Run: `bash scripts/test/test_skill.sh`
Expected: 失败于新增断言（handoff.py/接收方独立判断/原始发起人/bot-boundary任一未命中，取决于Plan2占位文本的具体措辞）

- [ ] **Step 3: 改写"协作消息识别"章节**（原文件第27-36行）

原文本：

```markdown
## 协作消息识别（3.2 前置，先于 9 步）

当前会话若由飞书群消息触发，**先看消息正文是否带机器前缀** `[cc-task <task-id>][contract <M.m>]`：

- **带前缀** → 这是搭档 bot 的**契约协作消息**，不是新任务。若本地存在 `.ai-devflow/<task-id>/contract-state.json` 且有对应状态，按动作处理，**处理完不进 9 步主流程**：
  - `确认` → 你正是被请求确认方且契约可接受 → 回复 `[cc-task <task-id>][contract <M.m>] 确认`（@ 发起方）。
  - `拒绝：<差异>` → 回复 `[cc-task <task-id>][contract <M.m>] 拒绝：<差异>`。
  - `契约漂移：... 请重新确认` → 核对漂移后回复确认或拒绝。
  协作消息只做"对齐需求边界与接口契约"，不合作改代码。前缀工具：`${CLAUDE_PLUGIN_ROOT}/scripts/collab/partner.py` 的 `parse_collab_message` 逻辑。
- **不带前缀** → 走下方 9 步主流程。
```

改为（引入 `bot-boundary` 三分支判断，把原有的"带前缀→契约协作"细化为"两种前缀分别处理"，同时把"不带前缀"细化成"要看sender是不是bot"）：

```markdown
## 协作消息识别（前置，先于 9 步）

当前会话若由飞书群消息触发，先判断消息 sender 是否为另一个bot身份，按
`skills/bot-boundary` 的三分支路由处理（详见该skill）：

- **消息带 `[cc-task <task-id>][contract <M.m>]` 前缀** → 机器人对齐消息，
  不是新任务。若本地存在 `.ai-devflow/<task-id>/contract-state.json` 且有
  对应状态，按动作处理，**处理完不进9步主流程**：
  - `确认` → 回复 `[cc-task <task-id>][contract <M.m>] 确认`（@发起方）
  - `拒绝：<差异>` → 回复 `[cc-task <task-id>][contract <M.m>] 拒绝：<差异>`
  - `契约漂移：... 请重新确认` → 核对漂移后回复确认或拒绝
  前缀解析：`${CLAUDE_PLUGIN_ROOT}/scripts/collab/partner.py` 的
  `parse_collab_message`。

- **消息带 `[cc-task <task-id>][handoff]` 前缀** → 机器人任务交接消息。
  前缀解析：`${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py` 的
  `parse_handoff_message`。按action分支：
  - `交接请求：<摘要> | 触发原因：<理由> | 原始发起人：<@某人或无>` →
    **把交接内容当成本仓库步骤1的第三种输入来源**（同task-id/直接对话描述
    并列），进入正常的intent.md理解流程——**独立判断Accept/Reject/Defer**，
    不因为交接方是可信bot就默认Accept：
    - **Accept** → intent.md完成后，若"原始发起人"字段非空，直接@回那个人
      说明"已接手，正在处理"（不经交接方转发）；然后正常走完整9步（自己的
      SPEC/sandbox/开发/验证/review/MR）。用
      `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py state <task-id>
      accepted --dir $PWD` 记录本地状态。
    - **Reject/Defer** → 回复 `[cc-task <task-id>][handoff] 拒绝：<理由>` 或
      `延后：<理由>` 给交接方bot（交接方收到后必须转告原始发起人，这是
      交接方的职责，不是本仓库要做的事）。用 `handoff.py state <task-id>
      rejected --reason <理由> --dir $PWD` 记录本地状态。
  - `接受`/`拒绝：<理由>`/`延后：<理由>` → 若本仓库是发起方，收到这是对方
    对自己发出交接请求的回应，更新本地 `handoff.py state <task-id>
    <accepted|rejected|deferred>` 状态，若非Accept则转告原始发起人。
  - `已完成：<MR链接>` → 若本仓库是发起方，收到这是接收方任务完成回报，
    `handoff.py state <task-id> done --mr-url <链接> --dir $PWD` 记录，视
    情况通知原始发起人（若步骤中接收方已直接通知过，这里只需在自己任务
    记录里标注完成，不必重复打扰用户）。
  处理完**不进9步主流程**（除非是"交接请求→Accept"分支，那种情况是走
  **自己的**9步主流程，输入来源是交接内容而非task-id/对话描述）。

- **消息不带任何已知前缀**（且sender确认是bot身份）→ 只输出分析性回复，
  不执行任何写操作（见`skills/bot-boundary`）。

- **sender是人类用户**（无论消息是否带前缀）→ 不适用上述bot-boundary规则，
  走下方9步主流程正常自动路由。
```

- [ ] **Step 4: 改写步骤1.4任务交接分支**（Plan 2 Task 2 Step 4中写入的占位文本）

原占位文本：

```markdown
       - **涉及跨仓库·需要对方真正开发** → 触发机器人任务交接协议（见
         `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py`，具体消息格式与
         接收方处理逻辑见插件文档），交接后若本仓库还有剩余工作则继续步骤2，
         若整块转出则到此止步
```

改为：

```markdown
       - **涉及跨仓库·需要对方真正开发** → 发起机器人任务交接：组织交接消息
         `[cc-task <task-id>][handoff] 交接请求：<需求摘要> | 触发原因：
         <为什么判定对方需要开发> | 原始发起人：<步骤1.1记录的sender，或"无"
         （若来源是对话描述）>`，@对方bot发到`partner.yaml`声明的群里；
         `${CLAUDE_PLUGIN_ROOT}/scripts/collab/handoff.py state <task-id>
         requested --requester <原始发起人> --dir $PWD` 记录本地状态。
         等待对方回应（接受/拒绝/延后，见上方"协作消息识别"章节的处理规则）。
         交接后若本仓库还有剩余工作（比如前端仍需自己改一部分）则继续步骤2，
         若整块转出则到此止步——不产生本仓库的sandbox/MR。
```

- [ ] **Step 5: 跑测试确认通过**

Run: `bash scripts/test/test_skill.sh`
Expected: `test_skill: ALL OK`

- [ ] **Step 6: 跑全量回归确认没有破坏Plan1/Plan2产出的其他测试**

Run:
```bash
bash scripts/test/test_verify_skill.sh
bash scripts/test/test_verifier_agent.sh
bash scripts/test/test_agents.sh
bash scripts/test/test_review_skill.sh
bash scripts/test/test_fix_bug_skill.sh
bash scripts/test/test_bot_boundary_skill.sh
cd scripts/test && python3 -m pytest test_handoff.py test_partner.py -v
```
Expected: 全部通过（`test_partner.py`同时跑一遍确认Task1新增的handoff.py没有意外影响partner.py的既有测试——两者是独立文件，理应互不影响，这一步是显式确认）

- [ ] **Step 7: Commit**

```bash
git add skills/devflow-start-task/SKILL.md scripts/test/test_skill.sh
git commit -m "feat: complete devflow-start-task handoff protocol integration, replacing Plan2 placeholder"
```

---

## Self-Review

**1. Spec coverage**：spec第5.2节"机器人任务交接"全部要点——新消息类型/交接流程五步/接收方独立判断/通知原始发起人规则——分别由 Task 1（handoff.py消息解析与状态机）+ Task 3（SKILL.md把流程五步转成可执行描述）覆盖；spec第8.2节"bot-boundary三分支" → Task 2覆盖；spec第8.1节"飞书通知改@回触发者"已在Plan 2 Task 2 Step5落地（步骤3改写），本Plan Task 3只是在此基础上补充"交接场景通知原始发起人"这个特殊分支，未重复改写Plan2已完成的部分。

**2. Placeholder scan**：所有测试文件和SKILL.md/handoff.py正文均为完整实现，无TODO。Task 3明确指出自己在"消化"Plan 2 Task 2 Step 4留下的占位文本，这是刻意的跨Plan依赖衔接，不是本Plan自己遗留的空白。

**3. 类型/接口一致性**：`parse_handoff_message`返回的dict字段名（`task_id`/`action`/`summary`/`reason`/`requester`/`mr_url`）在Task 1定义后，Task 2的bot-boundary SKILL.md和Task 3的devflow-start-task SKILL.md均只在自然语言正文中引用函数名与action枚举值，未引入与Task1不一致的字段名或action词汇（交接请求/接受/拒绝/延后/已完成，五个action贯穿三个任务保持一致）。`handoff.py`的status枚举（draft/requested/accepted/rejected/deferred/done）与`parse_handoff_message`的action枚举（request/accept/reject/defer/done）刻意使用不同词形（status是名词态过去分词，action是动词态）——这是有意的命名区分（一个描述"当前状态"，一个描述"这条消息代表的动作"），Task 3引用时对两者未混淆（`handoff.py state ... accepted`用status枚举，消息正文用"接受"对应action枚举）。

**4. 与Plan1/Plan2的边界**：本Plan不修改`scripts/collab/partner.py`的任何现有逻辑（Task 2的bot-boundary skill只是在文档里引用`parse_collab_message`函数名，不改其实现）；不修改Plan1产出的`skills/verify/SKILL.md`/`agents/verifier.md`；不修改Plan2产出的`skills/devflow-fix-bug/`（bug流程的机器人交接支持已在Plan2 Task3 Step5的severity.md优先级2里预留"转入机器人任务交接协议"的引用，本Plan未展开该处细节，因为bug场景的交接是否需要与需求场景完全一致的消息格式，在原spec里没有单独区分讨论，沿用同一套`handoff.py`协议即可，不需要额外改动）。

**5. 依赖顺序**：Task 1（handoff.py）→ Task 2（bot-boundary引用handoff.py）→ Task 3（SKILL.md引用两者）严格递增，且Task 3明确依赖Plan2已产出的占位文本存在。三个任务各自可独立commit验证，Task 3的Step 6额外做了跨Plan回归检查（对Plan1/Plan2产出的测试文件全部重跑一遍），这是因为Task 3改写的是Plan2产出的同一份文件（`skills/devflow-start-task/SKILL.md`），风险高于Task1/2的纯新增，因此在此task内加了一道额外验证步骤。
