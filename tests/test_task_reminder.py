import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("task_reminder", ROOT / "scripts/hooks/feishu-task-reminder.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
TASK = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
URL = "https://applink.feishu.cn/client/todo/detail?guid=" + TASK
LINK = "https://applink.feishu.cn/client/chat/open?messageId=om_test"


class TaskReminderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.patch = patch.object(hook, "STATE_DIR", self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        env = patch.dict(os.environ, {"CC_SESSION_KEY": "feishu:chat:thread:om_test",
                                     "CLAUDE_PLUGIN_ROOT": str(ROOT)})
        env.start()
        self.addCleanup(env.stop)

    def prompt(self, text, sid="session"):
        return hook.reminder({"session_id": sid, "prompt": text})

    @patch.object(hook, "launch_linkback")
    def test_link_reminds_and_launches_backlink_without_routing(self, launch):
        text = self.prompt("请查看 " + URL)
        self.assertIn(TASK, text)
        self.assertNotIn("docs/agents", text)
        self.assertNotIn("/opt/", text)
        self.assertNotIn("devflow", text.lower())
        self.assertNotIn("Intent", text)
        self.assertEqual(launch.call_args.args[:2], (TASK, "om_test"))
        state = json.loads(next(self.state.glob("*.state")).read_text())
        self.assertNotIn("posted", state)

    @patch.object(hook, "launch_linkback")
    def test_tenth_message_reminds_and_sessions_are_isolated(self, launch):
        self.prompt(URL)
        for _ in range(9):
            self.assertEqual(self.prompt("继续"), "")
        self.assertIn(TASK, self.prompt("继续"))
        self.assertEqual(self.prompt("继续", sid="another"), "")

    @patch.object(hook, "launch_linkback")
    def test_new_task_replaces_current_context(self, launch):
        self.prompt(URL)
        text = self.prompt(URL.replace(TASK, OTHER))
        self.assertIn(OTHER, text)
        self.assertNotIn(TASK, text)

    @patch.object(hook, "launch_linkback")
    def test_markdown_link_arms_reminder_and_replaces_previous_task(self, launch):
        self.prompt(URL.replace(TASK, OTHER))
        wrapped = f"[任务]({URL})"
        self.assertEqual(hook.task_ids(wrapped), [TASK])
        text = self.prompt(wrapped)
        self.assertIn(TASK, text)
        self.assertNotIn(OTHER, text)
        self.assertEqual(launch.call_args.args[:2], (TASK, "om_test"))
        for _ in range(9):
            self.assertEqual(self.prompt("继续"), "")
        self.assertIn(TASK, self.prompt("继续"))

    def test_query_order_multiple_links_and_invalid_guid(self):
        urls = f'{URL}&amp;suite_entity_num=t1 {URL} https://applink.feishu.cn/client/todo/task?suite_entity_num=t2&guid={OTHER}'
        self.assertEqual(hook.task_ids(urls), [TASK, OTHER])
        self.assertEqual(hook.task_ids(URL.replace(TASK, "../../oops")), [])
        self.assertEqual(hook.task_ids("https://example.com/?guid=" + TASK), [])

    @patch.object(hook, "launch_linkback")
    def test_local_session_never_posts(self, launch):
        with patch.dict(os.environ, {"CC_SESSION_KEY": ""}):
            self.assertIn(TASK, self.prompt(URL))
        launch.assert_not_called()

    @patch.object(hook, "run_cli")
    def test_success_is_recorded_after_comment_and_deduplicated(self, cli):
        receipt = self.state / "receipt.link"
        def response(args):
            if args[0] == "im":
                return {"ok": True, "data": [{"message_app_link": LINK}]}
            self.assertEqual(json.loads(receipt.read_text())["status"], "unconfirmed")
            self.assertEqual(args, ["task", "+comment", "--task-id", TASK,
                                    "--content", "关联会话：" + LINK])
            return {"ok": True, "data": {"comment_id": "comment"}}
        cli.side_effect = response
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(json.loads(receipt.read_text())["status"], "posted")
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(cli.call_count, 2)

    @patch.object(hook, "run_cli")
    def test_uncertain_write_is_not_retried(self, cli):
        cli.side_effect = [{"data": {"message_app_link": LINK}}, None]
        receipt = self.state / "receipt.link"
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(json.loads(receipt.read_text())["status"], "unconfirmed")
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(cli.call_count, 2)

    @patch.object(hook, "run_cli")
    def test_failed_lookup_can_retry_without_claiming_success(self, cli):
        receipt = self.state / "receipt.link"
        cli.return_value = None
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(receipt.read_text(), "")
        cli.side_effect = [{"data": {"message_app_link": LINK}}, {"ok": True}]
        hook.linkback(TASK, "om_test", receipt)
        self.assertEqual(json.loads(receipt.read_text())["status"], "posted")

    @patch.object(hook, "launch_linkback")
    def test_unconfirmed_backlink_is_visible_and_not_launched_again(self, launch):
        self.prompt(URL)
        receipt = launch.call_args.args[2]
        receipt.write_text(json.dumps({"status": "unconfirmed", "url": LINK}))
        launch.reset_mock()
        self.assertIn("回链未确认", self.prompt(URL))
        launch.assert_not_called()

    @patch.object(hook.subprocess, "run")
    def test_cli_success_requires_envelope_and_exit_status(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"ok":true,"data":{}}')
        self.assertIsNotNone(hook.run_cli(["task", "+comment"]))
        self.assertIn("bot", run.call_args.args[0])
        run.return_value = subprocess.CompletedProcess([], 1, '{"ok":false}')
        self.assertIsNone(hook.run_cli(["task", "+comment"]))
        run.side_effect = subprocess.TimeoutExpired("lark-cli", 10)
        self.assertIsNone(hook.run_cli(["task", "+comment"]))

    @patch.object(hook, "launch_linkback")
    def test_cleanup_keeps_uncertain_writes_for_manual_reconciliation(self, launch):
        self.prompt(URL)
        receipt = launch.call_args.args[2]
        receipt.write_text(json.dumps({"status": "unconfirmed", "url": LINK}))
        os.utime(receipt, (1, 1))
        stale = self.state / "expired.state"
        stale.write_text('{}')
        os.utime(stale, (1, 1))
        launch.reset_mock()
        self.assertIn("回链未确认", self.prompt(URL))
        self.assertTrue(receipt.exists())
        self.assertFalse(stale.exists())
        launch.assert_not_called()

    @patch.object(hook, "run_cli")
    def test_concurrent_backlink_worker_does_not_send_again(self, cli):
        receipt = self.state / "receipt.link"
        with receipt.open("w+") as handle:
            hook.fcntl.flock(handle, hook.fcntl.LOCK_EX)
            hook.linkback(TASK, "om_test", receipt)
        cli.assert_not_called()

    def test_codex_prompt_payload_returns_additional_context(self):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "codex-thread",
                   "turn_id": "turn-1", "cwd": str(ROOT), "transcript_path": None,
                   "model": "test-model", "permission_mode": "default", "prompt": URL}
        output = io.StringIO()
        with patch.dict(os.environ, {"CC_SESSION_KEY": ""}), \
                patch.object(hook.sys, "argv", ["feishu-task-reminder.py"]), \
                patch.object(hook.sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(output):
            hook.main()
        result = json.loads(output.getvalue())
        self.assertEqual(set(result), {"hookSpecificOutput"})
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        self.assertIn(TASK, specific["additionalContext"])
        self.assertEqual(set(specific), {"hookEventName", "additionalContext"})

    def test_hook_is_registered(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
        self.assertEqual(set(hooks["hooks"]), {"UserPromptSubmit"})
        commands = hooks["hooks"]["UserPromptSubmit"][0]["hooks"]
        self.assertEqual(len(commands), 1)
        self.assertIn("feishu-task-reminder.py", commands[0]["command"])


if __name__ == "__main__":
    unittest.main()
