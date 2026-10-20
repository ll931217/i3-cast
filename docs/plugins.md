# Writing x-cast plugins

A plugin is one Python file in `~/.config/x-cast/plugins/`. x-cast loads every `*.py` there (files starting with `_` are skipped) when the host starts. Bundled plugins live in `host/plugins/` and use the same API. Restart the host to pick up a new file (`pkill -f 'host/main.py$'`, then any `x-cast` command starts it again).

A plugin adds a **provider**: a source of rows for root search.

```python
class Notes:
    id = "notes"                                   # lowercase letters, digits, dashes

    def candidates(self):
        return [{"id": "inbox", "title": "Open Inbox", "subtitle": "Notes", "keywords": ["todo"]}]

    def actions_for(self, candidate):
        return [{"id": "open", "title": "Open Inbox"}]   # the first action runs on Enter

    def perform(self, candidate, action, ctx):
        # ctx = {"query": str, "arguments": [str, ...]}
        return {"close": True, "visit": True}

def register(api):
    api.add_provider(Notes())
```

## Candidate fields

`id` is required. The rest are optional.

| Field | Meaning |
|---|---|
| `title`, `subtitle` | Row text. |
| `keywords` | Extra words that match in search. |
| `type_label` | Right-hand label, and the entry in the Ctrl+P type filter. Default `Command`. |
| `icon` | Absolute path to an image. |
| `glyph` | A Nerd Font glyph, used when there is no icon. |
| `arguments` | Up to three pills: `{"placeholder", "type": "text" or "password" or "dropdown", "optional", "data": [options]}`. |
| `data` | Anything JSON. It comes back to you in `actions_for` and `perform`. |
| `category` | Which of your `filters()` entries this row belongs to. |
| `root` | `"always"` (default), `"searching"` (only when a query is typed) or `"empty"`. |

x-cast prefixes ids with your provider id so plugins cannot collide. Your code always sees its own short id.

## Outcomes

`perform` returns a dict, or `None` for "not mine".

| Key | Effect |
|---|---|
| `close` | Hide the launcher. |
| `visit` | Count it as a launch for ranking. |
| `toast` | `{"style": "success" or "failure", "title": str, "actions": [...]}`. A toast action is `{"title", "copy": text}` or `{"title", "open": url}`. Ctrl+T opens them. |
| `hud` | Text for a desktop notification once the window closes. |

An exception in `perform` is caught and shown as a failure toast with a "Copy Error" action. A plugin that fails to load is skipped, and the traceback goes to the host's stderr.

## Optional provider methods

`answers(query)` returns candidate dicts shown above the results for that exact query, unstored and unranked. Their `perform` and `actions_for` work as usual. The bundled calculator uses it.

`filters()` returns `[{"id", "title"}]`. They are added to the Ctrl+P dropdown, and picking one shows only your rows whose `category` equals its id.

`fallbacks(query)` returns rows for the "Use "query" with..." section. Each row is a candidate dict whose `perform` gets the query in `ctx["query"]`.

## The `api` object

| Call | Use |
|---|---|
| `api.add_provider(provider)` | Register a provider. |
| `api.settings(provider_id)` | Your section of `config.yaml`: `plugins: {<id>: {...}}`. |
| `api.config_dir()` | `~/.config/x-cast` as a `Path`. |
| `api.watch(path)` | Refresh the rows when this file or folder changes. |
| `api.changed()` | Refresh the rows now. |
| `api.notify(style, text)` | Desktop notification. |
| `api.copy(text)` | Put text on the clipboard (xclip). |
| `api.run_in_background(work, done)` | Run `work()` on a thread. `done(result)` runs on the UI thread. |

Never block in `candidates`, `actions_for` or `perform`. They run on the UI thread. Use `run_in_background` for anything slow.

## Script Commands

The bundled `script_commands.py` reads Raycast-format scripts from `~/.config/x-cast/script-commands` (override with `plugins: {script-commands: {directories: [...]}}`). Scripts must be executable and start with:

```bash
#!/bin/bash
# @raycast.schemaVersion 1
# @raycast.title Say Hello
# @raycast.mode compact
# @raycast.argument1 { "type": "text", "placeholder": "Name" }
echo "hello $1"
```

Press Tab to move into the argument pills, type a value, then Enter. All modes (`compact`, `silent`, `fullOutput`) run in the background and show the last output line as a notification. `inline` scripts need `# @raycast.refreshTime 10s` (or `5m`, `1h`, `1d`; at least 10 s) and no arguments. Their last output line becomes the row's subtitle and refreshes in the background. `# @raycast.needsConfirmation true` asks for a second Enter within 5 seconds. Each script's `packageName` is a Ctrl+P filter.
