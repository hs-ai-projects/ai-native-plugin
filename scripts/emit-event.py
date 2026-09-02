#!/usr/bin/env python3
"""emit-event.py <event_type> --task-id X [--repo Y] [--data '{"k":v}'] [--parent-event-id Z]

Append a JSONL event to $EVENTS_BASE/<YYYY-MM-DD>.jsonl (default
EVENTS_BASE=<repo>/.ai-devflow/events, i.e. current working directory's
.ai-devflow/events). Event includes type/event_id/parent_event_id/
timestamp/task_id plus any extra keys from --data.

stdout prints the generated event_id so the orchestration Skill can store
it in SPEC chapter 4 Status and thread it as --parent-event-id on the next
emit (spec 7.11).

Ported from ai-native/scripts/emit-event.py; EVENTS_BASE default moved off
the container path /app/.ai-devflow/events.
"""
import argparse
import json
import os
import sys
import time
import uuid

EVENTS_BASE = os.environ.get("EVENTS_BASE", os.path.join(os.getcwd(), ".ai-devflow", "events"))
EVENT_TYPES = {"task_created", "state_change", "test_result",
               "failure_attributed", "repair_round", "mr_created",
               "mr_merged", "cost"}
BASE_KEYS = {"type", "timestamp", "task_id", "repo", "event_id", "parent_event_id"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("event_type")
    p.add_argument("--task-id", required=True)
    p.add_argument("--repo", default="")
    p.add_argument("--data", default="{}")
    p.add_argument("--parent-event-id", default="")
    args = p.parse_args()

    if args.event_type not in EVENT_TYPES:
        sys.stderr.write(f"emit-event: unknown type '{args.event_type}'\n")
        sys.exit(1)
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"emit-event: bad --data: {e}\n")
        sys.exit(1)
    if not isinstance(data, dict):
        sys.stderr.write("emit-event: --data must be a JSON object\n")
        sys.exit(1)
    overlap = BASE_KEYS & set(data.keys())
    if overlap:
        sys.stderr.write(f"emit-event: --data must not override reserved keys: {sorted(overlap)}\n")
        sys.exit(1)

    os.makedirs(EVENTS_BASE, exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    path = os.path.join(EVENTS_BASE, f"{day}.jsonl")
    event = {
        "type": args.event_type,
        "event_id": str(uuid.uuid4()),
        "parent_event_id": args.parent_event_id or None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_id": args.task_id,
        "repo": args.repo,
        **data,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps({"event_id": event["event_id"], "parent_event_id": event["parent_event_id"]},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
