"""Unit tests for scripts/contract-align.py: 阶段 0 写对齐快照 contract.json +
置 contract-state.json 为 aligned。"""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "contract-align.py")


def run(*args):
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), *[str(a) for a in args]],
        capture_output=True, text=True,
    )


def test_align_writes_contract_and_state(tmp_path):
    eps = json.dumps([{"path": "/api/claims/{id}/status", "method": "GET",
                       "response": {"fields": ["status", "next_step"]}}])
    r = run("T1", "--endpoints", eps, "--version", "1.0",
            "--aligned-with", "@fe-bot", "--dir", tmp_path)
    assert r.returncode == 0, r.stderr
    c = json.loads((tmp_path / ".ai-devflow/T1/contract.json").read_text())
    assert c["meta"]["version"] == "1.0"
    assert c["meta"]["aligned_with"] == "@fe-bot"
    assert c["api"][0]["path"].endswith("/status")
    assert c["api"][0]["response"]["fields"] == ["status", "next_step"]
    s = json.loads((tmp_path / ".ai-devflow/T1/contract-state.json").read_text())
    assert s["status"] == "aligned" and s["ack_version"] == "1.0"


def test_align_bad_endpoint_missing_method_fails_no_files(tmp_path):
    r = run("T1", "--endpoints", json.dumps([{"path": "/api/x"}]),
            "--dir", tmp_path)
    assert r.returncode == 1
    assert "missing fields" in r.stderr
    assert not (tmp_path / ".ai-devflow/T1/contract.json").exists()


def test_align_non_list_endpoints_fails(tmp_path):
    r = run("T1", "--endpoints", json.dumps({"path": "/api/x"}), "--dir", tmp_path)
    assert r.returncode == 1
    assert "must be a JSON array" in r.stderr


def test_align_bad_json_fails(tmp_path):
    r = run("T1", "--endpoints", "{not json", "--dir", tmp_path)
    assert r.returncode == 1
    assert "bad --endpoints" in r.stderr
