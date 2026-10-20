# CLAUDE.md

This repo is a clean-room rebuild of **Raycast for Linux**. The first target is **Omarchy**: Arch Linux + Hyprland, plus Omarchy's own scripts, themes and bindings. The behaviour and interfaces come from a static reverse-engineering pass over Raycast 2.8.2 on macOS, done with the `reverse-engineer-anything` skill. This repo holds that pass's results and no Raycast code.

## Read these first

| File | What it is | When to read it |
|---|---|---|
| `SPEC.md` | **The plan.** Architecture, IPC contract, platform matrix, data layer, root-search algorithm, feature catalog, extension runtime, frontend, `.rayconfig` import, phased build plan with acceptance checks. | Before any work. Re-read the relevant section before each phase. |
| `reference/01-host-ipc.md` | Native host: window model, ~408 host capabilities (§4.1), WebView bridge, host↔backend wire protocol, helper processes, a Linux mapping for each (§4.3). | Phase 1 (window), Phase 5 (supervisor, for the Node extension host), Phase 6 (WM) |
| `reference/02-backend.md` | Backend service map and RPC methods, DB engine, **root-search ranking (§4)**, frecency (§4.6), clipboard (§5.1), snippet placeholder grammar (§5.2), quicklinks (§6), calculator, indexer. | Phases 1–4, 7 |
| `reference/03-extensions.md` | `@raycast/api` runtime: worker model, reconciler, **render-tree JSON schema (§2.4)**, API→RPC table (§3.2), manifest (§4), Script Commands (§5), install pipeline (§6), Icon enum (App. A). | Phase 2 (script commands), Phase 5 |
| `reference/04-frontend-features.md` | **Built-in command catalog (§1, App. A)**, launcher UI anatomy (§2), default shortcuts (§2.8), settings pages (§3, App. B/C), themes and design tokens (§4). | Phase 1 onward, every UI task |
| `reference/05-data-config.md` | On-disk layout, DB encryption, reconstructed schema, `.rayconfig` format (§5), XDG mapping (§8). | Phase 0 (paths, DB), Phase 8 (import) |
| `reference/schema-nonai.sql` | Raycast's non-AI DDL, reconstructed. **Reference only.** The clone uses the simpler schema in `SPEC.md §6.4`. | When you need a field Raycast stores |
| `reference/backend-methods-nonai.txt` | Every non-AI backend RPC method name. **Do not implement all of them.** Reuse the names for what each phase needs. | When naming an IPC method |

Spec legend: **[O]** observed in Raycast, **[I]** inferred, **[D]** design decision for this clone. [O] is ground truth for behaviour. [D] may be changed if you have a reason; note the change in `SPEC.md`.

## Ground rules (from SPEC.md §0, non-negotiable)

1. **Clean room.** Never copy, bundle or redistribute anything from `Raycast.app` (JS, icons, fonts, `.node` modules). Allowed: the public npm `@raycast/api` / `@raycast/utils` packages (check the license of the pinned version) and the MIT `raycast/extensions` repo.
2. **Never call `*.raycast.com`.** No store, account, sync, telemetry or currency APIs. Build extensions from a local `raycast/extensions` clone.
3. **No telemetry.** No Sentry, no PostHog.
4. **No AI features.** Where a built-in mixes AI and non-AI behaviour, build the non-AI path and leave a `// AI: not implemented` comment.
5. **Port the root-search ranker exactly** from `reference/02-backend.md §4.2–4.5`. Do not substitute fzf, nucleo or fuse.js.

## How to work

- Build **phase by phase** following `SPEC.md §12` (Phase 0 → 9). A phase is done only when its **Accept** checks pass. Then move on.
- After each phase, update the **Status** section at the bottom of this file: what works, what's stubbed, and any deviations from the spec.
- If the reference docs don't answer a question, choose a sensible value, mark it `[I]` or `[D]` in a code comment, and keep going. Raycast.app is not on the Omarchy machine. Re-running the reverse-engineering only works on the Mac where `/Applications/Raycast.app` lives.
- The working name is **`x-cast`**: plugin id `typecraft.x-cast`, CLI `x-cast`, IPC target `x-cast`, layer namespace `x-cast`, URL scheme `x-cast://` (later). Also register `raycast://` for extension deep links (SPEC §5.5).

