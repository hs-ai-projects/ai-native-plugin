"""check-bands.py 单测：rolling baseline 的 sigma 分级（2σ log / 3σ notify 落文件）。

bands.yaml 由目标仓库自带，故测试在 tmp_path 内写一份 spec 7.10 的示例 bands.yaml 作为
fixture，不依赖插件自带 docs/bands.yaml。
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

try:
    import yaml
except ImportError:
    yaml = None

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "check-bands.py")

BANDS_CONTENT = {
    "metric": "repair_round_count",
    "baseline": {"strategy": "rolling", "window_days": 30},
    "thresholds": {"sigma_2": {"action": "log"}, "sigma_3": {"action": "notify"}},
}


def _fixture_bands(tmp_path):
    p = tmp_path / "bands.yaml"
    p.write_text(yaml.safe_dump(BANDS_CONTENT), encoding="utf-8")
    return str(p)


def make_db(tmp_path, daily_counts):
    """daily_counts: dict of {day_offset_from_today: count}. day_offset=0 is today."""
    db_path = str(tmp_path / "events.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, type TEXT, timestamp TEXT, task_id TEXT, repo TEXT, payload TEXT)")
    today = time.gmtime()
    for offset, count in daily_counts.items():
        day_ts = time.gmtime(time.mktime(today) - offset * 86400)
        day_str = time.strftime("%Y-%m-%d", day_ts)
        for i in range(count):
            conn.execute(
                "INSERT INTO events (type, timestamp, task_id, repo, payload) VALUES (?,?,?,?,?)",
                ("repair_round", f"{day_str}T00:00:0{i}Z", f"t{i}", "repo", "{}"))
    conn.commit()
    conn.close()
    return db_path


def run(db_path, bands_yaml=None, env_extra=None):
    args = [sys.executable, os.path.abspath(SCRIPT), db_path]
    if bands_yaml:
        args.append(bands_yaml)
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(args, capture_output=True, text=True, env=env)


def test_no_table_returns_none_tier(tmp_path):
    db_path = str(tmp_path / "empty.db")
    sqlite3.connect(db_path).close()
    r = run(db_path, _fixture_bands(tmp_path))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["tier"] is None


def test_normal_day_no_tier(tmp_path):
    # baseline 均值 5，今天也是 5 → z=0，不触发任何 tier
    counts = {i: 5 for i in range(1, 31)}
    counts[0] = 5
    db_path = make_db(tmp_path, counts)
    r = run(db_path, _fixture_bands(tmp_path))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["tier"] is None


def test_spike_triggers_sigma_3(tmp_path):
    # baseline 均值 2、标准差小，今天飙到 20 → z-score 远超 3
    counts = {i: 2 for i in range(1, 31)}
    counts[0] = 20
    db_path = make_db(tmp_path, counts)
    alert_dir = tmp_path / "alerts"
    r = run(db_path, _fixture_bands(tmp_path), env_extra={"BANDS_ALERT_DIR": str(alert_dir)})
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["tier"] == "sigma_3"
    assert out["action"] == "notify"
    files = list(alert_dir.glob("*.md"))
    assert len(files) == 1, "3sigma should write exactly one alert file"
    content = files[0].read_text(encoding="utf-8")
    assert "z-score" in content
    assert "人工判断后手动开新任务" in content


def test_insufficient_history_returns_none_tier(tmp_path):
    db_path = make_db(tmp_path, {0: 5})
    r = run(db_path, _fixture_bands(tmp_path))
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["tier"] is None
    assert "insufficient history" in out["reason"]
