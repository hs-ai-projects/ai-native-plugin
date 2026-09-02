#!/usr/bin/env python3
"""check-bands.py <db_path> [bands_yaml]

Read bands.yaml, compute today's metric value vs a rolling baseline
from the events DB (loaded by load-events.py), and print which sigma
tier (if any) was crossed. Read-only diagnostic — does not create PRs or
new intent.md automatically; 3sigma only writes a notify file under
BANDS_ALERT_DIR for a human to triage (see bands.yaml comment).

Default bands_yaml is <repo>/.ai-devflow 同级仓库的 docs/bands.yaml ——
bands.yaml 由目标仓库自带（spec 7.10），非插件文件。
"""
import json
import os
import sqlite3
import statistics
import sys
import time

try:
    import yaml
except ImportError:
    sys.stderr.write("check-bands: PyYAML required\n")
    sys.exit(2)

METRIC_QUERIES = {
    "repair_round_count": (
        "SELECT substr(timestamp, 1, 10) AS day, COUNT(*) AS n "
        "FROM events WHERE type='repair_round' "
        "GROUP BY day ORDER BY day"),
}


def load_bands(path):
    with open(path) as f:
        return yaml.safe_load(f)


def daily_series(conn, metric):
    query = METRIC_QUERIES.get(metric)
    if not query:
        sys.stderr.write(f"check-bands: unknown metric '{metric}'\n")
        sys.exit(2)
    rows = conn.execute(query).fetchall()
    return {day: n for day, n in rows}


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: check-bands.py <db_path> [bands_yaml]\n")
        sys.exit(2)
    db_path = sys.argv[1]
    bands_path = sys.argv[2] if len(sys.argv) > 2 else "docs/bands.yaml"

    bands = load_bands(bands_path)
    metric = bands["metric"]
    window_days = bands.get("baseline", {}).get("window_days", 30)

    conn = sqlite3.connect(db_path)
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()
    if not has_table:
        print(json.dumps({"tier": None, "reason": "no data: db not loaded"}))
        sys.exit(0)

    series = daily_series(conn, metric)
    days_sorted = sorted(series.keys())
    if len(days_sorted) < 2:
        print(json.dumps({"tier": None, "reason": "insufficient history"}))
        sys.exit(0)

    today = days_sorted[-1]
    baseline_days = days_sorted[max(0, len(days_sorted) - 1 - window_days):-1]
    baseline_values = [series[d] for d in baseline_days]
    today_value = series[today]

    mean = statistics.mean(baseline_values)
    stdev = statistics.pstdev(baseline_values) if len(baseline_values) > 1 else 0.0

    if stdev == 0:
        z = 0.0 if today_value == mean else float("inf")
    else:
        z = (today_value - mean) / stdev

    thresholds = bands.get("thresholds", {})
    tier = None
    action = None
    if z != float("inf") and abs(z) >= 3 and "sigma_3" in thresholds:
        tier, action = "sigma_3", thresholds["sigma_3"]["action"]
    elif z == float("inf") and "sigma_3" in thresholds:
        tier, action = "sigma_3", thresholds["sigma_3"]["action"]
    elif z != float("inf") and abs(z) >= 2 and "sigma_2" in thresholds:
        tier, action = "sigma_2", thresholds["sigma_2"]["action"]

    result = {
        "metric": metric,
        "today": today,
        "today_value": today_value,
        "baseline_mean": round(mean, 2),
        "baseline_stdev": round(stdev, 2),
        "z_score": round(z, 2) if z != float("inf") else "inf",
        "tier": tier,
        "action": action,
    }
    print(json.dumps(result))

    if tier == "sigma_3":
        notify_dir = os.environ.get("BANDS_ALERT_DIR", os.path.join(os.getcwd(), ".ai-devflow", "bands-alerts"))
        os.makedirs(notify_dir, exist_ok=True)
        alert_path = os.path.join(notify_dir, f"{today}.md")
        with open(alert_path, "w", encoding="utf-8") as f:
            f.write(f"# Bands Alert: {metric}\n\n")
            f.write(f"- 日期：{today}\n")
            f.write(f"- 当日值：{today_value}（{window_days} 天基线均值 {mean:.2f}，标准差 {stdev:.2f}）\n")
            f.write(f"- z-score：{result['z_score']}（触发 3sigma）\n\n")
            f.write("人工判断后手动开新任务（本工具不自动生成 intent.md）。\n")
        print(f"[check-bands] 3sigma alert written: {alert_path}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
