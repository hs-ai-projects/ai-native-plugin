#!/usr/bin/env python3
"""Keep task context and conversation backlinks without choosing a development flow."""
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

STATE_DIR = (Path("/root/data/feishu-task-state") if Path.home() == Path("/root") else
             Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) /
             "ai-native-plugin/feishu-task-state")
INTERVAL = 10
RETENTION_SECONDS = 15 * 24 * 60 * 60


def task_ids(prompt):
    result = []
    for url in re.findall(r'https://applink\.feishu\.cn/client/todo/(?:detail|task)\?[^\s<>"\')]+', html.unescape(prompt)):
        try:
            task_id = str(UUID(parse_qs(urlsplit(url).query)["guid"][0]))
        except (KeyError, ValueError):
            continue
        if task_id not in result:
            result.append(task_id)
    return result


def run_cli(args):
    try:
        result = subprocess.run(["lark-cli", *args, "--as", "bot", "--format", "json"],
                                capture_output=True, text=True, timeout=10)
        response = json.loads(result.stdout)
        if result.returncode == 0 and response.get("ok") is True:
            return response
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def find_message_link(value):
    if isinstance(value, dict):
        link = value.get("message_app_link")
        if isinstance(link, str) and link.startswith("https://"):
            return link
        for child in value.values():
            link = find_message_link(child)
            if link:
                return link
    elif isinstance(value, list):
        for child in value:
            link = find_message_link(child)
            if link:
                return link
    return None


def save(handle, value):
    handle.seek(0)
    json.dump(value, handle, ensure_ascii=False)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def linkback(task_id, message_id, receipt):
    with os.fdopen(os.open(receipt, os.O_RDWR | os.O_CREAT, 0o600), "r+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        handle.seek(0)
        if handle.read():
            return
        response = run_cli(["im", "+messages-mget", "--message-ids", message_id])
        link = find_message_link(response)
        if not link:
            return  # No write attempted; a later reminder may retry the lookup.
        # Persist uncertainty before the write: interruption must not duplicate a comment.
        save(handle, {"status": "unconfirmed", "url": link})
        response = run_cli(["task", "+comment", "--task-id", task_id,
                            "--content", "关联会话：" + link])
        if response:
            save(handle, {"status": "posted", "url": link})


def launch_linkback(task_id, message_id, receipt):
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--linkback",
                      task_id, message_id, str(receipt)], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reminder(data):
    prompt = data.get("prompt", "")
    sid = data.get("session_id") or os.environ.get("CC_SESSION_KEY")
    if not isinstance(prompt, str) or not sid:
        return ""
    key = hashlib.sha256(str(sid).encode()).hexdigest()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for path in STATE_DIR.iterdir():
        if path.suffix in {".state", ".link"}:
            try:
                if time.time() - path.stat().st_mtime > RETENTION_SECONDS:
                    raw = path.read_text() if path.suffix == ".link" else ""
                    if raw:
                        try:
                            if json.loads(raw).get("status") != "posted":
                                continue
                        except ValueError:
                            continue
                    path.unlink()
            except OSError:
                pass
    state_path = STATE_DIR / f"{key}.state"
    with os.fdopen(os.open(state_path, os.O_RDWR | os.O_CREAT, 0o600), "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        try:
            state = json.load(handle)
        except ValueError:
            state = {}
        current = task_ids(prompt)
        if current:
            state = {"tasks": current, "count": 0}
        elif state.get("tasks"):
            state["count"] = state.get("count", 0) + 1
        else:
            return ""
        save(handle, state)
        if state["count"] % INTERVAL:
            return ""
    text = (f"关联飞书任务：{', '.join(state['tasks'])}。"
            "请按实际进展同步任务。")
    session = os.environ.get("CC_SESSION_KEY", "")
    message_id = session.rsplit(":", 1)[-1] if session.startswith("feishu:") else ""
    if message_id:
        for task_id in state["tasks"]:
            receipt = STATE_DIR / f"{key}-{task_id}.link"
            try:
                raw = receipt.read_text()
                status = json.loads(raw).get("status") if raw else None
                if status:
                    receipt.touch()
            except OSError:
                status = None
            except ValueError:
                status = "unconfirmed"
            if status == "unconfirmed":
                text += f" 任务 {task_id} 的会话回链未确认；先核对任务评论，避免重复写入。"
            elif status != "posted":
                try:
                    launch_linkback(task_id, message_id, receipt)
                except OSError:
                    text += f" 任务 {task_id} 的会话回链未启动。"
    return text


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--linkback":
        linkback(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
        return
    try:
        data = json.load(sys.stdin)
        text = reminder(data) if isinstance(data, dict) else ""
        if text:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": text
            }}, ensure_ascii=False))
    except (OSError, ValueError):
        print("飞书任务提醒不可用；任务进展请按 tracker 约定维护。", file=sys.stderr)


if __name__ == "__main__":
    main()
