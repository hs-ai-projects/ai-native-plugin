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
