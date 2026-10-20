import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host" / "plugins"))
import script_commands as sc  # noqa: E402

SCRIPT = """#!/bin/bash
# @raycast.schemaVersion 1
# @raycast.title Greet
# @raycast.mode compact
# @raycast.packageName Demo
# @raycast.argument1 { "type": "text", "placeholder": "Name" }
# @raycast.argument2 { "type": "dropdown", "placeholder": "Mood", "optional": true, "data": [{"title": "Happy", "value": "happy"}, {"title": "Sad", "value": "sad"}] }
echo "hello $1"
"""


def write(directory, name, text, mode=0o755):
    path = Path(directory) / name
    path.write_text(text)
    path.chmod(mode)
    return path


class ParseTests(unittest.TestCase):
    def test_header_keys_are_case_insensitive_and_accept_other_comment_styles(self):
        meta = sc.parse_header("// @Raycast.Title Hi\nREM @raycast.mode silent\n:: @raycast.schemaVersion 1\n")
        self.assertEqual(meta, {"title": "Hi", "mode": "silent", "schemaversion": "1"})

    def test_requires_schema_title_and_mode(self):
        p = Path("/x/y.sh")
        self.assertIsNone(sc.parse_script(p, "# @raycast.title T\n# @raycast.mode compact\n"))
        self.assertIsNone(sc.parse_script(p, "# @raycast.schemaVersion 1\n# @raycast.mode compact\n"))
        self.assertIsNotNone(sc.parse_script(p, "# @raycast.schemaVersion 1\n# @raycast.title T\n# @raycast.mode full-output\n"))

    def test_arguments_and_package_name(self):
        script = sc.parse_script(Path("/scripts/my-tools/greet.sh"), SCRIPT.replace("# @raycast.packageName Demo\n", ""))
        self.assertEqual(script["package"], "My Tools")
        self.assertEqual([a["placeholder"] for a in script["arguments"]], ["Name", "Mood"])
        self.assertEqual(script["arguments"][1]["data"], ["happy", "sad"])
        self.assertTrue(script["arguments"][1]["optional"])

    def test_bad_argument_json_rejects_the_script(self):
        self.assertIsNone(sc.parse_script(Path("/a.sh"), "# @raycast.schemaVersion 1\n# @raycast.title T\n# @raycast.mode compact\n# @raycast.argument1 {nope\n"))


class ScanAndRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_skips_non_executable_templates_and_unrelated_files(self):
        write(self.dir, "greet.sh", SCRIPT)
        write(self.dir, "plain.sh", "#!/bin/bash\necho hi\n")
        write(self.dir, "locked.sh", SCRIPT, mode=0o644)
        write(self.dir, "greet.template.sh", SCRIPT)
        (Path(self.dir) / "sub").mkdir()
        self.assertEqual([s["title"] for s in sc.scan(self.dir)], ["Greet"])

    def test_build_args_validates_and_encodes(self):
        script = sc.parse_script(Path("/g.sh"), SCRIPT)
        self.assertEqual(sc.build_args(script, ["Ann", "sad"]), ["Ann", "sad"])
        self.assertEqual(sc.build_args(script, ["Ann"]), ["Ann", ""])
        with self.assertRaisesRegex(ValueError, "Name is required"):
            sc.build_args(script, [])
        with self.assertRaisesRegex(ValueError, "must be one of"):
            sc.build_args(script, ["Ann", "angry"])
        script["arguments"][0]["percentEncoded"] = True
        self.assertEqual(sc.build_args(script, ["a b&c"])[0], "a%20b%26c")

    def test_run_reports_last_non_empty_line_and_exit_status(self):
        path = write(self.dir, "greet.sh", SCRIPT)
        script = sc.parse_script(path, SCRIPT)
        self.assertEqual(sc.run_script(script, ["Ann"]), (True, "hello Ann"))
        bad = write(self.dir, "bad.sh", SCRIPT.replace('echo "hello $1"', 'printf "\\033[31moops\\033[0m\\n\\n"; exit 3'))
        self.assertEqual(sc.run_script(sc.parse_script(bad, bad.read_text()), ["x"]), (False, "oops"))


if __name__ == "__main__":
    unittest.main()


class InlineAndConfirmTests(unittest.TestCase):
    BASE = "# @raycast.schemaVersion 1\n# @raycast.title T\n"

    def test_parse_refresh(self):
        self.assertEqual(sc.parse_refresh("10s"), 10)
        self.assertEqual(sc.parse_refresh("5m"), 300)
        self.assertEqual(sc.parse_refresh("1d"), 86400)
        self.assertIsNone(sc.parse_refresh("5s"))
        self.assertIsNone(sc.parse_refresh("soon"))

    def test_inline_needs_a_valid_refresh_time_and_no_arguments(self):
        p = Path("/x.sh")
        self.assertIsNone(sc.parse_script(p, self.BASE + "# @raycast.mode inline\n"))
        self.assertIsNone(sc.parse_script(p, self.BASE + "# @raycast.mode inline\n# @raycast.refreshTime 1m\n# @raycast.argument1 {\"type\": \"text\", \"placeholder\": \"a\"}\n"))
        s = sc.parse_script(p, self.BASE + "# @raycast.mode inline\n# @raycast.refreshTime 1m\n")
        self.assertEqual((s["mode"], s["refresh"]), ("inline", 60))

    def test_confirmation_requires_an_explicit_invocation_marker(self):
        class Api:
            def __init__(self, root):
                self.root, self.runs = root, 0
            def settings(self, _pid): return {}
            def config_dir(self): return self.root
            def watch(self, _path): pass
            def run_in_background(self, _work, _done): self.runs += 1
        with tempfile.TemporaryDirectory() as directory:
            api = Api(Path(directory))
            provider = sc.ScriptCommands(api)
            script = sc.parse_script(Path('/x.sh'), self.BASE + '# @raycast.mode silent\n# @raycast.needsConfirmation true\n')
            candidate = {'data': script}
            first = provider.perform(candidate, 'run', {'arguments': []})
            second = provider.perform(candidate, 'run', {'arguments': []})
            self.assertEqual(first['prompt']['kind'], 'confirmation')
            self.assertEqual(second['prompt']['kind'], 'confirmation')
            self.assertEqual(api.runs, 0)
            self.assertTrue(provider.perform(candidate, 'run', {'arguments': [], 'confirmed': True})['visit'])
            self.assertEqual(api.runs, 1)

    def test_needs_confirmation_flag(self):
        s = sc.parse_script(Path("/x.sh"), self.BASE + "# @raycast.mode silent\n# @raycast.needsConfirmation true\n")
        self.assertTrue(s["confirm"])
