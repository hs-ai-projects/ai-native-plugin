#!/usr/bin/env python3
"""contract_checker.py <contract_file> [repo_dir]

Two checks, run in order:

1. Structural validation of contract_file: must be an object with an "api"
   array; each endpoint must declare path + method. Always runs.

2. Usage cross-check (only when [repo_dir] is given and repo_dir/harness.yaml
   declares a non-empty, existing paths.business_code): for each contract
   endpoint, verify its "path" string is actually referenced somewhere under
   this repo's own business_code. This is what makes the layer catch real
   contract drift ("路径在契约里，代码里却没有/不再实现") instead of only
   confirming contract.json itself is well-formed — a repo could otherwise
   ship a perfectly valid contract.json that nothing in the codebase honors,
   and this check would never notice.

   The failure is attributed to *this* repo's own stack.type (frontend or
   backend) via test-harness/lib/verify_runner.py's guess_owner(), since the
   check only ever inspects this repo's own business_code — see
   EXECUTION-PLAN Phase 4.2 ("contract 失败→看字段缺失方").

   If business_code is missing/empty (project hasn't implemented anything
   yet, e.g. the harness-adapters/* samples in this framework repo), the
   usage cross-check is skipped and only the structural check applies — a
   fresh scaffold must stay green.

Exit 0 on valid (and, when checked, fully referenced), 1 otherwise.
"""
import json
import os
import sys

REQUIRED = {"path", "method"}


def load_contract(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"contract_checker: cannot read {path}: {e}\n")
        sys.exit(1)


def validate_structure(data):
    if not isinstance(data, dict) or "api" not in data:
        sys.stderr.write("contract_checker: must be an object with 'api' list\n")
        sys.exit(1)
    if not isinstance(data["api"], list):
        sys.stderr.write("contract_checker: 'api' must be a list\n")
        sys.exit(1)
    for i, ep in enumerate(data["api"]):
        if not isinstance(ep, dict):
            sys.stderr.write(f"contract_checker: api[{i}] must be an object\n")
            sys.exit(1)
        missing = REQUIRED - set(ep.keys())
        if missing:
            sys.stderr.write(f"contract_checker: api[{i}] missing fields: {sorted(missing)}\n")
            sys.exit(1)


def load_repo_context(repo_dir):
    """Return (stack_type, [existing non-empty business_code dirs]) or (None, [])."""
    harness_path = os.path.join(repo_dir, "harness.yaml")
    if not os.path.isfile(harness_path):
        return None, []
    try:
        import yaml
    except ImportError:
        sys.stderr.write("contract_checker: PyYAML required for usage cross-check, skipping\n")
        return None, []
    try:
        with open(harness_path) as f:
            harness = yaml.safe_load(f) or {}
    except Exception as e:
        sys.stderr.write(f"contract_checker: cannot read harness.yaml: {e}, skipping usage check\n")
        return None, []
    stack_type = harness.get("project", {}).get("stack", {}).get("type")
    biz_rel = harness.get("paths", {}).get("business_code", [])
    biz_dirs = []
    for d in biz_rel:
        abs_d = os.path.join(repo_dir, d)
        if os.path.isdir(abs_d) and any(os.scandir(abs_d)):
            biz_dirs.append(abs_d)
    return stack_type, biz_dirs


def path_referenced(path, biz_dirs):
    for base in biz_dirs:
        for root, _dirs, files in os.walk(base):
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as fh:
                        if path in fh.read():
                            return True
                except OSError:
                    continue
    return False


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: contract_checker.py <contract_file> [repo_dir]\n")
        sys.exit(1)
    contract_path = sys.argv[1]
    repo_dir = sys.argv[2] if len(sys.argv) > 2 else None

    data = load_contract(contract_path)
    validate_structure(data)
    endpoints = data["api"]

    if not repo_dir:
        print(f"contract_checker: OK ({len(endpoints)} endpoints; structural only, no repo_dir given)")
        sys.exit(0)

    stack_type, biz_dirs = load_repo_context(repo_dir)
    if not biz_dirs:
        print(f"contract_checker: OK ({len(endpoints)} endpoints; business_code empty/absent, usage check skipped)")
        sys.exit(0)

    missing = [ep["path"] for ep in endpoints if not path_referenced(ep["path"], biz_dirs)]
    if missing:
        side = stack_type if stack_type in ("frontend", "backend") else "unknown"
        sys.stderr.write(
            f"contract_checker: {side} business_code does not reference {len(missing)} "
            f"contract endpoint(s): {missing}\n"
        )
        sys.exit(1)

    print(f"contract_checker: OK ({len(endpoints)} endpoints; usage verified in {stack_type} business_code)")
    sys.exit(0)


if __name__ == "__main__":
    main()
