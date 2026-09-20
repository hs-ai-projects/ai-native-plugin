#!/usr/bin/env python3
# feishu-task-reminder.py
# UserPromptSubmit hook: 检测飞书任务链接，命中后每 10 条消息重复注入规则。
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

STATUS_RULE = """\
<feishu-status-rule>
【飞书任务状态流转规则（强制遵守，不可跳过、不可自行省略回写）】
先加载 `devflow` skill。任务自定义字段「状态」是流转的唯一依据，到对应阶段必须
把「状态」改到对应值——完整流转表见该 skill 下 `state-transitions.md`，以其为准，
此处不重复列。
</feishu-status-rule>
"""

# 贴到任务评论区的会话链接前缀。按阶段区分，方便翻任务时看出这条会话在哪个阶段。
LINKBACK_PREFIX = {"dev": "任务处理会话：", "intent": "Intent 阶段会话："}

# 判定用的字段名与选项名。不写死 GUID —— 字段/选项 GUID 是按租户生成的，
# 跨环境会变，只有名字是稳定的。取不到时按「不命中」处理，退回普通 devflow。
FIELD_TYPE = "任务类型"
FIELD_STATUS = "状态"
TYPE_VALUE = "需求"
STATUS_VALUE = "待评审"

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


def _option_name(field_guid, option_guid, cache):
    """把 single_select 的选项 GUID 翻成选项名。失败返回 None。"""
    if field_guid in cache:
        options = cache[field_guid]
    else:
        out, _ = run_lark_cli(
            [
                "task",
                "custom_fields",
                "get",
                "--custom-field-guid",
                field_guid,
                "--as",
                "bot",
                "--format",
                "json",
            ]
        )
        if out is None:
            return None
        try:
            options = json.loads(out)["data"]["custom_field"]["single_select_setting"][
                "options"
            ]
        except (ValueError, KeyError, TypeError):
            return None
        cache[field_guid] = options
    for opt in options:
        if opt.get("guid") == option_guid:
            return opt.get("name")
    return None


def is_intent_task(task_id):
    """任务是否「任务类型=需求 且 状态=待评审」。

    返回 True 命中、False 不命中、None 查不到（按不命中处理，退回普通 devflow——
    宁可漏进 intent 流程，也不要因为接口报错把无关任务误判成需求）。
    """
    out, _ = run_lark_cli(
        [
            "task",
            "tasks",
            "get",
            "--task-guid",
            task_id,
            "--as",
            "bot",
            "--format",
            "json",
        ]
    )
    if out is None:
        return None
    try:
        fields = json.loads(out)["data"]["task"]["custom_fields"]
    except (ValueError, KeyError, TypeError):
        return None

    picked = {}
    for f in fields or []:
        if f.get("name") in (FIELD_TYPE, FIELD_STATUS):
            picked[f["name"]] = (f.get("guid"), f.get("single_select_value"))
    if FIELD_TYPE not in picked or FIELD_STATUS not in picked:
        return None

    cache = {}
    names = {}
    for name, (field_guid, option_guid) in picked.items():
        if not field_guid or not option_guid:
            return None
        opt_name = _option_name(field_guid, option_guid, cache)
        if opt_name is None:
            return None
        names[name] = opt_name

    return names[FIELD_TYPE] == TYPE_VALUE and names[FIELD_STATUS] == STATUS_VALUE


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


def _do_linkback(task_id, prefix):
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
            prefix + link,
            "--as",
            "bot",
        ]
    )


def post_linkback(task_id, prefix):
    """fork 子进程静默贴链接，父进程立即返回，不阻塞规则注入。

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
            _do_linkback(task_id, prefix)
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
        task_id = extract_task_id(prompt)
        # 查任务自定义字段判定入口：类型=需求 且 状态=待评审 → 进 intent 阶段。
        # 查不到（返回 None）按普通 devflow 走，不把无关任务误判成需求。
        # 必须先于贴评论：评论前缀按阶段区分。
        state["mode"] = "intent" if (task_id and is_intent_task(task_id)) else "dev"
        # 异步取会话链接贴到任务评论（后台静默跑，不阻塞规则注入，成功失败均不反馈）；
        # 同一任务仅派发一次，避免刷屏
        if task_id and task_id not in state.get("posted", []):
            if post_linkback(task_id, LINKBACK_PREFIX[state["mode"]]):
                state.setdefault("posted", []).append(task_id)
        emit = STATUS_RULE
    elif state.get("armed"):
        state["count"] = state.get("count", 0) + 1
        if state["count"] % INTERVAL == 0:
            emit = STATUS_RULE

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
