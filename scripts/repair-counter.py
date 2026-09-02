#!/usr/bin/env python3
"""repair-counter.py <task_id> <repo> <PASS|FAIL>

Track consecutive repair-round failures per (task_id, repo) in a JSON
state file at $REPAIR_STATE_BASE/<task_id>/repair-state.json (default
REPAIR_STATE_BASE=<repo>/.ai-devflow, i.e. the current working
directory's .ai-devflow).

FAIL increments the counter; PASS resets it to 0. Prints the updated
state as JSON: {"repo": ..., "consecutive_failures": N, "escalate": bool}.
escalate is true once consecutive_failures reaches 3 (Team Lead should
stop repairing and escalate to a human at that point).

Ported from ai-native/scripts/repair-counter.py; default STATE_BASE moved
from the container path /app/.ai-devflow to a repo-relative .ai-devflow.
"""
import json
import os
import sys

STATE_BASE = os.environ.get("REPAIR_STATE_BASE", os.path.join(os.getcwd(), ".ai-devflow"))
ESCALATE_THRESHOLD = 3


def main():
    if len(sys.argv) != 4:
        sys.stderr.write("usage: repair-counter.py <task_id> <repo> <PASS|FAIL>\n")
        sys.exit(2)
    task_id, repo, result = sys.argv[1], sys.argv[2], sys.argv[3].upper()
    if result not in ("PASS", "FAIL"):
        sys.stderr.write(f"repair-counter: result must be PASS or FAIL, got '{result}'\n")
        sys.exit(2)

    state_dir = os.path.join(STATE_BASE, task_id)
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "repair-state.json")

    state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            state = {}
    if not isinstance(state, dict):
        state = {}

    count = (state.get(repo, 0) + 1) if result == "FAIL" else 0
    state[repo] = count

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "repo": repo,
        "consecutive_failures": count,
        "escalate": count >= ESCALATE_THRESHOLD,
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
