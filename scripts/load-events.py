#!/usr/bin/env python3
"""load-events.py <events_dir> <db_path>

Load all *.jsonl events into a SQLite DB (table `events`). Idempotent:
re-running drops and re-inserts (load is a full sync from JSONL).
"""
import glob
import json
import os
import sqlite3
import sys

BASE_KEYS = {"type", "timestamp", "task_id", "repo"}


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: load-events.py <events_dir> <db_path>\n")
        sys.exit(2)
    events_dir, db_path = sys.argv[1], sys.argv[2]

    if not os.path.isdir(events_dir):
        sys.stderr.write(f"load-events: no such dir: {events_dir}\n")
        sys.exit(2)

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS events")
    conn.execute("""CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        type TEXT, timestamp TEXT, task_id TEXT, repo TEXT, payload TEXT)""")
    conn.execute("CREATE INDEX idx_events_type ON events(type)")
    conn.execute("CREATE INDEX idx_events_task ON events(task_id)")

    count = 0
    for path in sorted(glob.glob(os.path.join(events_dir, "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = {k: v for k, v in ev.items() if k not in BASE_KEYS}
                conn.execute(
                    "INSERT INTO events (type, timestamp, task_id, repo, payload) VALUES (?,?,?,?,?)",
                    (ev.get("type"), ev.get("timestamp"), ev.get("task_id"),
                     ev.get("repo"), json.dumps(payload, ensure_ascii=False)))
                count += 1
    conn.commit()
    conn.close()
    print(f"loaded {count} events into {db_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
