import json
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))
import plugins  # noqa: E402

app = QCoreApplication.instance() or QCoreApplication([])

GOOD = '''
class P:
    id = "demo"
    def candidates(self): return [{"id": "a", "title": "Alpha", "arguments": [{"placeholder": "Who"}] * 5}]
    def actions_for(self, c): return [{"id": "go", "title": "Go"}]
    def perform(self, c, action, ctx): return {"close": True, "seen": c["id"]}
    def fallbacks(self, q): return [{"title": "Ask " + q}]
def register(api): api.add_provider(P())
'''

BAD_LOAD = "def register(api): raise RuntimeError('no')\n"
BAD_PERFORM = GOOD.replace('return {"close": True, "seen": c["id"]}', 'raise ValueError("boom")')


def host_with(*sources):
    tmp = tempfile.TemporaryDirectory()
    for i, source in enumerate(sources):
        Path(tmp.name, "p%d.py" % i).write_text(source)
    host = plugins.PluginHost(tmp.name, lambda: {"plugins": {"demo": {"k": 1}}})
    host.load_all(tmp.name)
    return host, tmp


class PluginHostTests(unittest.TestCase):
    def test_candidates_are_namespaced_and_arguments_capped_at_three(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        [row] = json.loads(host.candidates("demo"))
        self.assertEqual(row["id"], "demo:a")
        self.assertEqual(len(row["arguments"]), 3)
        [info] = json.loads(host.providers())
        self.assertEqual((info["id"], info["hasFallbacks"], info["hasFilters"], info["hasAnswers"]), ("demo", True, False, False))

    def test_plugin_sees_its_local_id_and_returns_an_outcome(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        outcome = json.loads(host.perform("demo", json.dumps({"id": "demo:a", "title": "Alpha"}), "go", "{}"))
        self.assertEqual(outcome, {"close": True, "seen": "a"})

    def test_fallbacks_are_search_only_rows(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        [row] = json.loads(host.fallbacks("demo", "x"))
        self.assertEqual(row["title"], "Ask x")
        self.assertEqual(row["rootSearch"]["when"], "searching")

    def test_a_plugin_that_fails_to_load_does_not_stop_the_others(self):
        host, tmp = host_with(BAD_LOAD, GOOD)
        self.addCleanup(tmp.cleanup)
        self.assertEqual([p["id"] for p in json.loads(host.providers())], ["demo"])

    def test_a_failing_perform_becomes_a_toast_with_a_copy_action(self):
        host, tmp = host_with(BAD_PERFORM)
        self.addCleanup(tmp.cleanup)
        outcome = json.loads(host.perform("demo", json.dumps({"id": "demo:a", "title": "Alpha"}), "go", "{}"))
        self.assertEqual(outcome["toast"]["style"], "failure")
        self.assertIn("boom", outcome["toast"]["actions"][0]["copy"])

    def test_duplicate_provider_ids_are_rejected(self):
        host, tmp = host_with(GOOD, GOOD)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(len(json.loads(host.providers())), 1)

    def test_settings_come_from_the_plugins_section(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(host.settings("demo"), {"k": 1})
        self.assertEqual(host.settings("other"), {})


if __name__ == "__main__":
    unittest.main()


class ManagementTests(unittest.TestCase):
    def make(self, settings=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name, "data")
        import os
        old = os.environ.get("X_CAST_DATA_DIR")
        os.environ["X_CAST_DATA_DIR"] = str(data)
        self.addCleanup(lambda: os.environ.pop("X_CAST_DATA_DIR") if old is None else os.environ.update(X_CAST_DATA_DIR=old))
        host = plugins.PluginHost(Path(tmp.name, "config"), lambda: {"plugins": settings or {}})
        Path(tmp.name, "bundled").mkdir()
        Path(tmp.name, "bundled", "demo.py").write_text(GOOD)
        host.load_all(Path(tmp.name, "bundled"), bundled=True)
        return host, tmp

    def test_install_adds_a_plugin_that_works_at_once(self):
        host, _ = self.make()
        result = host._install_bytes("extra.py", GOOD.replace('id = "demo"', 'id = "extra"').encode())
        self.assertEqual(result, {"ok": True, "name": "extra"})
        self.assertEqual({p["id"] for p in json.loads(host.providers())}, {"demo", "extra"})
        self.assertTrue((host.plugin_dir / "extra.py").exists())

    def test_install_rejects_bad_files_and_leaves_nothing_behind(self):
        host, _ = self.make()
        cases = {
            "bad-name.py": GOOD,
            "syntax.py": "def register(api: \n",
            "noregister.py": "x = 1\n",
            "clash.py": GOOD,                       # provider id "demo" is taken by the bundled plugin
            "demo.py": GOOD,                        # same plugin name as the bundled one
        }
        for name, text in cases.items():
            result = host._install_bytes(name, text.encode())
            self.assertFalse(result["ok"], name)
            self.assertFalse((host.plugin_dir / name).exists(), name)
        self.assertEqual([p["id"] for p in json.loads(host.providers())], ["demo"])

    def test_remove_deletes_a_user_plugin_but_refuses_a_bundled_one(self):
        host, _ = self.make()
        host._install_bytes("extra.py", GOOD.replace('id = "demo"', 'id = "extra"').encode())
        self.assertTrue(json.loads(host.remove("extra"))["ok"])
        self.assertFalse((host.plugin_dir / "extra.py").exists())
        self.assertEqual([p["id"] for p in json.loads(host.providers())], ["demo"])
        refused = json.loads(host.remove("demo"))
        self.assertFalse(refused["ok"])
        self.assertIn("turn it off", refused["error"])

    def test_turning_a_provider_off_hides_it_and_persists(self):
        host, tmp = self.make()
        self.assertTrue(json.loads(host.setEnabled("demo", False))["ok"])
        self.assertEqual(json.loads(host.providers()), [])
        [plugin] = json.loads(host.plugins())
        self.assertEqual(plugin["providers"], [{"id": "demo", "enabled": False, "locked": False}])
        again = plugins.PluginHost(Path(tmp.name, "config"), lambda: {})
        self.assertEqual(again._disabled, {"demo"})
        self.assertTrue(json.loads(host.setEnabled("demo", True))["ok"])
        self.assertEqual(len(json.loads(host.providers())), 1)

    def test_config_yaml_can_turn_a_plugin_off_and_locks_the_switch(self):
        host, _ = self.make({"demo": {"enabled": False}})
        self.assertEqual(json.loads(host.providers()), [])
        self.assertTrue(json.loads(host.plugins())[0]["providers"][0]["locked"])
        self.assertFalse(json.loads(host.setEnabled("demo", True))["ok"])

    def test_fetch_reads_a_local_file_and_enforces_the_size_limit(self):
        host, tmp = self.make()
        path = Path(tmp.name, "one.py")
        path.write_text(GOOD)
        self.assertEqual(host._fetch(str(path)), ("one.py", GOOD.encode()))
        path.write_bytes(b"#" * (plugins.MAX_PLUGIN_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "larger"):
            host._fetch(str(path))
        with self.assertRaises(OSError):
            host._fetch(str(Path(tmp.name, "missing.py")))

    def test_a_plugin_that_fails_to_load_is_listed_with_its_error(self):
        host, tmp = self.make()
        Path(tmp.name, "b2").mkdir()
        Path(tmp.name, "b2", "broken.py").write_text(BAD_LOAD)
        host.load_all(Path(tmp.name, "b2"))
        broken = [p for p in json.loads(host.plugins()) if p["name"] == "broken"][0]
        self.assertIn("RuntimeError", broken["error"])
