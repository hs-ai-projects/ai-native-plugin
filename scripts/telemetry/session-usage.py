#!/usr/bin/env python3
"""session-usage.py report <task_id>

Report the real Claude Code token usage consumed since the last call for
the current session, and save a verbatim copy of that transcript segment
for the task. No network calls, no session_id env var needed (Claude Code
doesn't expose one to subprocesses) — this reads the CLI's own transcript
file directly (~/.claude/projects/*/*.jsonl), picking the most recently
active one whose `cwd` field matches the current working directory.

Cursor state lives at $STATE_BASE/.session-cursors/<hash>.json, keyed by
the transcript's own path (not task_id). Calling this once per task in a
long-running Team Lead session naturally reports only the delta since the
previous call — no separate "start recording" step needed.

Output (stdout, JSON): input_tokens / output_tokens /
cache_creation_input_tokens / cache_read_input_tokens / turn_count /
duration_seconds / transcript_saved_to. Meant to be fed straight into
`emit-event.py cost --data <output>`.

Side effect: writes the raw transcript lines covering this delta to
$STATE_BASE/<task_id>/session-transcript.jsonl (full session detail for
this task, not just the aggregated counts).
"""
import glob
import hashlib
import json
import os
import sys
import time

STATE_BASE = os.environ.get("STATE_BASE", os.path.join(os.getcwd(), ".ai-devflow"))
TRANSCRIPTS_GLOB = os.environ.get(
    "TRANSCRIPTS_GLOB", os.path.expanduser("~/.claude/projects/*/*.jsonl"))
ACTIVE_WINDOW_SECONDS = 600  # 只在最近10分钟内被写过的transcript里找,避免匹配到别的历史session


def _find_current_transcript(cwd):
    """Most recently modified transcript, touched within the active
    window, whose latest `cwd`-bearing line matches the given cwd."""
    now = time.time()
    candidates = []
    for path in glob.glob(TRANSCRIPTS_GLOB):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if now - mtime > ACTIVE_WINDOW_SECONDS:
            continue
        last_cwd = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "cwd" in entry:
                        last_cwd = entry["cwd"]
        except OSError:
            continue
        if last_cwd == cwd:
            candidates.append((mtime, path))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _cursor_path(transcript_path):
    key = hashlib.sha256(transcript_path.encode("utf-8")).hexdigest()[:16]
    d = os.path.join(STATE_BASE, ".session-cursors")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.json")


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "report":
        sys.stderr.write("usage: session-usage.py report <task_id>\n")
        sys.exit(2)
    task_id = sys.argv[2]

    cwd = os.getcwd()
    transcript = _find_current_transcript(cwd)
    if not transcript:
        sys.stderr.write(f"session-usage: no active transcript found for cwd={cwd}\n")
        sys.exit(1)

    cursor_file = _cursor_path(transcript)
    cursor = {}
    if os.path.exists(cursor_file):
        try:
            with open(cursor_file, "r", encoding="utf-8") as f:
                cursor = json.load(f)
        except (OSError, json.JSONDecodeError):
            cursor = {}
    offset = cursor.get("offset", 0)
    since = cursor.get("recorded_at", os.path.getctime(transcript))

    totals = {"input_tokens": 0, "output_tokens": 0,
              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
              "turn_count": 0}
    raw_lines = []
    with open(transcript, "r", encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            raw_lines.append(stripped)
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            usage = (entry.get("message") or {}).get("usage")
            if not usage:
                continue
            totals["input_tokens"] += usage.get("input_tokens", 0)
            totals["output_tokens"] += usage.get("output_tokens", 0)
            totals["cache_creation_input_tokens"] += usage.get("cache_creation_input_tokens", 0)
            totals["cache_read_input_tokens"] += usage.get("cache_read_input_tokens", 0)
            totals["turn_count"] += 1
        new_offset = f.tell()

    totals["duration_seconds"] = round(time.time() - since)

    # 保存这段 delta 对应的完整原始 transcript（任务级别的详细会话记录）
    task_dir = os.path.join(STATE_BASE, task_id)
    os.makedirs(task_dir, exist_ok=True)
    transcript_out = os.path.join(task_dir, "session-transcript.jsonl")
    with open(transcript_out, "w", encoding="utf-8") as f:
        f.write("\n".join(raw_lines))
        if raw_lines:
            f.write("\n")
    totals["transcript_saved_to"] = transcript_out

    with open(cursor_file, "w", encoding="utf-8") as f:
        json.dump({"offset": new_offset, "recorded_at": time.time(),
                    "transcript": transcript}, f)

    print(json.dumps(totals, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
