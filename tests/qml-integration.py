"""Isolated Qt integration checks; run separately from QCoreApplication tests.

QT_QPA_PLATFORM=offscreen .venv/bin/python tests/qml-integration.py
No desktop processes, clipboard writes, user config, or live socket are used.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))
ISOLATED = tempfile.TemporaryDirectory(prefix="x-cast-qml-")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["X_CAST_CONFIG_DIR"] = ISOLATED.name + "/config"
os.environ["XDG_DATA_HOME"] = ISOLATED.name + "/data"
os.environ["XDG_CACHE_HOME"] = ISOLATED.name + "/cache"

from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonInstance  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
import apps  # noqa: E402
import plugins  # noqa: E402
import qsshim  # noqa: E402
import userconfig  # noqa: E402
from main import IpcRegistry  # noqa: E402


class LauncherIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        qsshim.register()
        cls.registry = IpcRegistry()
        cls.user = userconfig.HostConfig()
        cls.shell = apps.HostShell()
        cls.plugins = plugins.PluginHost(userconfig.config_dir(), lambda: cls.user.config)
        cls.host = apps.Host()
        qmlRegisterSingletonInstance(IpcRegistry, "OmaHost", 1, 0, "IpcRegistry", cls.registry)
        qmlRegisterSingletonInstance(userconfig.HostConfig, "OmaHost", 1, 0, "HostConfig", cls.user)
        qmlRegisterSingletonInstance(apps.HostShell, "OmaHost", 1, 0, "HostShell", cls.shell)
        qmlRegisterSingletonInstance(plugins.PluginHost, "OmaHost", 1, 0, "PluginHost", cls.plugins)
        qmlRegisterSingletonInstance(apps.Host, "OmaHost", 1, 0, "Host", cls.host)
        cls.engine = QQmlEngine()
        cls.registry.engine = cls.engine
        cls.engine.addImportPath(str(ROOT / "host" / "qml"))
        cls.component = QQmlComponent(cls.engine, QUrl.fromLocalFile(str(ROOT / "plugin" / "Launcher.qml")))
        if cls.component.isError():
            raise AssertionError("\n".join(e.toString() for e in cls.component.errors()))
        cls.root = cls.component.create()
        if cls.root is None:
            raise AssertionError("\n".join(e.toString() for e in cls.component.errors()))
        cls.backend = cls.root.findChild(QObject, "backend")
        cls.window = cls.root.findChild(QObject, "launcherWindow")
        for name, obj in (("launcher", cls.root), ("backend", cls.backend), ("window", cls.window)):
            cls.engine.globalObject().setProperty(name, cls.engine.newQObject(obj))
        for _ in range(100):
            if cls.backend.property("ready"):
                break
            QTest.qWait(10)
        if not cls.backend.property("ready"):
            raise AssertionError("isolated stores did not load")
        cls.js('''
          var calls = [], visits = [], notices = [];
          function makeProbeProvider() { return {
            id: "probe",
            candidates: function() { return [{ id:"probe:stored", provider:"probe", title:"Probe", type:"command", typeLabel:"Probe", arguments:[{name:"name", optional:false}], rootSearch:{when:"always"}, data:{answer:"original"} }] },
            answers: function(q) { return [{ id:"probe:answer", title:q, type:"command", rootSearch:{when:"always"}, data:{answer:q} }] },
            actionsFor: function() { return [{id:"run", title:"Run"}] },
            perform: function(c, action, ctx) {
              if (action !== "run") return undefined;
              if (!ctx.confirmed) return {prompt:{kind:"confirmation", title:"Press Enter to confirm"}};
              calls.push({candidate:c,ctx:ctx}); return {close:true,visit:true};
            }
          }; }
          var provider;
          backend.providerRegistry.order.push("probe");
        ''')

    @classmethod
    def tearDownClass(cls):
        cls.js('launcher.hide()')
        QTest.qWait(300)  # Let debounced store writes finish before Qt teardown.

    @classmethod
    def js(cls, script):
        result = cls.engine.evaluate(script)
        if result.isError():
            raise AssertionError(result.toString() + "\n" + result.property("stack").toString())
        return result.toVariant()

    def setUp(self):
        self.js('''
          launcher.hide();
          window.popToRoot();
          calls = []; visits = []; notices = [];
          provider = makeProbeProvider();
          backend.providerRegistry.providers.probe = provider;
          backend.rebuildCandidates();
        ''')
        self.addCleanup(self.js, 'launcher.hide()')

    def rpc(self, method, data=None):
        return self.js('backend.callSync(' + json.dumps(method) + ',' + json.dumps(data) + ')')

    def open_session(self):
        result = self.rpc("rootSearch.openSession")
        self.assertTrue(result["ok"], result)
        session = result["data"]
        self.addCleanup(self.close_session, session)
        return session

    def close_session(self, session):
        result = self.rpc("rootSearch.closeSession", {"session": session})
        self.assertTrue(result["ok"], result)

    def stored_ref(self, session):
        result = self.rpc("rootSearch.search", {"query": "Probe", "session": session})
        self.assertTrue(result["ok"], result)
        rows = [row for section in result["data"] for row in section["rows"]
                if row["id"] == "probe:stored"]
        self.assertEqual(len(rows), 1, result)
        return rows[0]["ref"]

    def present_prompt(self, result):
        self.assertTrue(result["ok"], result)
        self.assertIn("prompt", result["data"])
        self.addCleanup(self.rpc, "rootSearch.cancelPrompt",
                        {"continuation": result["data"]["continuation"]})
        self.js('launcher.present(' + json.dumps(result) + ')')

    def test_hidden_run_opens_exact_argument_prompt_and_confirms_once(self):
        result = self.js('launcher.run("probe:stored")')
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["prompt"]["kind"], "arguments")
        self.assertTrue(self.root.property("opened"))
        self.assertEqual(self.js('window.selectedRow.itemId'), "probe:stored")
        self.js('window.argValues = ["Ann"]; window.performNth(0)')
        self.assertEqual(self.js('calls.length'), 0)
        self.assertTrue(self.js('Boolean(window.continuation)'))
        self.js('window.performNth(0)')
        self.assertEqual(self.js('calls.length'), 1, self.js('JSON.stringify({toast:window.toast,continuation:window.continuation,args:window.argValues,selected:window.selectedRow})'))
        self.assertEqual(self.js('calls[0].ctx.arguments[0]'), "Ann")
        self.assertFalse(self.root.property("opened"))
        self.assertEqual(self.js('window.continuation'), "")

    def test_displayed_answer_not_reconstructed_and_other_search_is_independent(self):
        self.js('launcher.open(JSON.stringify({query:"original query"}))')
        ref = self.js('window.selectedRow.resultRef')
        self.js('provider.answers = function() { return [{id:"probe:answer",title:"changed",data:{answer:"changed"}}] }; backend.callSync("rootSearch.search",{query:"other"})')
        self.js('window.performNth(0)')
        self.js('window.performNth(0)')
        self.assertEqual(self.js('calls.length'), 1, self.js('JSON.stringify({toast:window.toast,continuation:window.continuation,args:window.argValues,selected:window.selectedRow})'))
        self.assertEqual(self.js('calls[0].candidate.data.answer'), "original query")
        self.assertEqual(self.js('calls[0].ctx.query'), "original query")
        result = self.js('backend.callSync("rootSearch.performAction", {ref:' + json.dumps(ref) + '})')
        self.assertFalse(result["ok"])
        self.assertIn("expired", result["error"])

    def test_action_panel_holds_generation_across_refresh(self):
        self.js('launcher.show(); window.setQuery("panel"); window.togglePanel("actions")')
        ref = self.js('window.selectedRow.resultRef')
        self.js('backend.rebuildCandidates()')
        self.assertEqual(self.js('window.selectedRow.resultRef'), ref)
        self.assertTrue(self.js('window.refreshPending'))
        self.js('window.actionPanelOpen = false')
        QTest.qWait(20)
        self.assertNotEqual(self.js('window.selectedRow.resultRef'), ref)

    def test_link_arguments_enter_the_same_prompt_path(self):
        result = self.js('backend.callSync("rootSearch.openLink", {url:"raycast://script-commands/probe?arguments=%5B%22Ann%22%5D"})')
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["prompt"]["kind"], "confirmation")
        self.js('launcher.present(' + json.dumps(result) + ')')
        self.assertEqual(self.js('window.argValues[0]'), "Ann")
        self.assertEqual(self.js('window.selectedRow.itemId'), "probe:stored")
        self.js('window.performNth(0)')
        self.assertEqual(self.js('calls.length'), 1)

    def test_secondary_confirmation_enter_resumes_original_action(self):
        self.js('''
          var attempts = [];
          provider.actionsFor = function() {
            return [{id:"run", title:"Run"}, {id:"delete", title:"Delete"}];
          };
          provider.perform = function(c, action, ctx) {
            attempts.push([action, ctx.confirmed]);
            if (!ctx.confirmed) return {prompt:{kind:"confirmation", title:"Confirm " + action}};
            calls.push({candidate:c, action:action, ctx:ctx});
            return {close:true};
          };
        ''')
        result = self.rpc("rootSearch.performAction", {
            "id": "probe:stored", "action": "delete", "arguments": ["Ann"]})
        self.present_prompt(result)
        self.assertEqual(result["data"]["prompt"]["kind"], "confirmation")
        self.js('window.performNth(0)')  # The same hook used by Enter.
        self.assertEqual(self.js('attempts'), [["delete", False], ["delete", True]])
        self.assertEqual(self.js('calls.length'), 1)
        self.assertEqual(self.js('calls[0].action'), "delete")
        self.assertEqual(self.js('calls[0].ctx.arguments'), ["Ann"])

    def test_presenting_external_session_b_does_not_cancel_session_a_prompt(self):
        session_a, session_b = self.open_session(), self.open_session()
        ref_a, ref_b = self.stored_ref(session_a), self.stored_ref(session_b)
        prompt_a = self.rpc("rootSearch.performAction", {"ref": ref_a, "arguments": ["A"]})
        self.present_prompt(prompt_a)
        prompt_b = self.rpc("rootSearch.performAction", {"ref": ref_b, "arguments": ["B"]})
        self.present_prompt(prompt_b)
        self.assertEqual(self.js('window.argValues'), ["B"])
        for ref in (ref_a, ref_b):
            result = self.rpc("rootSearch.getActions", {"ref": ref})
            self.assertTrue(result["ok"], result)
        # Resume B first so its success is checked even while A is broken.
        for ref, prompt, args in ((ref_b, prompt_b, ["B"]), (ref_a, prompt_a, ["A"])):
            with self.subTest(arguments=args):
                before = self.js('calls.length')
                result = self.rpc("rootSearch.performAction", {
                    "ref": ref, "continuation": prompt["data"]["continuation"], "arguments": args})
                self.assertTrue(result["ok"], result)
                self.assertNotIn("prompt", result["data"])
                self.assertEqual(self.js('calls.length'), before + 1)
                self.assertEqual(self.js('calls[calls.length - 1].ctx.arguments'), args)
                self.assertTrue(self.js('calls[calls.length - 1].ctx.confirmed'))

    def test_alias_editor_expires_previous_displayed_refs(self):
        self.js('''
          launcher.open(JSON.stringify({query:"Probe"}));
          for (var n = 1; ; n++) {
            var index = window.nthItem(n);
            if (index < 0) break;
            window.select(index);
            if (window.selectedRow.itemId === "probe:stored") break;
          }
        ''')
        self.assertEqual(self.js('window.selectedRow.itemId'), "probe:stored")
        ref = self.js('window.selectedRow.resultRef')
        self.assertTrue(self.rpc("rootSearch.getActions", {"ref": ref})["ok"])
        self.js('window.perform("set-alias")')
        self.assertEqual(self.js('window.view.kind'), "alias")
        self.assertIsNone(self.js('window.selectedRow'))
        for method, data in (("rootSearch.getActions", {"ref": ref}),
                             ("rootSearch.performAction", {"ref": ref, "arguments": ["Ann"]})):
            with self.subTest(method=method):
                result = self.rpc(method, data)
                if result["ok"] and "continuation" in result["data"]:
                    self.addCleanup(self.rpc, "rootSearch.cancelPrompt",
                                    {"continuation": result["data"]["continuation"]})
                self.assertFalse(result["ok"], result)
                self.assertIn("expired", result["error"].lower())
        self.assertEqual(self.js('calls.length'), 0)

    def test_closing_command_prompt_expires_it_and_reopens_at_root(self):
        self.js('''
          var storedCandidates = provider.candidates;
          provider.candidates = function() {
            return [{id:"probe:aaa", title:"Aardvark", type:"command", rootSearch:{when:"always"}}]
              .concat(storedCandidates());
          };
          backend.rebuildCandidates();
        ''')
        result = self.js('launcher.run("probe:stored")')
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["prompt"]["kind"], "arguments")
        self.assertEqual(self.js('window.selectedRow.itemId'), "probe:stored")
        self.js('window.argValues = ["Ann"]')
        ref = self.js('window.selectedRow.resultRef')
        self.js('launcher.hide()')
        stale_ref = self.rpc("rootSearch.getActions", {"ref": ref})
        self.assertFalse(stale_ref["ok"], stale_ref)
        self.assertIn("expired", stale_ref["error"].lower())
        stale_prompt = self.rpc("rootSearch.performAction", {
            "id": "probe:stored", "continuation": result["data"]["continuation"], "arguments": ["Ann"]})
        self.assertFalse(stale_prompt["ok"], stale_prompt)
        self.js('launcher.show()')
        self.assertTrue(self.js('window.atRoot'), "A closed command prompt must not reopen as an unrelated command view")
        self.assertEqual(self.js('window.continuation'), "")
        self.assertEqual(self.js('calls.length'), 0)

    def test_stored_same_id_provider_replacement_rejects_continuation(self):
        prompt = self.rpc("rootSearch.performAction", {"id": "probe:stored", "arguments": ["Ann"]})
        self.assertTrue(prompt["ok"], prompt)
        self.assertEqual(prompt["data"]["prompt"]["kind"], "confirmation")
        self.addCleanup(self.rpc, "rootSearch.cancelPrompt",
                        {"continuation": prompt["data"]["continuation"]})
        self.js('''
          var replacementCalls = [];
          provider = makeProbeProvider();
          provider.perform = function(c, action, ctx) {
            replacementCalls.push({candidate:c, action:action, ctx:ctx});
            return {close:true};
          };
          backend.providerRegistry.providers.probe = provider;
          backend.rebuildCandidates();
        ''')
        result = self.rpc("rootSearch.performAction", {
            "id": "probe:stored", "continuation": prompt["data"]["continuation"], "arguments": ["Ann"]})
        self.assertFalse(result["ok"], result)
        self.assertEqual(self.js('replacementCalls.length'), 0)
        replay = self.rpc("rootSearch.performAction", {
            "id": "probe:stored", "continuation": prompt["data"]["continuation"], "arguments": ["Ann"]})
        self.assertFalse(replay["ok"], replay)


if __name__ == "__main__":
    unittest.main()
