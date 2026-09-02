#!/usr/bin/env python3
"""analytics.py <db_path> [query]

Run predefined queries over the events DB.
queries: repair_rounds | failure_by_owner | token_usage_total | failures_by_repo | chain | all

chain 用递归 CTE 沿 parent_event_id 重建一条完整事件链路
（task_created → test_result → mr_created → mr_merged，spec 7.11）。
"""
import sqlite3
import sys

QUERIES = {
    "repair_rounds": (
        "SELECT task_id, COUNT(*) AS rounds FROM events "
        "WHERE type='repair_round' GROUP BY task_id"),
    "failure_by_owner": (
        "SELECT json_extract(payload, '$.owner') AS owner, COUNT(*) AS n "
        "FROM events WHERE type='failure_attributed' GROUP BY owner"),
    "token_usage_total": (
        "SELECT "
        "COALESCE(SUM(json_extract(payload, '$.input_tokens')), 0) AS input_tokens, "
        "COALESCE(SUM(json_extract(payload, '$.output_tokens')), 0) AS output_tokens, "
        "COALESCE(SUM(json_extract(payload, '$.cache_creation_input_tokens')), 0) AS cache_creation_input_tokens, "
        "COALESCE(SUM(json_extract(payload, '$.cache_read_input_tokens')), 0) AS cache_read_input_tokens "
        "FROM events WHERE type='cost'"),
    "failures_by_repo": (
        "SELECT repo, COUNT(*) AS n FROM events "
        "WHERE type='test_result' AND json_extract(payload, '$.result')='FAIL' "
        "GROUP BY repo"),
    "chain": (
        "WITH RECURSIVE chain(event_id, parent_event_id, type, task_id, depth) AS ("
        "  SELECT json_extract(payload, '$.event_id'), "
        "         json_extract(payload, '$.parent_event_id'), type, task_id, 0 "
        "  FROM events "
        "  WHERE json_extract(payload, '$.parent_event_id') IS NULL "
        "  UNION ALL "
        "  SELECT json_extract(e.payload, '$.event_id'), "
        "         json_extract(e.payload, '$.parent_event_id'), e.type, e.task_id, c.depth + 1 "
        "  FROM events e JOIN chain c "
        "    ON json_extract(e.payload, '$.parent_event_id') = c.event_id "
        ") SELECT task_id, type, depth FROM chain ORDER BY task_id, depth"),
}


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: analytics.py <db_path> [query]\n")
        sys.exit(2)
    db_path = sys.argv[1]
    q = sys.argv[2] if len(sys.argv) > 2 else "all"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()
    targets = list(QUERIES) if q == "all" else [q]
    if not has_table:
        for name in targets:
            print(f"--- {name} ---")
            print("(no data: db not loaded)")
        conn.close()
        sys.exit(0)
    for name in targets:
        if name not in QUERIES:
            sys.stderr.write(f"unknown query: {name}\n")
            sys.exit(1)
        rows = conn.execute(QUERIES[name]).fetchall()
        print(f"--- {name} ---")
        for r in rows:
            print(dict(r))
    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
