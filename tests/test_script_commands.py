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
