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
import os
import re
import subprocess
import sys
import threading
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal, Slot

PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*$")
PLUGIN_FILE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.py$")
MAX_ARGUMENTS = 3
MAX_PLUGIN_BYTES = 1 << 20
DOWNLOAD_SECONDS = 15
STATE_FILE = "plugin-state.json"


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
        "category": str(raw.get("category") or ""),
        "section": str(raw.get("section") or ""),
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

    def data_dir(self):
        """$XDG_DATA_HOME/x-cast as a Path, for state a plugin keeps."""
        return self._host.data_dir

    def watch(self, path):
        """Rebuild root search when `path` (file or directory) changes."""
        self._host.watch(path)

    def changed(self):
        """Rebuild root search now."""
        self._host.changed.emit()

    def notify(self, style, title):
        """A desktop notification. style: success | failure."""
        self._host.notice.emit(style, title)

    def copy(self, text):
        """Put text on the clipboard (needs xclip)."""
        self._host.copy(text)

    def run_in_background(self, work, done=None):
        """Run work() on a thread; done(result_or_exception) is called back on the main thread."""
        self._host.run_in_background(work, done)


class PluginHost(QObject):
    changed = Signal()
    notice = Signal(str, str)
    installed = Signal(str)   # JSON {ok, name?, error?} when an install attempt ends
    _finished = Signal(object, object)

    def __init__(self, config_dir, settings_source, parent=None):
        super().__init__(parent)
        self.config_dir = Path(config_dir)
        override = os.environ.get("X_CAST_DATA_DIR")
        base = os.environ.get("XDG_DATA_HOME")
        self.data_dir = Path(override) if override else \
            Path(base if base and base.startswith("/") else Path.home() / ".local" / "share") / "x-cast"
        self.plugin_dir = self.config_dir / "plugins"
        self._settings_source = settings_source
        self._providers = {}
        self._plugins = {}       # file stem -> {path, bundled, providers: [id], error}
        self._disabled = self._read_disabled()
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

    def load_all(self, *directories, bundled=False):
        for directory in directories:
            directory = Path(directory)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if not path.name.startswith("_"):
                    self.load(path, bundled=bundled)

    def load(self, path, bundled=False):
        """Load one plugin file. Returns None, or the error text when it failed."""
        path = Path(path)
        entry = {"path": path, "bundled": bundled, "providers": [], "error": None}
        self._plugins[path.stem] = entry
        name = "xcast_plugin_" + path.stem
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            module.register(Api(self, path.stem))
        except Exception:
            text = traceback.format_exc()
            entry["error"] = text.strip().splitlines()[-1]
            self._record(path.stem, "load", text)
            self._unload(path.stem, keep_entry=True)
            return entry["error"]
        return None

    def _unload(self, stem, keep_entry=False):
        entry = self._plugins.get(stem)
        if entry:
            for pid in entry["providers"]:
                self._providers.pop(pid, None)
            entry["providers"] = []
            if not keep_entry:
                del self._plugins[stem]
        sys.modules.pop("xcast_plugin_" + stem, None)

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
        if plugin_name in self._plugins:  # a provider added without a file is not listed
            self._plugins[plugin_name]["providers"].append(pid)

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
        # Diagnostics must not grow without bound over repeated search refreshes.
        who, during, text = str(who)[:120], str(during)[:80], str(text)[:1000]
        self._errors.append({"plugin": who, "during": during, "error": text})
        del self._errors[:-100]
        print("x-cast: plugin %s failed during %s:\n%s" % (who, during, text), file=sys.stderr)

    def _failure(self, provider_id, during, error, entry=None):
        # Exception messages, reprs and tracebacks can contain passwords/data.
        text = "entry %d: " % entry if entry is not None else ""
        text += "plugin operation failed (%s)" % type(error).__name__[:120]
        self._record(provider_id, during, text)
        return text

    def _list(self, provider_id, during, invoke, normalize):
        """Contain invocation, normalization and strict serialization at the slot seam."""
        try:
            rows = invoke(self._providers[provider_id])
            if not isinstance(rows, list):
                raise TypeError("expected list")
            out = []
            for i, raw in enumerate(rows):
                try:
                    if not isinstance(raw, dict):
                        raise TypeError("expected object entry")
                    out.append(json.dumps(normalize(raw, i), allow_nan=False))
                except Exception as error:
                    self._failure(provider_id, during, error, i)
            return "[" + ",".join(out) + "]"
        except Exception as error:
            self._failure(provider_id, during, error)
            return "[]"

    # ------------------------------------------- enabling, adding, removing

    def _state_path(self):
        return self.data_dir / STATE_FILE

    def _read_disabled(self):
        try:
            rows = json.loads(self._state_path().read_text()).get("disabled", [])
        except (OSError, ValueError, AttributeError):
            return set()
        return {r for r in rows if isinstance(r, str)}

    def _write_disabled(self):
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._state_path().write_text(json.dumps({"disabled": sorted(self._disabled)}))
        except OSError as e:
            self._record("host", "state", str(e))

    def locked(self, provider_id):
        """config.yaml `plugins: {<id>: {enabled: false}}` wins over the settings window."""
        return self.settings(provider_id).get("enabled") is False

    def enabled(self, provider_id):
        return not self.locked(provider_id) and provider_id not in self._disabled

    def _install_bytes(self, name, data):
        """Check and write a plugin file, then load it. Returns the result dict."""
        if not PLUGIN_FILE.match(name):
            return {"ok": False, "error": "the file name must be letters, digits and underscores, ending in .py"}
        stem = name[:-3]
        target = self.plugin_dir / name
        if stem in self._plugins or target.exists():
            return {"ok": False, "error": "a plugin named %s is already installed; remove it first" % stem}
        try:
            text = data.decode("utf-8")
            compile(text, name, "exec")
        except (UnicodeDecodeError, SyntaxError) as e:
            return {"ok": False, "error": "not a valid Python file: %s" % e}
        if not re.search(r"^def register\(", text, re.MULTILINE):
            return {"ok": False, "error": "no register(api) function; see docs/plugins.md"}
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        error = self.load(target)
        if error:
            self._unload(stem)
            target.unlink(missing_ok=True)
            return {"ok": False, "error": error}
        self.changed.emit()
        return {"ok": True, "name": stem}

    @staticmethod
    def _fetch(source):
        """(file name, bytes) for a local path or an http(s) URL. Runs on a worker thread."""
        source = source.strip()
        if re.match(r"^https?://", source, re.IGNORECASE):
            name = Path(urllib.parse.urlparse(source).path).name
            with urllib.request.urlopen(source, timeout=DOWNLOAD_SECONDS) as response:
                data = response.read(MAX_PLUGIN_BYTES + 1)
        else:
            path = Path(source).expanduser()
            name = path.name
            with open(path, "rb") as f:
                data = f.read(MAX_PLUGIN_BYTES + 1)
        if len(data) > MAX_PLUGIN_BYTES:
            raise ValueError("the file is larger than %d KiB" % (MAX_PLUGIN_BYTES // 1024))
        return name, data

    def _finish_install(self, result):
        if isinstance(result, Exception):
            outcome = {"ok": False, "error": "could not read it: %s" % result}
        else:
            outcome = self._install_bytes(*result)
        self.installed.emit(json.dumps(outcome))

    @Slot(str)
    def install(self, source):
        """Add a plugin from a .py path or URL. The outcome arrives on `installed`."""
        if not source.strip():
            self.installed.emit(json.dumps({"ok": False, "error": "enter a path or an https:// link to a .py file"}))
            return
        self.run_in_background(lambda: self._fetch(source), self._finish_install)

    @Slot(str, result=str)
    def remove(self, name):
        """Delete a plugin you added. Bundled plugins can be turned off but not deleted."""
        entry = self._plugins.get(name)
        if entry is None:
            return json.dumps({"ok": False, "error": "no plugin named %s" % name})
        if entry["bundled"]:
            return json.dumps({"ok": False, "error": "%s ships with x-cast; turn it off instead" % name})
        ids = list(entry["providers"])
        self._unload(name)
        try:
            entry["path"].unlink(missing_ok=True)
        except OSError as e:
            return json.dumps({"ok": False, "error": str(e)})
        self._disabled.difference_update(ids)
        self._write_disabled()
        self.changed.emit()
        return json.dumps({"ok": True})

    @Slot(str, bool, result=str)
    def setEnabled(self, provider_id, enabled):
        if provider_id not in self._providers:
            return json.dumps({"ok": False, "error": "no provider %s" % provider_id})
        if self.locked(provider_id):
            return json.dumps({"ok": False, "error": "config.yaml turns %s off; edit it there" % provider_id})
        (self._disabled.discard if enabled else self._disabled.add)(provider_id)
        self._write_disabled()
        self.changed.emit()
        return json.dumps({"ok": True})

    @Slot(result=str)
    def plugins(self):
        """Every plugin file with its providers, for the settings window."""
        return json.dumps([{
            "name": stem, "file": str(e["path"]), "bundled": e["bundled"], "error": e["error"],
            "providers": [{"id": pid, "enabled": self.enabled(pid), "locked": self.locked(pid)} for pid in e["providers"]],
        } for stem, e in sorted(self._plugins.items(), key=lambda kv: (not kv[1]["bundled"], kv[0]))])

    # ------------------------------------------------- the QML-facing surface

    @Slot(result=str)
    def providers(self):
        out = []
        for pid, provider in self._providers.items():
            if not self.enabled(pid):
                continue
            try:
                out.append(json.dumps({"id": pid, "hasFallbacks": callable(getattr(provider, "fallbacks", None)),
                                       "hasFilters": callable(getattr(provider, "filters", None)),
                                       "hasAnswers": callable(getattr(provider, "answers", None))}, allow_nan=False))
            except Exception as error:
                self._failure(pid, "providers", error)
        return "[" + ",".join(out) + "]"

    @Slot(str, str, result=str)
    def answers(self, provider_id, query):
        return self._list(provider_id, "answers", lambda p: p.answers(query),
                          lambda raw, i: normalize_candidate(provider_id, {"id": "answer-%d" % i, **raw}))

    def copy(self, text):
        try:
            proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            proc.stdin.write(str(text).encode())
            proc.stdin.close()
        except OSError as e:
            self._record("host", "copy", str(e))

    @Slot(str, result=str)
    def filters(self, provider_id):
        return self._list(provider_id, "filters", lambda p: p.filters(),
                          lambda raw, i: {"id": str(raw["id"]), "title": str(raw.get("title") or raw["id"])})

    @Slot(str, result=str)
    def candidates(self, provider_id):
        return self._list(provider_id, "candidates", lambda p: p.candidates(),
                          lambda raw, i: normalize_candidate(provider_id, raw))

    @Slot(str, str, result=str)
    def fallbacks(self, provider_id, query):
        def normalize(raw, i):
            candidate = normalize_candidate(provider_id, {"id": "fallback-%d" % i, **raw}, searching_only=True)
            candidate["subtitle"] = str(raw.get("subtitle", query))
            candidate["typeLabel"] = str(raw.get("type_label") or "Fallback")
            return candidate
        return self._list(provider_id, "fallbacks", lambda p: p.fallbacks(query), normalize)

    @Slot(str, str, result=str)
    def actionsFor(self, provider_id, candidate_json):
        def invoke(provider):
            candidate = self._local(provider_id, self._decode(candidate_json))
            return provider.actions_for(candidate)
        def normalize(raw, i):
            if (not isinstance(raw.get("id"), str) or not raw["id"]
                    or not isinstance(raw.get("title"), str) or not raw["title"]):
                raise TypeError("action needs non-empty id and title strings")
            return raw
        return self._list(provider_id, "actions_for", invoke, normalize)

    @Slot(str, str, str, str, result=str)
    def perform(self, provider_id, candidate_json, action, ctx_json):
        invoked = False
        try:
            candidate = self._local(provider_id, self._decode(candidate_json))
            ctx = self._decode(ctx_json)
            if not isinstance(ctx, dict):
                raise TypeError("expected context object")
            if "query" in ctx and not isinstance(ctx["query"], str):
                raise TypeError("expected query string")
            if "arguments" in ctx and (not isinstance(ctx["arguments"], list)
                                       or not all(isinstance(a, str) for a in ctx["arguments"])):
                raise TypeError("expected argument strings")
            perform = self._providers[provider_id].perform
            invoked = True
            outcome = perform(candidate, action, ctx)
            self._validate_outcome(outcome)
            return json.dumps(outcome, allow_nan=False)
        except Exception as error:
            detail = self._failure(provider_id, "perform", error)
            message = "%s perform failed: %s" % (str(provider_id)[:120], detail)
            if invoked:
                message += "; side effects may already have occurred"
            return json.dumps({"toast": {"style": "failure", "title": message,
                                        "actions": [{"title": "Copy Error", "copy": message}]}}, allow_nan=False)

    @staticmethod
    def _decode(text):
        def invalid_constant(value):
            raise ValueError("non-finite JSON number")
        return json.loads(text, parse_constant=invalid_constant)

    @staticmethod
    def _validate_outcome(outcome):
        # Unknown fields are deliberately retained for forward-compatible wire JSON.
        if outcome is None:
            return
        if not isinstance(outcome, dict):
            raise TypeError("expected outcome object or None")
        for key in ("close", "visit", "settings"):
            if key in outcome and not isinstance(outcome[key], bool):
                raise TypeError("expected outcome boolean")
        if "hud" in outcome and not isinstance(outcome["hud"], str):
            raise TypeError("expected HUD text")
        if "push" in outcome and not isinstance(outcome["push"], dict):
            raise TypeError("expected navigation object")
        if "prompt" in outcome:
            prompt = outcome["prompt"]
            if (not isinstance(prompt, dict) or prompt.get("kind") not in ("arguments", "confirmation")
                    or ("title" in prompt and not isinstance(prompt["title"], str))
                    or "close" in outcome or "visit" in outcome):
                raise TypeError("invalid prompt outcome")
        if "toast" in outcome:
            toast = outcome["toast"]
            if (not isinstance(toast, dict) or toast.get("style") not in ("success", "failure")
                    or not isinstance(toast.get("title"), str)):
                raise TypeError("invalid toast")
            actions = toast.get("actions", [])
            if not isinstance(actions, list):
                raise TypeError("expected toast actions list")
            for action in actions:
                if (not isinstance(action, dict) or not isinstance(action.get("title"), str)
                        or not ("copy" in action or "open" in action)):
                    raise TypeError("invalid toast action")
                for key in ("copy", "open"):
                    if key in action and not isinstance(action[key], str):
                        raise TypeError("expected toast action text")

    @staticmethod
    def _local(provider_id, candidate):
        """The candidate as the plugin made it: local id, its own data."""
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise TypeError("expected candidate object with string id")
        local = dict(candidate)
        prefix = provider_id + ":"
        if local.get("id", "").startswith(prefix):
            local["id"] = local["id"][len(prefix):]
        return local
