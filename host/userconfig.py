"""~/.config/x-cast/config.yaml and theme.yaml, parsed once and re-sent to QML on every save."""
import os
import re
import sys
from pathlib import Path

import yaml
from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QTimer, Signal

CONFIG_EXAMPLE = """\
# x-cast options. Every key is optional; delete a line to get its default back.
# Saved changes apply live.

log_level: info                   # trace | debug | info | warning | error | fatal
keep_visible_on_focus_loss: false # keep the window open when it loses focus (for debugging)

general:
  window_mode: expanded           # expanded | compact (compact shows only the search box until you type)
  window_presentation_mode: mouse-screen  # mouse-screen | active-screen | primary-screen
  pop_to_root_timeout: 90         # seconds before a hidden launcher returns to the root view; 0 = always
  escape_key_behavior: pop-back-or-close  # pop-back-or-close | close-and-pop-to-root
  root_search_sensitivity: medium # low | medium | high
  ui_zoom: 1                      # scales the whole window

# "Use <query> with..." rows. {query} is replaced by the URL-encoded search text.
# Leave commented out to keep Google and DuckDuckGo.
# fallbacks:
#   - title: Search Google
#     url: https://www.google.com/search?q={query}
#   - title: Search Kagi
#     url: https://kagi.com/search?q={query}
"""

THEME_EXAMPLE = """\
# x-cast theme. Every key is optional; delete a line to get its default back.
# Colors are #rgb, #rrggbb or #aarrggbb. Saved changes apply live.

colors:
  background: "#1a1b26"
  text: "#c0caf5"
  selected_text: "#7aa2f7"        # accent: search icon, caret, selection text
  selected_background: "#2a2e45"
  border: "#3b4261"
  error: "#e06c75"

font:
  family: Sans
  icon_family: JetBrainsMono Nerd Font   # any Nerd Font; draws the icons
  caption: 12
  body_small: 13
  body: 14
  title: 16
  heading: 20

corner_radius: 8
gap: 10                           # minimum space between the card and the window edge
"""


def config_dir():
    override = os.environ.get("X_CAST_CONFIG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME")
    base = base if base and base.startswith("/") else str(Path.home() / ".config")
    return Path(base) / "x-cast"


def camelize(value):
    if isinstance(value, dict):
        return {re.sub(r"_([a-z0-9])", lambda m: m.group(1).upper(), str(k)): camelize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [camelize(v) for v in value]
    return value


def load(path, previous):
    """Parsed mapping, {} when the file is absent or empty, `previous` when it is unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        print("x-cast: cannot read %s: %s" % (path, e), file=sys.stderr)
        return previous
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print("x-cast: ignoring %s, it is not valid YAML: %s" % (path, e), file=sys.stderr)
        return previous
    if data is None:
        return {}
    if not isinstance(data, dict):
        print("x-cast: ignoring %s, the top level must be a mapping" % path, file=sys.stderr)
        return previous
    return camelize(data)


def write_examples(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (("config.yaml", CONFIG_EXAMPLE), ("theme.yaml", THEME_EXAMPLE)):
        target = directory / name
        if not target.exists():
            target.write_text(text, encoding="utf-8")


class HostConfig(QObject):
    configChanged = Signal()
    themeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir = config_dir()
        write_examples(self._dir)
        self._config = load(self._dir / "config.yaml", {})
        self._theme = load(self._dir / "theme.yaml", {})
        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._reload)
        self._watcher.fileChanged.connect(lambda _p: self._debounce.start())
        self._watcher.directoryChanged.connect(lambda _p: self._debounce.start())
        self._rewatch()

    def _rewatch(self):
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        self._watcher.addPath(str(self._dir))
        for name in ("config.yaml", "theme.yaml"):
            if (self._dir / name).exists():
                self._watcher.addPath(str(self._dir / name))

    def _reload(self):
        config = load(self._dir / "config.yaml", self._config)
        theme = load(self._dir / "theme.yaml", self._theme)
        if config != self._config:
            self._config = config
            self.configChanged.emit()
        if theme != self._theme:
            self._theme = theme
            self.themeChanged.emit()
        self._rewatch()

    config = Property("QVariantMap", lambda s: s._config, notify=configChanged)
    theme = Property("QVariantMap", lambda s: s._theme, notify=themeChanged)
