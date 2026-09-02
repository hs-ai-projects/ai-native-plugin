"""Unit tests for scripts/contract_checker.py: structural validation +
usage cross-check against a repo's own business_code (paths.business_code
from harness.yaml)."""
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


def write_contract(path, endpoints):
    path.write_text(json.dumps({"api": endpoints}))


# ── structural checks (no repo_dir) ──────────────────────────────────────

def test_structural_valid_passes(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/x", "method": "GET"}])
    r = run(c)
    assert r.returncode == 0, r.stderr
    assert "structural only" in r.stdout


def test_structural_missing_api_key_fails(tmp_path):
    c = tmp_path / "contract.json"
    c.write_text(json.dumps({"not_api": []}))
    r = run(c)
    assert r.returncode == 1


def test_structural_endpoint_missing_field_fails(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/x"}])  # missing "method"
    r = run(c)
    assert r.returncode == 1
    assert "missing fields" in r.stderr


def test_invalid_json_fails(tmp_path):
    c = tmp_path / "contract.json"
    c.write_text("{not json")
    r = run(c)
    assert r.returncode == 1


def test_missing_file_fails(tmp_path):
    r = run(tmp_path / "nope.json")
    assert r.returncode == 1


# ── usage cross-check (with repo_dir) ────────────────────────────────────

def make_repo(tmp_path, stack_type, business_code_dirs):
    repo = tmp_path / "repo"
    repo.mkdir()
    harness = {
        "project": {"name": "x", "stack": {"type": stack_type}},
        "paths": {"business_code": business_code_dirs},
    }
    try:
        import yaml
        (repo / "harness.yaml").write_text(yaml.safe_dump(harness))
    except ImportError:
        return None
    return repo


def test_usage_check_skipped_when_business_code_absent(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/register", "method": "POST"}])
    repo = make_repo(tmp_path, "backend", ["app"])
    if repo is None:
        return  # no PyYAML locally; skip like the shell tests do
    r = run(c, repo)
    assert r.returncode == 0, r.stderr
    assert "usage check skipped" in r.stdout


def test_usage_check_skipped_when_business_code_empty_dir(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/register", "method": "POST"}])
    repo = make_repo(tmp_path, "backend", ["app"])
    if repo is None:
        return
    (repo / "app").mkdir()
    r = run(c, repo)
    assert r.returncode == 0, r.stderr
    assert "usage check skipped" in r.stdout


def test_usage_check_fails_when_endpoint_not_referenced(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/register", "method": "POST"}])
    repo = make_repo(tmp_path, "backend", ["app"])
    if repo is None:
        return
    app = repo / "app"
    app.mkdir()
    (app / "main.py").write_text("def other(): pass" + chr(10))
    r = run(c, repo)
    assert r.returncode == 1
    assert "backend" in r.stderr
    assert "/api/register" in r.stderr


def test_usage_check_passes_when_endpoint_referenced(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/register", "method": "POST"}])
    repo = make_repo(tmp_path, "backend", ["app"])
    if repo is None:
        return
    app = repo / "app"
    app.mkdir()
    (app / "main.py").write_text("ROUTE = '/api/register'" + chr(10))
    r = run(c, repo)
    assert r.returncode == 0, r.stderr
    assert "usage verified in backend" in r.stdout


def test_usage_check_attributes_to_frontend_stack_type(tmp_path):
    c = tmp_path / "contract.json"
    write_contract(c, [{"path": "/api/register", "method": "POST"}])
    repo = make_repo(tmp_path, "frontend", ["src"])
    if repo is None:
        return
    src = repo / "src"
    src.mkdir()
    (src / "api.ts").write_text("export const other = 1" + chr(10))
    r = run(c, repo)
    assert r.returncode == 1
    assert "frontend" in r.stderr
