"""Script Commands: Raycast-style scripts in a folder become root-search commands.

Scripts live in ~/.config/x-cast/script-commands (non-recursive). Metadata is read from
`# @raycast.<key> <value>` comment lines (also `//`, `REM`, `::`), the same as Raycast's
format, so scripts from raycast/script-commands work unchanged.

Supported: title, mode, packageName, icon, description, currentDirectoryPath, argument1..3.
[D] Every mode runs in the background and reports its last output line as a notice:
fullOutput, compact and silent behave alike; inline refresh and needsConfirmation are ignored.
"""
import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

HEADER = re.compile(r"^(?:#|REM|::|//)\s*@raycast\.(\w+)\s+(.*)", re.IGNORECASE)
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
MAX_BYTES = 2 * 1024 * 1024
HEADER_LINES = 60
TIMEOUT_SECONDS = 120


def parse_header(text):
    """{key: value} from the leading comment block, keys lower-cased."""
    meta = {}
    for line in text.splitlines()[:HEADER_LINES]:
        m = HEADER.match(line.strip())
        if m:
            meta[m.group(1).lower()] = m.group(2).strip()
    return meta


def parse_script(path, text):
    """A command description, or None when the file is not a valid script command."""
    meta = parse_header(text)
    if meta.get("schemaversion") != "1" or not meta.get("title") or not meta.get("mode"):
        return None
    arguments = []
    for i in (1, 2, 3):
        raw = meta.get("argument%d" % i)
        if raw is None:
            continue
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError:
            return None
        arguments.append({
            "name": "argument%d" % i,
            "placeholder": spec.get("placeholder", "Argument %d" % i),
            "type": spec.get("type", "text"),
            "optional": bool(spec.get("optional", False)),
            "percentEncoded": bool(spec.get("percentEncoded", False)),
            "data": [d.get("value", d.get("title")) if isinstance(d, dict) else d for d in spec.get("data", [])],
        })
    package = meta.get("packagename") or path.parent.name.replace("-", " ").replace("_", " ").title()
    return {
        "path": str(path),
        "title": meta["title"],
        "mode": meta["mode"].replace("-", "").lower(),
        "package": package,
        "icon": meta.get("icon", ""),
        "description": meta.get("description", ""),
        "cwd": meta.get("currentdirectorypath", "."),
        "arguments": arguments,
    }


def scan(directory):
    found = []
    for path in sorted(Path(directory).glob("*")):
        try:
            if not path.is_file() or ".template." in path.name or not os.access(path, os.X_OK):
                continue
            if path.stat().st_size > MAX_BYTES or path.stat().st_size == 0:
                continue
            script = parse_script(path, path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if script:
            found.append(script)
    return found


def build_args(script, values):
    """Positional arguments for the script, or raise ValueError with a user-facing message."""
    args = []
    for i, spec in enumerate(script["arguments"]):
        value = (values[i] if i < len(values) else "") or ""
        if not value and not spec["optional"]:
            raise ValueError("%s is required" % spec["placeholder"])
        if value and spec["type"] == "dropdown" and spec["data"] and value not in spec["data"]:
            raise ValueError("%s must be one of: %s" % (spec["placeholder"], ", ".join(spec["data"])))
        args.append(urllib.parse.quote(value, safe="") if spec["percentEncoded"] else value)
    return args


def last_line(output):
    lines = [ANSI.sub("", l).strip() for l in output.splitlines()]
    lines = [l for l in lines if l]
    return lines[-1] if lines else ""


def run_script(script, args):
    """(ok, message): exit 0 is success; the message is the last non-empty output line."""
    cwd = (Path(script["path"]).parent / script["cwd"]).resolve()
    try:
        done = subprocess.run([script["path"], *args], cwd=cwd, capture_output=True, text=True,
                              errors="replace", timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "%s timed out after %ds" % (script["title"], TIMEOUT_SECONDS)
    message = last_line(done.stdout) or last_line(done.stderr)
    if done.returncode == 0:
        return True, message or "%s finished" % script["title"]
    return False, message or "%s failed (exit %d)" % (script["title"], done.returncode)


class ScriptCommands:
    id = "script-commands"

    def __init__(self, api):
        self.api = api
        settings = api.settings(self.id)
        configured = settings.get("directories")
        self.directories = [Path(d).expanduser() for d in configured] if isinstance(configured, list) and configured \
            else [api.config_dir() / "script-commands"]
        for directory in self.directories:
            directory.mkdir(parents=True, exist_ok=True)
            api.watch(directory)

    def candidates(self):
        rows = []
        for directory in self.directories:
            for script in scan(directory):
                rows.append({
                    "id": script["path"],
                    "title": script["title"],
                    "subtitle": script["package"],
                    "keywords": [script["description"]] if script["description"] else [],
                    "type_label": "Script",
                    "icon": script["icon"] if script["icon"].startswith("/") else "",
                    "arguments": script["arguments"],
                    "data": script,
                })
        return rows

    def actions_for(self, candidate):
        return [{"id": "run", "title": "Run Script", "icon": ""}]

    def perform(self, candidate, action, ctx):
        if action not in ("run", "open"):
            return None
        script = candidate["data"]
        try:
            args = build_args(script, ctx.get("arguments") or [])
        except ValueError as e:
            return {"toast": {"style": "failure", "title": str(e)}}

        def done(result):
            ok, message = result if isinstance(result, tuple) else (False, str(result))
            self.api.notify("success" if ok else "failure", message)

        self.api.run_in_background(lambda: run_script(script, args), done)
        return {"close": True, "visit": True}


def register(api):
    api.add_provider(ScriptCommands(api))
