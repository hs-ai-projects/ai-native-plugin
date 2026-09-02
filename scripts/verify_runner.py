#!/usr/bin/env python3
"""verify_runner.py <repo_dir>

Read <repo_dir>/harness.yaml, execute each layer listed in gates.full,
and write .ai-devflow/verification.json (PASS/FAIL). A layer without a
configured command records result=NOT_RUN and does not block.

Result states per layer: PASS / FAIL / NOT_RUN / ERROR. ERROR carries a
subtype (timeout | infra_exception) so attribute.py can attribute infra
failures without keyword guessing. Ported from ai-native/test-harness/lib/
verify_runner.py; plugin paths are repo-relative (.ai-devflow/).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

try:
    import yaml
except ImportError:
    sys.stderr.write("verify_runner: PyYAML required\n")
    sys.exit(2)

# 子进程用哪个 bash：显式解析真实路径，避免 Windows 上 CreateProcess 的搜索顺序
# 先把 System32\\bash.exe（WSL 中继）排在 PATH 前面而选中一个不可用的 WSL bash。
BASH = os.environ.get("VERIFY_BASH") or shutil.which("bash") or "bash"


def read_harness(repo_dir):
    path = os.path.join(repo_dir, "harness.yaml")
    if not os.path.isfile(path):
        sys.stderr.write(f"verify_runner: no harness.yaml in {repo_dir}\n")
        sys.exit(2)
    with open(path) as f:
        return yaml.safe_load(f)


def layer_command(harness, layer):
    stack = harness.get("project", {}).get("stack", {})
    if layer == "unit":
        type_ = stack.get("type", "")
        if type_:
            cmd = stack.get(f"{type_}_unit_cmd", "")
            if cmd:
                return cmd
        return stack.get("frontend_unit_cmd") or stack.get("backend_unit_cmd") or ""
    return stack.get(f"{layer}_cmd", "")


def run_layer(repo_dir, layer, cmd):
    timeout = int(os.environ.get("VERIFY_TIMEOUT_SECONDS", "600"))
    start = time.time()
    if not cmd:
        return {"result": "NOT_RUN", "reason": f"{layer}_cmd not configured", "duration_ms": 0}
    try:
        proc = subprocess.run([BASH, "-c", cmd], cwd=repo_dir,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"result": "ERROR", "subtype": "timeout",
                "reason": f"exceeded {timeout}s",
                "duration_ms": int((time.time() - start) * 1000)}
    except Exception as e:
        return {"result": "ERROR", "subtype": "infra_exception",
                "reason": f"{type(e).__name__}: {e}",
                "duration_ms": int((time.time() - start) * 1000)}
    dur = int((time.time() - start) * 1000)
    return {
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "subtype": "success" if proc.returncode == 0 else "assertion_failed",
        "returncode": proc.returncode,
        "duration_ms": dur,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def guess_owner(layer, harness):
    stack_type = harness.get("project", {}).get("stack", {}).get("type", "")
    # unit AND contract both run inside THIS repo, against THIS repo's own
    # business_code, so a failure here is this repo's own side's fault.
    # (Previously "contract" was hardcoded to "backend", which meant a
    # frontend repo's contract drift always got misrouted to the backend
    # subagent to "fix" — contract failures must be attributed by "which
    # side is missing the field", not blindly to backend.)
    if layer in ("unit", "contract"):
        return stack_type if stack_type in ("frontend", "backend") else "test"
    if layer == "e2e":
        return "frontend"
    if layer == "api":
        # api_cmd hits a running backend interface — always a backend concern.
        return "backend"
    return "test"


def git_commit(repo_dir):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_dir")
    args = parser.parse_args()
    repo_dir = args.repo_dir

    harness = read_harness(repo_dir)
    gates = harness.get("gates", {}).get("full", [])
    out_dir = os.path.join(repo_dir, ".ai-devflow")
    artifacts_dir = os.path.join(out_dir, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)

    tests = {}
    failures = []
    start = time.time()
    for layer in gates:
        cmd = layer_command(harness, layer)
        info = run_layer(repo_dir, layer, cmd)
        tests[layer] = info
        if info["result"] in ("FAIL", "ERROR"):
            ev_file = os.path.join(artifacts_dir, f"{layer}.log")
            with open(ev_file, "w") as f:
                f.write(info.get("stdout_tail", ""))
                f.write("\n---STDERR---\n")
                f.write(info.get("stderr_tail", ""))
            failures.append({
                "criteria": f"{layer} gate failed",
                "owner_hint": guess_owner(layer, harness),
                "subtype": info.get("subtype"),
                "expected": "exit 0",
                "actual": (f'exit {info.get("returncode")}'
                           if info.get("returncode") is not None
                           else info.get("reason", "error")),
                "evidence": {"log": os.path.relpath(ev_file, out_dir)},
            })
    total_ms = int((time.time() - start) * 1000)
    result = "FAIL" if failures else "PASS"
    ver = {
        "result": result,
        "repo": harness.get("project", {}).get("name", repo_dir),
        "commit": git_commit(repo_dir),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": total_ms,
        "tests": tests,
        "failures": failures,
    }
    out_path = os.path.join(out_dir, "verification.json")
    with open(out_path, "w") as f:
        json.dump(ver, f, indent=2)
    summary = {k: v["result"] for k, v in tests.items()}
    print(f"[full-verify] result={result} repo={ver['repo']} tests={json.dumps(summary)}")
    sys.exit(0 if result == "PASS" else 1)


if __name__ == "__main__":
    main()
