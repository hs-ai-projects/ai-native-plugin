import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "repair-counter.py")


def run(state_base, task_id, repo, result):
    env = dict(os.environ)
    env["REPAIR_STATE_BASE"] = str(state_base)
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), task_id, repo, result],
        capture_output=True, text=True, env=env,
    )


def test_first_failure_counts_one(tmp_path):
    r = run(tmp_path, "t1", "ads", "FAIL")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out == {"repo": "ads", "consecutive_failures": 1, "escalate": False}


def test_pass_resets_to_zero(tmp_path):
    run(tmp_path, "t1", "ads", "FAIL")
    r = run(tmp_path, "t1", "ads", "PASS")
    out = json.loads(r.stdout)
    assert out["consecutive_failures"] == 0
    assert out["escalate"] is False


def test_third_consecutive_failure_escalates(tmp_path):
    run(tmp_path, "t1", "ads", "FAIL")
    run(tmp_path, "t1", "ads", "FAIL")
    r = run(tmp_path, "t1", "ads", "FAIL")
    out = json.loads(r.stdout)
    assert out["consecutive_failures"] == 3
    assert out["escalate"] is True


def test_counters_are_independent_per_repo(tmp_path):
    run(tmp_path, "t1", "ads", "FAIL")
    run(tmp_path, "t1", "ads", "FAIL")
    r = run(tmp_path, "t1", "ads-web", "FAIL")
    out = json.loads(r.stdout)
    assert out["repo"] == "ads-web"
    assert out["consecutive_failures"] == 1


def test_state_persists_to_json_file(tmp_path):
    run(tmp_path, "t1", "ads", "FAIL")
    state_path = tmp_path / "t1" / "repair-state.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text()) == {"ads": 1}


def test_invalid_result_exits_two(tmp_path):
    r = run(tmp_path, "t1", "ads", "WEIRD")
    assert r.returncode == 2
