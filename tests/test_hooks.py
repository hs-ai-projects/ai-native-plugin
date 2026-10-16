import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HookTests(unittest.TestCase):
    def test_session_pointer_is_readable_without_cc_connect(self):
        result = subprocess.run(["bash", str(ROOT / "scripts/hooks/inject-rules.sh")],
                                env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
                                text=True, capture_output=True, check=True)
        event = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(event["hookEventName"], "SessionStart")
        self.assertIn(str(ROOT / "rules/harness.md"), event["additionalContext"])
        self.assertTrue((ROOT / "rules/harness.md").is_file())

    def test_mention_guard_still_blocks_plain_mentions(self):
        script = ROOT / "scripts/hooks/enforce-at-mention.sh"
        for message, code in [("@同事 请检查", 2), ('<at user_id="ou_test">同事</at> 请检查', 0)]:
            result = subprocess.run(["bash", str(script)],
                                    env={**os.environ, "CC_SESSION_KEY": "feishu:test"},
                                    input=json.dumps({"last_assistant_message": message}),
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, code, result.stderr)


if __name__ == "__main__":
    unittest.main()
