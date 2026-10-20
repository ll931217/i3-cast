"""Exercise the real link CLI with a local recording socket-command adapter."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class LinkCliTests(unittest.TestCase):
    def invoke(self, reply):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            nc = directory / "nc"
            nc.write_text('''#!/bin/bash
case " $* " in *" -z "*) exit 0 ;; esac
IFS= read -r request
printf '%s\\n' "$request" >> "$NC_LOG"
printf '%s\\n' "$REPLY_JSON"
''')
            nc.chmod(0o755)
            log = directory / "calls"
            env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ["PATH"],
                       NC_LOG=str(log), REPLY_JSON=json.dumps(reply), XDG_RUNTIME_DIR=str(directory))
            result = subprocess.run([str(ROOT / "bin/x-cast"), "open", "raycast://script-commands/probe"],
                                    env=env, text=True, capture_output=True)
            return result, log.read_text().splitlines()

    def test_execution_errors_are_visible_and_nonzero(self):
        result, calls = self.invoke({"ok": False, "error": "Command is disabled"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Command is disabled", result.stderr)
        self.assertEqual(len(calls), 1)

    def test_prompt_does_not_trigger_a_second_search_or_execution(self):
        result, calls = self.invoke({"ok": True, "data": {"prompt": {"kind": "arguments"}}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("call rootSearch.openLink "))

    def test_unresolved_link_searches_once(self):
        result, calls = self.invoke({"ok": True, "data": {"search": "probe"}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1], "search probe")
        self.assertEqual(len(calls), 2)
