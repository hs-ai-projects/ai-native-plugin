#!/usr/bin/env python3
# feishu-task-reminder.py
# UserPromptSubmit hook: 检测飞书任务链接，命中后每 10 条消息重复注入分组流转规则。
# 输出注入上下文；总是 exit 0，不阻断任何输入。
#
# 多会话隔离：状态按 session_id 分文件存。
# 防膨胀：状态文件 mtime 超 15 天懒删除。

import sys
import os
import json
import time
import re
import subprocess

CLEANUP_SECONDS = 1296000  # 状态文件 mtime 超 15 天删除，防无限膨胀
INTERVAL = 10  # armed 后每 10 条消息提醒一次
MATCH = "https://applink.feishu.cn/client/todo/detail"
STATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "feishu-task-state"
)

RULE = """\
<feishu-task-rule>
【飞书任务分组流转规则（强制遵守）】
任务分组：待办 / 进行中 / 待审核 / 待验证
- 待办 → 进行中：领取到任务即进入进行中
- → 待审核：方案或权限需要审核时
- → 待验证：代码提交了合并请求或已提交到分支
到对应阶段必须把任务移到对应分组。
</feishu-task-rule>
"""

# 任务链接格式: https://applink.feishu.cn/client/todo/detail?guid=<task_id>
_TASK_URL_RE = re.compile(
    r"https://applink\.feishu\.cn/client/todo/detail\?[^\"\s<]*guid=([A-Za-z0-9_.-]+)"
)


def extract_task_id(prompt):
    """从 prompt 中的飞书任务链接提取 task_id（guid 参数）。"""
    m = _TASK_URL_RE.search(prompt)
    return m.group(1) if m else None


def session_message_id():
    """从 CC_SESSION_KEY 取 message_id。格式: feishu:<chat_id>:<thread>:<message_id>"""
    key = os.environ.get("CC_SESSION_KEY", "")
    if not key.startswith("feishu:"):
        return None
    # 冒号可能出现在 chat_id/thread 内，统一取最后一段
    return key.rsplit(":", 1)[-1] or None


def run_lark_cli(args):
    """执行 lark-cli，返回 (stdout, err)。失败时 stdout 为 None。"""
    try:
        r = subprocess.run(
            ["lark-cli"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        return None, str(e)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout, None


def _find_app_link(obj):
    """递归在 lark-cli JSON 输出中查找 message_app_link。"""
    if isinstance(obj, dict):
        v = obj.get("message_app_link")
        if isinstance(v, str) and v:
            return v
        for val in obj.values():
            found = _find_app_link(val)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_app_link(item)
            if found:
                return found
    return None


def _do_linkback(task_id):
    """静默取当前会话链接并贴到任务评论，结果不反馈。"""
    message_id = session_message_id()
    if not message_id:
        return
    out, err = run_lark_cli(
        [
            "im",
            "+messages-mget",
            "--message-ids",
            message_id,
            "--as",
            "bot",
            "--format",
            "json",
        ]
    )
    if out is None:
        return
    try:
        data = json.loads(out)
    except ValueError:
        return
    link = _find_app_link(data)
    if not link:
        return
    run_lark_cli(
        [
            "task",
            "+comment",
            "--task-id",
            task_id,
            "--content",
            "任务处理会话：" + link,
            "--as",
            "bot",
        ]
    )


def post_linkback(task_id):
    """fork 子进程静默贴链接，父进程立即返回，不阻塞 RULE 注入。

    子进程 setsid 脱离父进程会话组：hook（父进程）被 kill 时子进程不受影响。
    fd 重定向到 devnull：避免子进程共享父进程 stdout 污染 hook 输出。
    子进程执行完毕以 os._exit 退出，不触发 atexit / 缓冲区 flush（父进程资源不应被子进程重复释放）。
    """
    try:
        pid = os.fork()
    except OSError:
        return False
    if pid == 0:
        # 子进程
        try:
            os.setsid()
            devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull, 0)
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
            _do_linkback(task_id)
        except Exception:
            pass
        finally:
            os._exit(0)
    return True


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    prompt = data.get("prompt", "")
    sid = data.get("session_id", "") or "unknown"
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)

    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, sid + ".state")

    # 懒清理过期状态文件（只删 mtime 超阈值的，活跃文件保留）
    now_c = time.time()
    try:
        for name in os.listdir(STATE_DIR):
            if not (name.endswith(".state") or name.endswith(".err")):
                continue
            p = os.path.join(STATE_DIR, name)
            try:
                if now_c - os.path.getmtime(p) > CLEANUP_SECONDS:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass

    # 读当前 session 状态
    state = {"armed": False, "count": 0, "ts": 0}
    try:
        with open(state_path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass

    now = time.time()
    emit = ""

    if MATCH in prompt:
        # 新任务链接：武装并重置计数，本次注入
        state["armed"] = True
        state["count"] = 0
        # 固定逻辑：异步取会话链接贴到任务评论（后台静默跑，不阻塞 RULE 注入，成功失败均不反馈）；
        # 同一任务仅派发一次，避免刷屏
        task_id = extract_task_id(prompt)
        if task_id and task_id not in state.get("posted", []):
            if post_linkback(task_id):
                state.setdefault("posted", []).append(task_id)
        emit = RULE
    elif state.get("armed"):
        state["count"] = state.get("count", 0) + 1
        if state["count"] % INTERVAL == 0:
            emit = RULE

    state["ts"] = now
    if state["armed"] or state["count"] > 0:
        try:
            with open(state_path, "w") as f:
                json.dump(state, f)
        except OSError:
            pass

    if emit:
        sys.stdout.write(emit)


if __name__ == "__main__":
    main()
