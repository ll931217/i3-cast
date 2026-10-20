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