## Architecture: a Qt host for X11 (i3)

`plugin/` is QML plus plain JS. `host/` runs it under PySide6 on any X11 window manager, with `host/qml/qs/*` and `host/qsshim.py` standing in for the Quickshell types `plugin/` imports. There is no Omarchy, Hyprland, Wayland or Quickshell dependency. **Keep dependencies near zero:** PySide6-Essentials and PyYAML (both in `host/requirements.txt`) plus system `nc`, `xclip`, `xdg-open`, `notify-send`. Ask before adding more.

Gotchas:
- A Python `QQuickImageProvider` deadlocks (Qt loads images on its own thread while the main thread holds the GIL), so icons are `file://` URLs from `host/apps.py`.
- Typed `ShellIpc` parameters turn a missing argument into the string `"undefined"`; `host/main.py` pads them.
- Without a compositor a window cannot be transparent, so `OverlayWindow` shapes the window to the card with `QWindow.setMask`.
- Never kill the host with `pkill -f main.py` from a command that contains that text; it kills your own shell.

## Repo layout

```
SPEC.md, reference/      # the spec (Raycast behaviour); the Tauri/Node and Omarchy parts of it are history
plugin/                  # the launcher UI and backend, host-agnostic QML
  Launcher.qml           #   entry point: show/hide/toggle, ShellIpc "x-cast"
  Backend.qml            #   in-process backend: stores, method registry, actions
  ui/, services/         #   launcher window, rows, action panel; JsonStore
  core/*.js              #   pure logic, no Qt imports, shared by QML and node tests (module.exports guard)
host/                    # the X11 host
  main.py                #   app, QML engine, control socket
  qsshim.py              #   Quickshell API on plain Qt (Process, FileView, ...)
  apps.py                #   desktop entries, icon index, window placement
  userconfig.py          #   config.yaml and theme.yaml, live reload
  qml/qs/{Commons,Ui}    #   Style, Color, Util, ShellIpc, OverlayWindow, BorderSurface
bin/x-cast               # bash CLI over the control socket
tests/*.test.js          # node --test unit tests for plugin/core
tests/smoke.sh           # live check against the running host
```

Rules for `plugin/core/*.js`: one self-contained file per module (QML `import "x.js"` and node `require` must both work, so a module never imports another one). Expose functions through the `if (typeof module !== "undefined") module.exports = …` guard. QML wires the modules together.

## Commands

```sh
node --test tests/*.test.js        # unit tests (a bare `tests/` directory argument fails on Node 24)
tests/smoke.sh                     # live checks: doctor, IPC, search, show latency
bin/x-cast host                    # run the host in the foreground
bin/x-cast setup i3                # symlink the CLI, bind $mod+d
bin/x-cast toggle | show | hide
bin/x-cast call <method> [json]    # any backend method, e.g. system.info
```

Options: `~/.config/x-cast/config.yaml` (behaviour, search fallbacks) and `theme.yaml` (colors, fonts). Both are written with defaults on first run and reload on save. `plugin/core/Schema.js` validates `config.yaml`; `host/qml/qs/Commons/{Color,Style}.qml` read `theme.yaml`.

Testing on the live desktop: don't synthesize keystrokes (`xdotool`) unless the launcher is open and `xdotool getactivewindow` equals `xdotool search --class x-cast`. The window opens on the screen under the pointer.

## Status

Renamed **raylinux → oma-launcher → oma-cast** on 2026-10-19, then **oma-cast → x-cast** on 2026-10-20 when the X11/i3 host was added (CLI `x-cast`, socket `x-cast.sock`, XDG dirs `x-cast`). The root search icon is a Nerd Font glyph; `theme.yaml` picks the font.

**Phase 1 (Quickshell build): done**, with the gaps listed below. **Phase 0: done.** Omarchy 4.0.0.alpha, Quickshell 0.3.2, Hyprland 0.56.2.

Works:
- **Root search** ported from ref 02 §4.2–4.6 (`core/Ranker.js`, `core/Frecency.js`, golden tests). Sections (`core/RootSearch.js`):
  - empty root: Favorites, Suggestions (frecency > 1, top 6), Commands, Applications
  - query: Results, then `Use "<q>" with…` (Google, DuckDuckGo fallbacks)
