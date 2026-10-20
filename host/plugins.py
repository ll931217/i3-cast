"""Loads Python plugins and exposes their providers to QML as JSON.

A plugin is a .py file in host/plugins/ (bundled) or ~/.config/x-cast/plugins/ with

    def register(api):
        api.add_provider(MyProvider())

A provider (duck-typed, see docs/plugins.md) has:
    id                                  "my-plugin"
    candidates() -> [dict]              rows for root search
    actions_for(candidate) -> [dict]    first is the primary action
    perform(candidate, action, ctx)     -> dict outcome or None; ctx has "query" and "arguments"
    fallbacks(query) -> [dict]          optional "Use ... with" rows
"""
import importlib.util
import json
import re
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal, Slot

PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*$")
MAX_ARGUMENTS = 3


def normalize_arguments(raw):
    """At most three {name, placeholder, type, optional, data} argument specs."""
    out = []
    for i, arg in enumerate((raw or [])[:MAX_ARGUMENTS]):
        if not isinstance(arg, dict):
            continue
        kind = arg.get("type") if arg.get("type") in ("text", "password", "dropdown") else "text"
        out.append({
            "name": str(arg.get("name") or "argument%d" % (i + 1)),
            "placeholder": str(arg.get("placeholder") or arg.get("name") or "Argument %d" % (i + 1)),
            "type": kind,
            "optional": bool(arg.get("optional", False)),
            "data": [str(d) for d in arg.get("data", [])] if kind == "dropdown" else [],
        })
    return out


def normalize_candidate(provider_id, raw, searching_only=False):
    """Fill in what root search needs. Ids are namespaced by provider so plugins cannot collide."""
    local = str(raw["id"])
    return {
        "id": "%s:%s" % (provider_id, local),
        "type": "command",
        "title": str(raw.get("title") or local),
        "subtitle": str(raw.get("subtitle") or ""),
        "keywords": [str(k) for k in raw.get("keywords", [])],
        "typeLabel": str(raw.get("type_label") or "Command"),
        "iconName": str(raw.get("icon") or ""),
        "glyph": str(raw.get("glyph") or ""),
        "arguments": normalize_arguments(raw.get("arguments")),
        "data": raw.get("data"),
        "rootSearch": {"when": "searching" if searching_only else raw.get("root", "always")},
    }


class Api:
    """What a plugin's register(api) receives."""

    def __init__(self, host, plugin_name):
        self._host = host
        self.plugin_name = plugin_name

    def add_provider(self, provider):
        self._host.add_provider(provider, self.plugin_name)

    def settings(self, provider_id):
        """The plugin's section of config.yaml: `plugins: {<provider_id>: {...}}` (snake_case keys kept)."""
        return self._host.settings(provider_id)

    def config_dir(self):
        return self._host.config_dir

    def watch(self, path):
        """Rebuild root search when `path` (file or directory) changes."""
        self._host.watch(path)

    def changed(self):
        """Rebuild root search now."""
        self._host.changed.emit()

    def notify(self, style, title):
        """A desktop notification. style: success | failure."""
        self._host.notice.emit(style, title)

    def run_in_background(self, work, done=None):
        """Run work() on a thread; done(result_or_exception) is called back on the main thread."""
        self._host.run_in_background(work, done)


