import json
import os
import sqlite3
import subprocess
import sys

SCRIPTS = os.path.join(os.path.dirname(__file__), "..")
TELEMETRY = os.path.join(SCRIPTS, "telemetry")
EMIT = os.path.join(TELEMETRY, "emit-event.py")
LOAD = os.path.join(TELEMETRY, "load-events.py")
ANALYTICS = os.path.join(TELEMETRY, "analytics.py")


def py(*args, **kw):
    env = dict(os.environ)
    env["EVENTS_BASE"] = str(kw.pop("events_base", os.path.dirname(__file__)))
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=env, **kw)


def test_emit_writes_jsonl(tmp_path):
    events = tmp_path / "events"
    r = py(EMIT, "task_created", "--task-id", "t1", "--repo", "ads",
           events_base=events)
    assert r.returncode == 0
    day = os.listdir(events)[0]
    with open(events / day) as f:
        ev = json.loads(f.readline())
    assert ev["type"] == "task_created"
    assert ev["task_id"] == "t1"
    assert ev["repo"] == "ads"
    assert "timestamp" in ev


def test_emit_rejects_unknown_type(tmp_path):
    r = py(EMIT, "nope", "--task-id", "t1", events_base=tmp_path / "e")
    assert r.returncode == 1


def test_load_and_analytics(tmp_path):
    events = tmp_path / "events"
    py(EMIT, "task_created", "--task-id", "t1", "--repo", "ads", events_base=events)
    py(EMIT, "failure_attributed", "--task-id", "t1", "--repo", "ads",
       "--data", '{"owner":"backend"}', events_base=events)
    py(EMIT, "test_result", "--task-id", "t1", "--repo", "ads",
       "--data", '{"result":"FAIL"}', events_base=events)
    py(EMIT, "cost", "--task-id", "t1", "--repo", "ads",
       "--data", '{"input_tokens":100,"output_tokens":50}', events_base=events)
    py(EMIT, "repair_round", "--task-id", "t1", "--repo", "ads", events_base=events)
    py(EMIT, "repair_round", "--task-id", "t1", "--repo", "ads", events_base=events)

    db = tmp_path / "events.db"
    r = py(LOAD, str(events), str(db))
    assert r.returncode == 0
    assert "loaded 6 events" in r.stdout

    r = py(ANALYTICS, str(db), "repair_rounds")
    assert "rounds" in r.stdout
    assert "'rounds': 2" in r.stdout

    r = py(ANALYTICS, str(db), "failure_by_owner")
    assert "backend" in r.stdout

    r = py(ANALYTICS, str(db), "token_usage_total")
    assert "'input_tokens': 100" in r.stdout
    assert "'output_tokens': 50" in r.stdout

    r = py(ANALYTICS, str(db), "failures_by_repo")
    assert "ads" in r.stdout


def test_schema_enum_matches_emit(tmp_path):
    import importlib.util
    schema_path = os.path.join(SCRIPTS, "..", "docs", "telemetry-schema.json")
    with open(os.path.abspath(schema_path)) as f:
        schema = json.load(f)
    spec = importlib.util.spec_from_file_location("emit", os.path.abspath(EMIT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(schema["properties"]["type"]["enum"]) == mod.EVENT_TYPES