- **Providers:** apps from `shell.appLibrary`, the whole Omarchy menu (about 400 items, with breadcrumbs, guards, ✓ state and font/power-profile provider rows), and the built-in "Omarchy Menu".
- **Ranking state:** frecency (+100 per launch, 10-day half-life) and learned search terms in `db/frecency.json`. Aliases (exact → top; duplicates rejected), favourites (Ctrl+Shift+F, reorder Ctrl+Alt+↑↓) and disabled commands live in `db/settings.json` `commands`.
- **Navigation:** pushed Omarchy submenus (search within them), the alias editor, back with Esc / Ctrl+[ / Backspace on an empty query / the header arrow, and Shift+Esc to pop to root.
- **Keyboard:** Ctrl+K action panel (filterable, per-row shortcuts), ↵ / Ctrl+↵ / Ctrl+Shift+↵ for the first three actions, Ctrl+1–9, Ctrl+↑↓ to jump sections, PageUp/PageDown, Ctrl+N/P (emacs), ↑ on an empty root for search history, Ctrl+Shift+C copy, Alt+Shift+D disable, Ctrl + / − / 0 zoom.
- **Feedback:** toasts in the footer, a HUD through Omarchy's OSD when the window closes, and a 2 px loading bar while guards and providers refresh (on every open, about 250 ms in the background).
- **Window behaviour:**
  - The `escapeKeyBehavior` setting works both ways.
  - Pop-to-root runs after `popToRootTimeout`.
  - Compact mode shows only the header until you type.
  - A launch from root clears the query [I].
  - A row is selected on hover only after a real pointer move (Omarchy's PointerMoveGate).
- **Latency:** show → mapped in 37–44 ms, hide in 9–25 ms (`tests/smoke.sh`).
- **Tests:** 65 unit tests (`node --test tests/`).

Stubbed / not yet:
- Keystroke buffering before the surface maps. Keys sent within ~40 ms of the hotkey go to the window underneath.
- Vim navigation bindings, Ctrl+P dropdown, Ctrl+T, Ctrl+Shift+K, inline argument pills, alerts.
- No settings window, so you can't re-enable a disabled command except by editing `~/.local/share/x-cast/db/settings.json` (delete its `enabled: false`). That's Phase 2.
- No deep links (`x-cast://`); Phase 2 or 9.

Deviations from the original spec (SPEC §2.0 and the Phase 1 note in §12):
- A Quickshell plugin instead of Tauri + Node; there's no NDJSON supervisor until Phase 5.
- JSON documents instead of SQLite; no DB encryption or libsecret key.
- Logs go to the shell log; `config.json` instead of `config.toml`; no D-Bus name.
- The Omarchy theme replaces Raycast's 8 themes; the HUD is Omarchy's OSD.

Testing lesson: the query survives hide/show until pop-to-root. A live test must clear it first (Ctrl+U), or typed text gets appended to the old query. Pressing ↵ on a stale query once opened real browser tabs.

**x-cast on X11 (2026-10-20, branch `i3-x11-host`).** All Omarchy options are gone: no Omarchy menu provider, `omarchy-*` actions, Hyprland shortcut or manifest. App search, aliases, favorites, frecency, the action panel and `Ctrl+K` work as before. New: the PySide6 host, `$mod+d` binding via `x-cast setup i3`, `config.yaml` and `theme.yaml`.
Plugins (2026-10-20): Python files in `~/.config/x-cast/plugins/*.py` and `host/plugins/` register providers (`host/plugins.py`, `plugin/core/{Providers,ExternalProvider}.js`, `docs/plugins.md`). Bundled: Script Commands. Also done: argument pills (Tab), vim motions, Ctrl+P type filter, Ctrl+T toast actions, settings window (`plugin/ui/SettingsWindow.qml`, `x-cast settings`). Tests: `node --test tests/*.test.js` and `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
Not done: dropdowns declared by plugins (Ctrl+P lists types only), per-command hotkeys, `.rayconfig` import, `x-cast://` deep links, inline script modes. Verified live on i3/xrdp: Enter-launch, `active-screen`, pills, filter, vim keys, toast actions, settings window. `plugin/core/Paths.js` still lists directories for later phases.
