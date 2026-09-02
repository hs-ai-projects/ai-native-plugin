"""Unit tests for scripts/contract_checker.py 字段级引用检查（spec 7.15）：
端点声明可选 fields 时，对每个字段名做与 path 相同的 business_code 引用检查；
不声明则退回纯 path 检查（既有行为由 test_contract_checker.py 覆盖）。"""
import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "contract_checker.py")


def run(*args):
    return subprocess.run(
        [sys.executable, os.path.abspath(SCRIPT), *[str(a) for a in args]],
        capture_output=True, text=True,
    )


def make_repo(tmp_path, stack_type="backend", code="ROUTE = '/api/x' status = 'ok'\n"):
    repo = tmp_path / "repo"
    repo.mkdir()
    harness = {
        "project": {"name": "x", "stack": {"type": stack_type}},
        "paths": {"business_code": ["app"]},
    }
    import yaml
    (repo / "harness.yaml").write_text(yaml.safe_dump(harness))
    (repo / "app").mkdir()
    (repo / "app" / "main.py").write_text(code)
    return repo


def write_contract(path, endpoints):
    path.write_text(json.dumps({"api": endpoints}))


def test_field_referenced_passes(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/x", "method": "GET", "fields": ["status", "ok"]}])
    repo = make_repo(tmp_path)
    r = run(c, repo)
    assert r.returncode == 0, r.stderr
    assert "usage verified" in r.stdout


def test_field_missing_fails(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/x", "method": "GET",
                        "response": {"fields": ["status", "vanished_field"]}}])
    repo = make_repo(tmp_path)  # code 里没有 vanished_field
    r = run(c, repo)
    assert r.returncode == 1
    assert "vanished_field" in r.stderr
    assert "backend" in r.stderr


def test_no_fields_declared_still_checks_path(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/gone", "method": "GET"}])
    repo = make_repo(tmp_path)
    r = run(c, repo)
    assert r.returncode == 1
    assert "/api/gone" in r.stderr