class PluginHost(QObject):
    changed = Signal()
    notice = Signal(str, str)
    _finished = Signal(object, object)

    def __init__(self, config_dir, settings_source, parent=None):
        super().__init__(parent)
        self.config_dir = Path(config_dir)
        self._settings_source = settings_source
        self._providers = {}
        self._errors = []
        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.changed.emit)
        self._watcher.fileChanged.connect(lambda _p: self._debounce.start())
        self._watcher.directoryChanged.connect(lambda _p: self._debounce.start())
        self._finished.connect(self._deliver)

    # ------------------------------------------------------------- loading

    def load_all(self, *directories):
        for directory in directories:
            directory = Path(directory)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if not path.name.startswith("_"):
                    self.load(path)

    def load(self, path):
        name = "xcast_plugin_" + path.stem
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            module.register(Api(self, path.stem))
        except Exception:
            self._record(path.stem, "load", traceback.format_exc())

    def add_provider(self, provider, plugin_name):
        pid = str(getattr(provider, "id", ""))
        if not PROVIDER_ID.match(pid):
            raise ValueError("invalid provider id %r" % pid)
        if pid in self._providers:
            raise ValueError("provider %s is already registered" % pid)
        for method in ("candidates", "actions_for", "perform"):
            if not callable(getattr(provider, method, None)):
                raise ValueError("provider %s lacks %s()" % (pid, method))
        self._providers[pid] = provider

    def settings(self, provider_id):
        plugins = self._settings_source().get("plugins")
        section = plugins.get(provider_id) if isinstance(plugins, dict) else None
        return section if isinstance(section, dict) else {}

    def watch(self, path):
        path = str(path)
        if Path(path).exists() and path not in self._watcher.files() + self._watcher.directories():
            self._watcher.addPath(path)

    def run_in_background(self, work, done):
        def runner():
            try:
                result = work()
            except Exception as e:
                result = e
            self._finished.emit(done, result)
        threading.Thread(target=runner, daemon=True).start()

    def _deliver(self, done, result):
        if done:
            try:
                done(result)
            except Exception:
                self._record("background", "done", traceback.format_exc())

    def _record(self, who, during, text):
        self._errors.append({"plugin": who, "during": during, "error": text})
        print("x-cast: plugin %s failed during %s:\n%s" % (who, during, text), file=sys.stderr)

    # ------------------------------------------------- the QML-facing surface

    def _call(self, provider_id, during, fn, fallback):
        try:
            return fn(self._providers[provider_id])
        except Exception:
            self._record(provider_id, during, traceback.format_exc())
            return fallback

    @Slot(result=str)
    def providers(self):
        return json.dumps([{"id": pid, "hasFallbacks": callable(getattr(p, "fallbacks", None))}
                           for pid, p in self._providers.items()])

    @Slot(str, result=str)
    def candidates(self, provider_id):
        rows = self._call(provider_id, "candidates", lambda p: p.candidates(), [])
        out = []
        for raw in rows or []:
            try:
                out.append(normalize_candidate(provider_id, raw))
            except (KeyError, TypeError):
                self._record(provider_id, "candidates", "a candidate needs at least an 'id': %r" % (raw,))
        return json.dumps(out)

    @Slot(str, str, result=str)
    def fallbacks(self, provider_id, query):
        rows = self._call(provider_id, "fallbacks", lambda p: p.fallbacks(query), [])
        out = []
        for i, raw in enumerate(rows or []):
            raw = dict(raw)
            raw.setdefault("id", "fallback-%d" % i)
            candidate = normalize_candidate(provider_id, raw, searching_only=True)
            candidate["subtitle"] = str(raw.get("subtitle", query))
            candidate["typeLabel"] = str(raw.get("type_label") or "Fallback")
            out.append(candidate)
        return json.dumps(out)

    @Slot(str, str, result=str)
    def actionsFor(self, provider_id, candidate_json):
        candidate = self._local(provider_id, json.loads(candidate_json))
        actions = self._call(provider_id, "actions_for", lambda p: p.actions_for(candidate), [])
        return json.dumps([a for a in actions or [] if isinstance(a, dict) and "id" in a and "title" in a])

    @Slot(str, str, str, str, result=str)
    def perform(self, provider_id, candidate_json, action, ctx_json):
        candidate = self._local(provider_id, json.loads(candidate_json))
        ctx = json.loads(ctx_json)
        try:
            outcome = self._providers[provider_id].perform(candidate, action, ctx)
        except Exception as e:
            self._record(provider_id, "perform", traceback.format_exc())
            message = "%s failed: %s" % (candidate.get("title"), e)
            outcome = {"toast": {"style": "failure", "title": message, "actions": [{"title": "Copy Error", "copy": message}]}}
        return json.dumps(outcome if isinstance(outcome, dict) else None)

    @staticmethod
    def _local(provider_id, candidate):
        """The candidate as the plugin made it: local id, its own data."""
        local = dict(candidate)
        prefix = provider_id + ":"
        if local.get("id", "").startswith(prefix):
            local["id"] = local["id"][len(prefix):]
        return local
