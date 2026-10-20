# x-cast

A Raycast-style launcher for X11 window managers (i3). It learns what you use, ranks results with a port of Raycast's root-search algorithm, and is configured with two YAML files.

* **Learns your habits.** Frecency and learned search terms: if you type `ff` and pick Firefox, `ff` keeps meaning Firefox.
* **Your shortcuts.** Give any app an alias, pin favorites, hide what you never use.
* **Keyboard-first.** Ctrl+K action panel, Ctrl+1–9 quick picks, search history on ↑, emacs-style navigation.
* **Light.** Plain Qt (PySide6) with no Electron or Node. The window opens in about 45 ms.

## Install

Needs Python 3.10+, `nc` (netcat-openbsd), `xclip`, `xdg-open` and `notify-send`.

```sh
git clone https://github.com/ll931217/i3-cast.git && cd i3-cast
python3 -m venv .venv && .venv/bin/pip install -r host/requirements.txt
bin/x-cast setup i3      # symlink ~/.local/bin/x-cast, bind $mod+d (your old $mod+d line is commented out)
bin/x-cast doctor        # check the pieces
```

Reload i3, then press `$mod+d`. The host starts on first use and stays running.

## Configure

`~/.config/x-cast/config.yaml` and `theme.yaml` are created with every option and its default on first run. Saved changes apply live.

```yaml
# config.yaml
general:
  window_mode: compact      # expanded | compact
  ui_zoom: 1.2
fallbacks:
  - title: Search Kagi
    url: https://kagi.com/search?q={query}
```

```yaml
# theme.yaml
colors:
  background: "#1a1b26"
  selected_text: "#7aa2f7"
font:
  family: Sans
  icon_family: JetBrainsMono Nerd Font
corner_radius: 8
```

## Keyboard

| Key | Does |
|---|---|
| `↵` / `Ctrl+↵` / `Ctrl+Shift+↵` | Run the first, second or third action |
| `Ctrl+K` | Open the action panel |
| `Ctrl+1`…`9` | Pick a result |
| `↑` on an empty search | Search history |
| `Ctrl+↑` / `Ctrl+↓` | Jump between sections |
| `Ctrl+N` / `Ctrl+P` | Next / previous |
| `Ctrl+Shift+F` | Add to favorites (`Ctrl+Alt+↑↓` to reorder) |
| `Ctrl+Shift+C` | Copy desktop id |
| `Alt+Shift+D` | Disable a command |
| `Esc` / `Shift+Esc` | Back / back to root |
| `Ctrl +` / `Ctrl −` / `Ctrl 0` | Zoom |

## CLI

```
x-cast toggle | show | hide
x-cast run app:firefox
x-cast call system.info
x-cast host        # run in the foreground to see logs
x-cast doctor
```

## Develop

```sh
node --test tests/*.test.js   # unit tests for plugin/core
tests/smoke.sh                # live check against the running host (shows and hides the window, never types)
```

Behaviour comes from a static reverse-engineering pass over Raycast; see `SPEC.md` and `reference/`. No Raycast code is included.
