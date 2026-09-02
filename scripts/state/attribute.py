#!/usr/bin/env python3
"""attribute.py <verification.json>

Read a verification.json, attribute each failure to an owner
(frontend/backend/test/infra), print a summary JSON.
Exit 0 if no failures, 1 if any failure attributed.

Ported from ai-native/scripts/attribute.py. Added: subtype check first —
verify_runner.py now labels infra failures explicitly (timeout /
infra_exception), so those no longer depend on keyword guessing.
"""
import json
import sys

OWNERS = ("frontend", "backend", "test", "infra")

INFRA_KEYWORDS = (
    "docker", "worktree", "sandbox", "npm install", "pip install",
    "network", "timeout", "permission denied", "connection refused",
    "dns", "disk", "out of memory", "环境", "依赖安装", "端口", "超时", "连接",
)


def owner_of(failure):
    # 环境/基础设施类失败（超时、子进程异常）优先于 owner_hint 直接归 infra，
    # 不再依赖 INFRA_KEYWORDS 关键词猜测——verify_runner 已用 subtype 显式标注。
    if failure.get("subtype") in ("timeout", "infra_exception"):
        return "infra"
    hint = failure.get("owner_hint", "")
    if hint in OWNERS:
        return hint
    criteria = (failure.get("criteria") or "").lower()
    if any(k in criteria for k in INFRA_KEYWORDS):
        return "infra"
    if "e2e" in criteria or "frontend" in criteria:
        return "frontend"
    if "api" in criteria or "backend" in criteria:
        return "backend"
    # "contract" is deliberately NOT bucketed into backend here: a contract
    # gate runs symmetrically in both frontend and backend repos against
    # their own business_code (see scripts/contract_checker.py), so the
    # normal path is verify_runner.guess_owner() setting an explicit
    # owner_hint of "frontend" or "backend" per the failing repo's own
    # stack.type — that hint is already handled above. This fallback only
    # fires when no owner_hint was supplied at all, so it can't tell which
    # side is at fault; default to "test" rather than guessing "backend".
    return "test"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "verification.json"
    try:
        with open(path) as f:
            ver = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"attribute: cannot read {path}: {e}\n")
        sys.exit(2)
    if not isinstance(ver, dict) or not isinstance(ver.get("failures"), list):
        sys.stderr.write("attribute: verification.json must be an object with a 'failures' list\n")
        sys.exit(2)
    failures = ver.get("failures", [])
    attributed = [{**f, "owner": owner_of(f)} for f in failures if isinstance(f, dict)]
    by_owner = {}
    for a in attributed:
        by_owner[a["owner"]] = by_owner.get(a["owner"], 0) + 1
    result = {
        "result": ver.get("result"),
        "repo": ver.get("repo"),
        "total_failures": len(attributed),
        "by_owner": by_owner,
        "failures": attributed,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if not attributed else 1)


if __name__ == "__main__":
    main()
