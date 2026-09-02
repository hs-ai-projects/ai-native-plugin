"""Unit tests for scripts/partner.py: partner.yaml check + contract-state 状态机
+ gather 收敛（飞书查询用 fake lark 注入，验证"把群内确认收敛回本地"逻辑）。"""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "partner.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(SCRIPT)))  # allow `import partner`


def run(*args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), *[str(a) for a in args]],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=e,
    )


def write_yaml(path, data):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


# ── partner.yaml check ──────────────────────────────────────────────────

def test_check_missing_partner_fails(tmp_path):
    r = run("check", tmp_path)
    assert r.returncode == 1
    assert "no partner.yaml" in r.stderr


def test_check_valid_passes(tmp_path):
    d = tmp_path / ".ai-devflow"
    write_yaml(d / "partner.yaml", {
        "me": {"bot": "@fe-bot"},
        "partner": {"bot": "@be-bot", "group_id": "oc_1", "contract_dir": ".ai-devflow"},
        "collaboration": {"enabled": True, "auto_align": True},
    })
    r = run("check", tmp_path)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_check_missing_group_id_fails(tmp_path):
    d = tmp_path / ".ai-devflow"
    write_yaml(d / "partner.yaml", {"partner": {"bot": "@be-bot"}})
    r = run("check", tmp_path)
    assert r.returncode == 1
    assert "group_id" in r.stderr


def test_check_disabled_collab_passes_even_if_partner_empty(tmp_path):
    d = tmp_path / ".ai-devflow"
    write_yaml(d / "partner.yaml", {"collaboration": {"enabled": False}})
    r = run("check", tmp_path)
    assert r.returncode == 0, r.stderr


# ── contract-state 状态机 ───────────────────────────────────────────────

def test_state_write_then_get(tmp_path):
    r = run("state", "t1", "pending", "--ack-version", "1.0", "--dir", tmp_path)
    assert r.returncode == 0, r.stderr
    st = json.loads(r.stdout)
    assert st["status"] == "pending" and st["ack_version"] == "1.0"
    r2 = run("get", "t1", "--dir", tmp_path)
    assert json.loads(r2.stdout)["status"] == "pending"


def test_state_bad_status_fails(tmp_path):
    r = run("state", "t1", "nope", "--dir", tmp_path)
    assert r.returncode == 1
    assert "bad status" in r.stderr


def test_get_missing_returns_draft(tmp_path):
    r = run("get", "nope", "--dir", tmp_path)
    assert r.returncode == 0
    assert json.loads(r.stdout)["status"] == "draft"


# ── 协作消息解析 ────────────────────────────────────────────────────────

def test_parse_collab_confirm():
    from partner import parse_collab_message
    p = parse_collab_message("[cc-task t1][contract 1.1] 确认可以接受")
    assert p == {"task_id": "t1", "version": "1.1", "action": "confirm"}


def test_parse_collab_drift_and_reject():
    from partner import parse_collab_message
    assert parse_collab_message("[cc-task t1][contract 1.2] 契约漂移：status 删了，请重新确认")["action"] == "drift"
    assert parse_collab_message("[cc-task t1][contract 1.1] 拒绝：缺 next_step")["action"] == "reject"


def test_parse_no_prefix_none():
    from partner import parse_collab_message
    assert parse_collab_message("普通群消息") is None


# ── gather 收敛（fake lark）─────────────────────────────────────────────

def _fake_lark(tmp_path, text):
    """写一个 fake lark-cli（纯 ASCII 源码，消息从 FAKE_TEXT env 读，避免
    Windows 下子进程源码/print 的编码问题）：输出一条带前缀的协作消息。"""
    fake = tmp_path / "fake_lark.py"
    fake.write_text(
        "import json,os,sys\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "text=os.environ.get('FAKE_TEXT','')\n"
        "items=[{'message_id':'m1','create_time':'1600000000000',\n"
        "        'body':{'content':json.dumps({'text':text},ensure_ascii=False)}}]\n"
        "print(json.dumps({'items':items},ensure_ascii=False))\n"
    )
    return fake


def _make_collab_repo(tmp_path, meta_version="1.1"):
    repo = tmp_path / "repo"
    d = repo / ".ai-devflow"
    write_yaml(d / "partner.yaml", {
        "me": {"bot": "@be-bot"},
        "partner": {"bot": "@fe-bot", "group_id": "oc_9"},
        "collaboration": {"enabled": True},
    })
    (d / "T1").mkdir(parents=True, exist_ok=True)
    (d / "T1" / "contract.json").write_text(json.dumps({
        "api": [{"path": "/api/x", "method": "GET"}],
        "meta": {"version": meta_version},
    }))
    return repo


def test_gather_confirms_and_aligns(tmp_path):
    repo = _make_collab_repo(tmp_path)
    fake = _fake_lark(tmp_path, "[cc-task T1][contract 1.1] 确认")
    r = run("state", "T1", "pending", "--pending-version", "1.1", "--dir", repo)
    assert r.returncode == 0
    r = run("gather", "T1", "--dir", repo,
            env={"LARK_CMD": f"{sys.executable} {fake}", "FAKE_TEXT": "[cc-task T1][contract 1.1] 确认"})
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["status"] == "aligned" and out["ack_version"] == "1.1"
    # state 文件也回写
    st = json.loads((repo / ".ai-devflow/T1/contract-state.json").read_text())
    assert st["ack_version"] == "1.1" and st["status"] == "aligned"
    assert st["last_cursor_ms"] == 1600000000000


def test_gather_reject_keeps_drifted(tmp_path):
    repo = _make_collab_repo(tmp_path)
    fake = _fake_lark(tmp_path, "[cc-task T1][contract 1.2] 拒绝：缺字段")
    run("state", "T1", "drifted", "--pending-version", "1.2", "--dir", repo)
    r = run("gather", "T1", "--dir", repo,
            env={"LARK_CMD": f"{sys.executable} {fake}", "FAKE_TEXT": "[cc-task T1][contract 1.2] 拒绝：缺字段"})
    assert r.returncode == 1  # drifted → 非放行
    out = json.loads(r.stdout)
    assert out["status"] == "drifted"


def test_gather_skip_mode_no_feishu(tmp_path):
    repo = _make_collab_repo(tmp_path)
    # skip 模式：不调飞书，state 仍 pending → exit 1，且 notes 有说明
    run("state", "T1", "pending", "--dir", repo)
    r = run("gather", "T1", "--dir", repo, env={"PARTNER_FEISHU": "skip"})
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["status"] == "pending"
