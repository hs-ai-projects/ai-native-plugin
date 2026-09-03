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
