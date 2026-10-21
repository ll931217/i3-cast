import contextlib
import io
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


class ExplodingText:
    def __str__(self):
        raise RuntimeError("candidate-secret")


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
        self.assertIn("ValueError", outcome["toast"]["actions"][0]["copy"])
        self.assertNotIn("boom", outcome["toast"]["actions"][0]["copy"])

    def test_duplicate_provider_ids_are_rejected(self):
        host, tmp = host_with(GOOD, GOOD)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(len(json.loads(host.providers())), 1)

    def test_list_slots_contain_bad_entries_and_keep_valid_siblings(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        for method, invoke in (
            ("candidates", lambda: host.candidates("demo")),
            ("answers", lambda: host.answers("demo", "q")),
            ("fallbacks", lambda: host.fallbacks("demo", "q")),
            ("filters", lambda: host.filters("demo")),
            ("actions_for", lambda: host.actionsFor("demo", '{"id":"demo:a"}')),
        ):
            with self.subTest(method=method):
                calls = []
                def rows(*args):
                    calls.append(args)
                    return [None, {"id": "bad", "title": "Bad", "data": object()},
                            {"id": "bad-title", "title": ExplodingText()},
                            {"id": "ok", "title": "Good"}] if method != "filters" else [
                                None, {"id": "bad-title", "title": ExplodingText()},
                                {"id": "ok", "title": "Good"}]
                setattr(provider, method, rows)
                result = json.loads(invoke())
                self.assertEqual([row["title"] for row in result], ["Good"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(host._errors[-1]["plugin"], "demo")
                self.assertEqual(host._errors[-1]["during"], method)

    def test_perform_contains_decoding_invocation_validation_and_serialization(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        calls = []
        result = None
        def perform(*args):
            calls.append(args)
            if isinstance(result, Exception):
                raise result
            return result
        provider.perform = perform
        candidate = '{"id":"demo:a","data":"candidate-secret"}'
        bad_outcomes = [False, 1, "bad", [], {"close": 1}, {"visit": "yes"},
                        {"hud": []}, {"toast": "bad"}, {"toast": {}},
                        {"toast": {"style": "other", "title": "Bad"}},
                        {"toast": {"style": "failure", "title": 1}},
                        {"toast": {"style": "success", "title": "OK", "actions": {}}},
                        {"toast": {"style": "success", "title": "OK", "actions": [None]}},
                        {"toast": {"style": "success", "title": "OK", "actions": [{"title": "Copy", "copy": 2}]}},
                        {"prompt": None}, {"prompt": {}}, {"prompt": {"kind": "other"}},
                        {"prompt": {"kind": "arguments", "title": 2}},
                        {"prompt": {"kind": "confirmation"}, "close": True},
                        {"prompt": {"kind": "arguments"}, "visit": False},
                        {"future": object()}, {"future": float("nan")},
                        {"future": float("inf")}, RuntimeError("candidate-secret")]
        cycle = {}
        cycle["cycle"] = cycle
        bad_outcomes.append(cycle)
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            for result in bad_outcomes:
                with self.subTest(result_type=type(result).__name__):
                    before = len(calls)
                    outcome = json.loads(host.perform("demo", candidate, "go", "{}"))
                    self.assertEqual(len(calls), before + 1)
                    self.assertEqual(set(outcome), {"toast"})
                    self.assertEqual(outcome["toast"]["style"], "failure")
                    self.assertEqual(outcome["toast"]["actions"][0]["title"], "Copy Error")
                    self.assertNotIn("candidate-secret", json.dumps(outcome))
            for bad_candidate, bad_ctx in [("{", "{}"), ("null", "{}"), ("[]", "{}"),
                                           ('{"id":4}', "{}"), (candidate, "{"),
                                           (candidate, "[]"), (candidate, '{"arguments":4}'),
                                           (candidate, '{"query":null}'),
                                           (candidate, '{"arguments":[NaN]}')]:
                with self.subTest(candidate=bad_candidate, ctx=bad_ctx):
                    before = len(calls)
                    outcome = json.loads(host.perform("demo", bad_candidate, "go", bad_ctx))
                    self.assertEqual(outcome["toast"]["style"], "failure")
                    self.assertEqual(len(calls), before)
            self.assertNotIn("candidate-secret", diagnostics.getvalue())

    def test_perform_warns_about_side_effects_only_after_invocation(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        side_effects = []
        warning = "side effects may already have occurred"
        candidate = '{"id":"demo:a","data":"candidate-secret"}'
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            for result in [False, {"future": object()}, RuntimeError("candidate-secret")]:
                def perform(*args):
                    side_effects.append("ran")
                    if isinstance(result, Exception):
                        raise result
                    return result
                provider.perform = perform
                before = len(side_effects)
                outcome = json.loads(host.perform("demo", candidate, "go", "{}"))
                self.assertEqual(len(side_effects), before + 1)
                self.assertEqual(set(outcome), {"toast"})
                self.assertEqual(outcome["toast"]["style"], "failure")
                self.assertIn(warning, outcome["toast"]["title"])
                self.assertEqual(outcome["toast"]["actions"], [
                    {"title": "Copy Error", "copy": outcome["toast"]["title"]}])
                self.assertNotIn("candidate-secret", json.dumps(outcome))
            for pid, raw, ctx in [("demo", "{", "{}"), ("demo", candidate, "{"),
                                  ("missing", candidate, "{}")]:
                before = len(side_effects)
                outcome = json.loads(host.perform(pid, raw, "go", ctx))
                self.assertEqual(len(side_effects), before)
                self.assertEqual(outcome["toast"]["style"], "failure")
                self.assertNotIn(warning, json.dumps(outcome))
                self.assertNotIn("candidate-secret", json.dumps(outcome))
            self.assertNotIn("candidate-secret", diagnostics.getvalue())

    def test_actions_reject_empty_id_or_title_without_losing_valid_siblings(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        host._providers["demo"].actions_for = lambda candidate: [
            {"id": "before", "title": "Before"},
            {"id": "", "title": "Empty id"},
            {"id": "empty-title", "title": ""},
            {"id": "after", "title": "After"}]
        with contextlib.redirect_stderr(io.StringIO()):
            actions = json.loads(host.actionsFor("demo", '{"id":"demo:a"}'))
        self.assertEqual(actions, [{"id": "before", "title": "Before"},
                                   {"id": "after", "title": "After"}])

    def test_perform_preserves_none_prompts_and_unknown_json_fields(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        for expected in [None, {}, {"close": False, "visit": True, "future": [1, {"ok": True}]},
                         {"prompt": {"kind": "arguments"}},
                         {"prompt": {"kind": "confirmation", "title": "Continue?"}},
                         {"hud": "Done", "toast": {"style": "success", "title": "OK",
                          "actions": [{"title": "Copy", "copy": "text"}, {"title": "Open", "open": "https://example.org"}]}}]:
            with self.subTest(expected=expected):
                provider.perform = lambda *args: expected
                self.assertEqual(json.loads(host.perform("demo", '{"id":"demo:a"}', "go", "{}")), expected)

    def test_malformed_list_containers_and_provider_errors_are_attributed(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        slots = [("candidates", lambda: host.candidates("demo")),
                 ("answers", lambda: host.answers("demo", "q")),
                 ("fallbacks", lambda: host.fallbacks("demo", "q")),
                 ("filters", lambda: host.filters("demo")),
                 ("actions_for", lambda: host.actionsFor("demo", '{"id":"demo:a"}'))]
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            for method, invoke in slots:
                for bad in [None, False, 7, "candidate-secret", {}, (), iter([])]:
                    with self.subTest(method=method, container=type(bad).__name__):
                        setattr(provider, method, lambda *args: bad)
                        before = len(host._errors)
                        self.assertEqual(invoke(), "[]")
                        self.assertGreater(len(host._errors), before)
                        self.assertEqual(host._errors[-1]["plugin"], "demo")
                        self.assertEqual(host._errors[-1]["during"], method)
                def fail(*args):
                    raise ValueError("candidate-secret")
                setattr(provider, method, fail)
                self.assertEqual(invoke(), "[]")
            self.assertEqual(host.actionsFor("demo", "{"), "[]")
            self.assertEqual(host.actionsFor("demo", "null"), "[]")
            self.assertEqual(host.candidates("missing"), "[]")
            for _ in range(150):
                host.perform("demo", "{", "go", "{}")
            self.assertLessEqual(len(host._errors), 100)
            self.assertTrue(all(len(error["error"]) <= 1000 for error in host._errors))
            self.assertNotIn("candidate-secret", diagnostics.getvalue())

    def test_strict_serialization_is_per_entry_not_per_list(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        provider = host._providers["demo"]
        cycle = []
        cycle.append(cycle)
        for method, invoke in [("candidates", lambda: host.candidates("demo")),
                               ("answers", lambda: host.answers("demo", "q")),
                               ("fallbacks", lambda: host.fallbacks("demo", "q")),
                               ("actions_for", lambda: host.actionsFor("demo", '{"id":"demo:a"}'))]:
            for bad in [float("nan"), float("inf"), -float("inf"), cycle, object()]:
                with self.subTest(method=method, bad_type=type(bad).__name__):
                    setattr(provider, method, lambda *args: [
                        {"id": "a", "title": "Before"},
                        {"id": "bad", "title": "Bad", "data": bad},
                        {"id": "b", "title": "After"}])
                    with contextlib.redirect_stderr(io.StringIO()):
                        rows = json.loads(invoke())
                    self.assertEqual([r["title"] for r in rows], ["Before", "After"])

    def test_bridge_slot_signatures_and_local_candidate_context_are_preserved(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        meta = host.metaObject()
        for signature in ["providers()", "candidates(QString)", "filters(QString)",
                          "answers(QString,QString)", "fallbacks(QString,QString)",
                          "actionsFor(QString,QString)", "perform(QString,QString,QString,QString)"]:
            with self.subTest(signature=signature):
                index = meta.indexOfSlot(signature)
                self.assertGreaterEqual(index, 0)
                self.assertEqual(meta.method(index).typeName(), "QString")
        seen = []
        provider = host._providers["demo"]
        provider.actions_for = lambda c: seen.append(c) or [{"id": "go", "title": "Go", "future": [1]}]
        candidate = {"id": "demo:a", "data": {"secret": "kept"}, "future": 2}
        self.assertEqual(json.loads(host.actionsFor("demo", json.dumps(candidate))),
                         [{"id": "go", "title": "Go", "future": [1]}])
        provider.perform = lambda c, a, ctx: {"seen": c, "action": a, "ctx": ctx}
        ctx = {"query": "q", "arguments": ["password"], "confirmed": True}
        outcome = json.loads(host.perform("demo", json.dumps(candidate), "go", json.dumps(ctx)))
        local = {"id": "a", "data": {"secret": "kept"}, "future": 2}
        self.assertEqual(seen, [local])
        self.assertEqual(outcome, {"seen": local, "action": "go", "ctx": ctx})

    def test_provider_metadata_failure_does_not_hide_healthy_provider(self):
        host, tmp = host_with(GOOD)
        self.addCleanup(tmp.cleanup)
        class BadMetadata:
            id = "broken"
            def candidates(self): return []
            def actions_for(self, candidate): return []
            def perform(self, *args): return None
            @property
            def filters(self): raise RuntimeError("candidate-secret")
        host.add_provider(BadMetadata(), "broken")
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            self.assertEqual([p["id"] for p in json.loads(host.providers())], ["demo"])
            self.assertNotIn("candidate-secret", diagnostics.getvalue())
        self.assertEqual(host._errors[-1]["plugin"], "broken")

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
