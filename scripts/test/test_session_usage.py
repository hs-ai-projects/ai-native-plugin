import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "telemetry", "session-usage.py")


def _write_transcript(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _usage_line(cwd, input_tokens, output_tokens):
    return {
        "cwd": cwd,
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }


def run(home, state_base, cwd, task_id):
    env = dict(os.environ)
    env["STATE_BASE"] = str(state_base)
    env["TRANSCRIPTS_GLOB"] = str(home / ".claude" / "projects" / "*" / "*.jsonl")
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), "report", task_id],
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )


def test_report_sums_usage_since_start(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "app"
    os.makedirs(cwd, exist_ok=True)
    transcript = home / ".claude" / "projects" / "fakeproj" / "session1.jsonl"
    _write_transcript(transcript, [
        _usage_line(str(cwd), 100, 20),
        _usage_line(str(cwd), 50, 10),
    ])

    state_base = tmp_path / "state"
    r = run(home, state_base, cwd, "task-1")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["input_tokens"] == 150
    assert out["output_tokens"] == 30
    assert out["turn_count"] == 2

    saved = state_base / "task-1" / "session-transcript.jsonl"
    assert saved.exists()
    assert len(saved.read_text().strip().splitlines()) == 2


def test_second_task_only_counts_delta(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "app"
    os.makedirs(cwd, exist_ok=True)
    transcript = home / ".claude" / "projects" / "fakeproj" / "session1.jsonl"
    _write_transcript(transcript, [_usage_line(str(cwd), 100, 20)])

    state_base = tmp_path / "state"
    run(home, state_base, cwd, "task-1")

    # 同一个 transcript 文件继续追加（模拟同一 session 里的第二个任务）
    with open(transcript, "a", encoding="utf-8") as f:
        f.write(json.dumps(_usage_line(str(cwd), 5, 5), ensure_ascii=False) + "\n")

    r = run(home, state_base, cwd, "task-2")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    # 只应统计 task-1 结束之后新增的这一行，不应把 task-1 的 100/20 也算进来
    assert out["input_tokens"] == 5
    assert out["output_tokens"] == 5
    assert out["turn_count"] == 1


def test_no_matching_transcript_exits_one(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "app"
    os.makedirs(cwd, exist_ok=True)
    # transcript 存在，但 cwd 不匹配
    transcript = home / ".claude" / "projects" / "fakeproj" / "session1.jsonl"
    _write_transcript(transcript, [_usage_line("/somewhere/else", 100, 20)])

    r = run(home, tmp_path / "state", cwd, "task-1")
    assert r.returncode == 1
