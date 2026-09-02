import json
import os
import subprocess
import sys

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "attribute.py")


def run(tmp_path, failures):
    ver = {"result": "FAIL" if failures else "PASS", "repo": "x", "failures": failures}
    p = tmp_path / "verification.json"
    p.write_text(json.dumps(ver))
    r = subprocess.run([sys.executable, os.path.abspath(SCRIPT), str(p)],
                       capture_output=True, text=True)
    return r


def test_no_failures_exit_zero(tmp_path):
    r = run(tmp_path, [])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["total_failures"] == 0


def test_owner_hint_priority(tmp_path):
    r = run(tmp_path, [{"owner_hint": "backend", "criteria": "unit gate failed"}])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["failures"][0]["owner"] == "backend"
    assert out["by_owner"] == {"backend": 1}


def test_criteria_fallback(tmp_path):
    r = run(tmp_path, [{"criteria": "e2e gate failed", "expected": "0", "actual": "1"}])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["failures"][0]["owner"] == "frontend"


def test_missing_file_exit_two(tmp_path):
    r = subprocess.run([sys.executable, os.path.abspath(SCRIPT), str(tmp_path / "nope.json")],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_invalid_json_exit_two(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    r = subprocess.run([sys.executable, os.path.abspath(SCRIPT), str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 2


def test_infra_hint_passthrough(tmp_path):
    r = run(tmp_path, [{"owner_hint": "infra", "criteria": "env broken"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "infra"


def test_infra_auto_detect_from_criteria(tmp_path):
    r = run(tmp_path, [{"criteria": "docker worktree add failed"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "infra"


def test_multi_failure_aggregation(tmp_path):
    r = run(tmp_path, [{"owner_hint": "frontend"}, {"owner_hint": "backend"}, {"criteria": "e2e gate failed"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["by_owner"] == {"frontend": 2, "backend": 1}


def test_contract_owner_hint_respects_stack_side(tmp_path):
    # verify_runner.guess_owner() now sets owner_hint to the failing repo's
    # own stack.type for contract failures (frontend or backend), not a
    # hardcoded "backend" — attribute.py must just pass that hint through.
    r = run(tmp_path, [{"owner_hint": "frontend", "criteria": "contract gate failed"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "frontend"


def test_contract_criteria_fallback_does_not_assume_backend(tmp_path):
    # Without an owner_hint at all, "contract" in the criteria text must not
    # be blindly bucketed into "backend" — see scripts/attribute.py comment.
    r = run(tmp_path, [{"criteria": "contract gate failed", "expected": "0", "actual": "1"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "test"


def test_subtype_error_maps_to_infra_even_with_owner_hint(tmp_path):
    # timeout / infra_exception 是环境问题，即使 owner_hint 写了业务侧也必须归 infra。
    r = run(tmp_path, [{"owner_hint": "frontend", "criteria": "unit gate failed", "subtype": "timeout"}])
    assert r.returncode == 1
    assert json.loads(r.stdout)["failures"][0]["owner"] == "infra"
