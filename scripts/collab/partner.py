#!/usr/bin/env python3
"""partner.py — spec 3.2/7.15 跨仓库协作的本地承载：partner.yaml 校验、契约对齐
本地状态机（contract-state.json）、以及"收敛群确认"（gather）。

背景（spec 3.2.0）：两个实例文件系统隔离，协作状态真值只落在飞书群消息里；
本脚本管理的 partner.yaml / contract-state.json 只是实例本地的断点缓存，不是同步源。
"对方确认"的动作由两边 bot 在群里以带 [cc-task <task-id>][contract <M.m>] 前缀的消息
互相收发（机器可读协议，见 SKILL.md 协作识别前置规则），本脚本不发送消息，
只负责在需要放行前把"群里已确认到什么版本"收敛回本地状态。

子命令：
  check <repo_dir>
      读/校验 <repo_dir>/.ai-devflow/partner.yaml 结构。协作所需字段齐 → exit 0；
      文件缺失或结构不全 → exit 1（stderr 说明缺什么）。
  init [--bot B] [--group-id G] [--auto-align] [--no-enable] [--force] [--dir REPO]
      按需写入/补齐 <dir>/.ai-devflow/partner.yaml。编排 skill 判定需求涉及
      协作、但本地缺配置时走这里当场初始化（把"@ 谁 / 在哪个群"落成文件）。
      enabled 时要求 bot+group_id 齐（校验同 check）；已存在且完整时需 --force
      覆盖。写后打印生成路径与完整结构。
  state <task_id> <status> [--ack-version V] [--pending-version V] [--cursor-ms N] [--dir REPO]
      读写 <dir>/.ai-devflow/<task_id>/contract-state.json。status ∈
      draft|pending|aligned|drifted|superseded。写后 stdout 打印最新状态 JSON。
  get <task_id> [--dir REPO]
      读状态，输出 JSON。文件不存在时输出 status=draft 的空状态（不报错）。
  gather <task_id> [--dir REPO]
      收敛：以 last_cursor_ms 为游标调飞书查群里带 [cc-task <task_id>] 的消息，
      筛出最新一条"确认"并回写 state.ack_version / status；游标推进到最新消息时间。
      飞书查询可注入：env LARK_CMD（默认 lark-cli）、PARTNER_FEISHU=skip|auto
      （skip=只做本地 get 收敛比较，不调飞书，供 dry-run/无凭据环境）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_DIR = os.getcwd()
STATE_STATUSES = ("draft", "pending", "aligned", "drifted", "superseded")

# 机器可读协作消息前缀：[cc-task <task-id>][contract <M.m>] <action 描述>
MSG_PREFIX_RE = re.compile(r"\[cc-task\s+([^\]]+?)\]\s*\[contract\s+([0-9][0-9.]*)\]\s*(.*)", re.S)


def state_path(task_id, base):
    return os.path.join(base, ".ai-devflow", task_id, "contract-state.json")


def contract_path(task_id, base):
    return os.path.join(base, ".ai-devflow", task_id, "contract.json")


def partner_path(base):
    return os.path.join(base, ".ai-devflow", "partner.yaml")


def empty_state(task_id):
    return {
        "task_id": task_id,
        "status": "draft",
        "ack_version": None,      # 群里对方确认到的最新契约版本（收敛结果）
        "pending_version": None,  # 本方发起但对方未确认的版本（pending/drifted 时）
        "last_cursor_ms": 0,      # 飞书查询游标（毫秒时间戳）
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


# ── partner.yaml 读取 / 校验 ────────────────────────────────────────────

def load_partner(base):
    """返回 (dict|None, err)。yaml 不可用或文件缺失/解析失败时 err 非空。"""
    if yaml is None:
        return None, "PyYAML required to read partner.yaml"
    p = partner_path(base)
    if not os.path.isfile(p):
        return None, f"no partner.yaml at {p}（未启用 3.2 跨仓库协作则忽略）"
    try:
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return None, f"cannot parse partner.yaml: {e}"
    return data, ""


def partner_errors(data):
    """校验协作必需字段，返回缺失项列表（空 = 齐）。"""
    errs = []
    if not isinstance(data, dict):
        return ["partner.yaml must be a mapping"]
    collab = data.get("collaboration") or {}
    if collab.get("enabled") is False:
        return []  # 显式关闭协作 → 不要求字段
    partner = data.get("partner") or {}
    if not partner.get("bot"):
        errs.append("partner.bot 缺失（对方 bot 名）")
    if not partner.get("group_id"):
        errs.append("partner.group_id 缺失（双方共同飞书群 chat_id）")
    return errs


def write_partner(data, base):
    """写 <base>/.ai-devflow/partner.yaml。返回 (path|None, err)。"""
    if yaml is None:
        return None, "PyYAML required to write partner.yaml"
    p = partner_path(base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False,
                           default_flow_style=False)
    except OSError as e:
        return None, f"cannot write partner.yaml: {e}"
    return p, ""


# ── 协作消息解析 ────────────────────────────────────────────────────────

def parse_collab_message(text):
    """解析带机器前缀的协作消息 → (task_id, version, action) | None。

    action ∈ request|confirm|reject|drift（按正文关键词判定，容忍空格/换行）。
    """
    if not text:
        return None
    m = MSG_PREFIX_RE.search(text)
    if not m:
        return None
    task_id, version, rest = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    if "契约漂移" in rest:
        action = "drift"
    elif "拒绝" in rest:
        action = "reject"
    elif "确认" in rest:
        action = "confirm"
    else:
        action = "request"
    return {"task_id": task_id, "version": version, "action": action}


# ── 飞书查询（gather 用，可注入） ───────────────────────────────────────

def lark_query(lark_cmd, group_id, cursor_ms):
    """调 lark-cli 查群里消息，返回 (messages:list, err)。

    messages 每个元素含 message_id / create_time / content（content 为 JSON
    字符串，text 字段里携带正文）。实际部署的飞书身份/分页细节在 SKILL 步骤
    接线处按 lark-cli 环境校准；此函数只负责把调用与解析收拢成可测试单元。
    """
    params = {
        "container_id_type": "chat",
        "container_id": group_id,
        "sort_type": "ByCreateTimeAsc",
    }
    if cursor_ms > 0:
        params["start_time"] = str(cursor_ms)
    argv = lark_cmd.split() + [
        "api", "GET", "/open-apis/im/v1/messages",
        "--params", json.dumps(params),
    ]
    try:
        # lark-cli 输出 UTF-8；Windows 下 text=True 默认按 locale(gbk) 解码会炸，
        # 显式 encoding。errors=replace 让个别不可映射字节不致中断解析。
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:
        return [], f"lark query exec failed: {e}"
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout or "").strip()[:500]
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], f"lark query stdout not JSON: {proc.stdout[:200]}"
    # 兼容 items / data.items / data.messages 几种返回外壳
    items = data.get("items") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            items = inner.get("items") or inner.get("messages")
    return items or [], ""


def gather(task_id, base, lark_cmd, feishu_mode):
    """收敛：把群里对 task 的最新"确认版本"写回本地 state。

    返回 (state, notes)。feishu_mode=skip 时只做本地判定，不发起飞书查询
    （游标不推进），供 dry-run / 无飞书凭据环境。
    """
    state = read_state(task_id, base)
    data, perr = load_partner(base)
    group_id = ((data or {}).get("partner") or {}).get("group_id") if data else None
    notes = []
    if perr:
        return state, [f"partner: {perr}"]
    if feishu_mode != "skip":
        if not group_id:
            return state, ["partner.group_id 缺失，跳过飞书查询"]
        messages, err = lark_query(lark_cmd, group_id, state.get("last_cursor_ms") or 0)
        if err:
            return state, [f"feishu query failed: {err}"]
        latest_time = state.get("last_cursor_ms") or 0
        best = None  # 命中本 task 的最新一条确认/拒绝
        for item in messages:
            try:
                t = int(item.get("create_time") or 0)
            except (TypeError, ValueError):
                t = 0
            if t > latest_time:
                latest_time = t
            content = item.get("body", {}).get("content") or item.get("content") or ""
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    content = {"text": content}
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            parsed = parse_collab_message(text)
            if parsed and parsed["task_id"] == task_id and parsed["action"] in ("confirm", "reject"):
                if best is None or (t or 0) >= (best.get("_t") or 0):
                    best = dict(parsed, _t=t)
        if latest_time > (state.get("last_cursor_ms") or 0):
            state["last_cursor_ms"] = latest_time
        if best:
            if best["action"] == "confirm":
                state["status"] = "aligned"
                state["ack_version"] = best["version"]
                state["pending_version"] = None
                notes.append(f"群内确认到 contract {best['version']}")
            else:
                state["status"] = "drifted"
                notes.append("群内最新为拒绝，保持 drifted")
    # 本地判定：state 与 contract.json 是否一致（两种模式都做）
    cp = contract_path(task_id, base)
    if os.path.isfile(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                cdata = json.load(f)
            meta_version = (cdata.get("meta") or {}).get("version")
        except (OSError, json.JSONDecodeError):
            meta_version = None
        if state.get("status") == "aligned" and state.get("ack_version"):
            if meta_version and state["ack_version"] != meta_version:
                notes.append(f"ack_version({state['ack_version']}) != contract meta.version({meta_version})")
    write_state(state, base)
    return state, notes


# ── main ────────────────────────────────────────────────────────────────

def main():
    # 管道输出统一 UTF-8（notes/错误含中文；Windows pipe 默认 locale 会炸）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="partner.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("check")
    sp.add_argument("dir", nargs="?", default=DEFAULT_DIR)

    sp = sub.add_parser("init")
    sp.add_argument("--bot", default=None, help="对方 bot 名（enabled 时必填）")
    sp.add_argument("--group-id", default=None, help="双方共同飞书群 chat_id（enabled 时必填）")
    sp.add_argument("--auto-align", action="store_true", default=None,
                    help="命中'仅需对齐字段'时是否自动发起对齐（默认 false）")
    sp.add_argument("--no-enable", action="store_true",
                    help="写 collaboration.enabled: false（关闭协作，不要求 bot/group_id）")
    sp.add_argument("--force", action="store_true",
                    help="已存在完整 partner.yaml 时也覆盖重建")
    sp.add_argument("--dir", default=DEFAULT_DIR)

    sp = sub.add_parser("state")
    sp.add_argument("task_id")
    sp.add_argument("status")
    sp.add_argument("--ack-version", default=None)
    sp.add_argument("--pending-version", default=None)
    sp.add_argument("--cursor-ms", type=int, default=None)
    sp.add_argument("--dir", default=DEFAULT_DIR)

    sp = sub.add_parser("get")
    sp.add_argument("task_id")
    sp.add_argument("--dir", default=DEFAULT_DIR)

    sp = sub.add_parser("gather")
    sp.add_argument("task_id")
    sp.add_argument("--dir", default=DEFAULT_DIR)

    args = p.parse_args()

    if args.cmd == "check":
        data, err = load_partner(args.dir)
        if err:
            sys.stderr.write(f"partner: {err}\n")
            sys.exit(1)
        errs = partner_errors(data)
        if errs:
            sys.stderr.write("partner: 协作配置不完整:\n  - " + "\n  - ".join(errs) + "\n")
            sys.exit(1)
        bot = (data.get("partner") or {}).get("bot")
        gid = (data.get("partner") or {}).get("group_id")
        print(f"partner: OK partner.bot={bot} group_id={gid}")
        sys.exit(0)

    if args.cmd == "init":
        has_file = os.path.isfile(partner_path(args.dir))
        existing, perr = load_partner(args.dir)
        if perr and has_file and "cannot parse" in perr:
            if not args.force:
                sys.stderr.write("partner: 已有 partner.yaml 解析失败，先手工修正或用 --force 重建\n")
                sys.exit(1)
            existing, perr = None, "rebuilt by --force"
        data = dict(existing) if isinstance(existing, dict) else {}
        collab = dict(data.get("collaboration") or {})
        collab["enabled"] = not args.no_enable
        if args.auto_align is not None:
            collab["auto_align"] = args.auto_align
        elif "auto_align" not in collab:
            collab["auto_align"] = False
        partner = dict(data.get("partner") or {})
        if args.bot:
            partner["bot"] = args.bot
        if args.group_id:
            partner["group_id"] = args.group_id
        data["collaboration"] = collab
        data["partner"] = partner
        if has_file and not args.force and not partner_errors(existing if isinstance(existing, dict) else {}):
            sys.stderr.write("partner: 已有完整 partner.yaml，无需 init；要覆盖请加 --force\n")
            sys.exit(1)
        errs = partner_errors(data)
        if errs:
            sys.stderr.write("partner: init 结果仍不完整:\n  - " + "\n  - ".join(errs) + "\n")
            sys.exit(1)
        wpath, werr = write_partner(data, args.dir)
        if werr:
            sys.stderr.write("partner: " + werr + "\n")
            sys.exit(1)
        print(f"partner: init OK -> {wpath}")
        print(json.dumps(data, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "state":
        if args.status not in STATE_STATUSES:
            sys.stderr.write(f"partner: bad status {args.status!r}; one of {STATE_STATUSES}\n")
            sys.exit(1)
        state = read_state(args.task_id, args.dir)
        state["status"] = args.status
        if args.ack_version is not None:
            state["ack_version"] = args.ack_version
        if args.pending_version is not None:
            state["pending_version"] = args.pending_version
        if args.cursor_ms is not None:
            state["last_cursor_ms"] = args.cursor_ms
        write_state(state, args.dir)
        print(json.dumps(state, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "get":
        print(json.dumps(read_state(args.task_id, args.dir), ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "gather":
        lark_cmd = os.environ.get("LARK_CMD", "lark-cli")
        feishu = os.environ.get("PARTNER_FEISHU", "auto")
        state, notes = gather(args.task_id, args.dir, lark_cmd, feishu)
        out = {"task_id": args.task_id, "status": state.get("status"),
               "ack_version": state.get("ack_version"), "notes": notes}
        print(json.dumps(out, ensure_ascii=False))
        if state.get("status") in ("pending", "drifted"):
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
