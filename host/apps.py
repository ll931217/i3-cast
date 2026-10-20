"""Desktop entries, icons and window helpers that Omarchy's shell provides to a plugin."""
import configparser
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QPainterPath, QRegion, QWindow


def data_dirs():
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    system = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return [home] + [d for d in system if d]


def current_desktops():
    return [d for d in (os.environ.get("XDG_CURRENT_DESKTOP") or "").split(":") if d]


def read_entry(path, entry_id):
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
        section = parser["Desktop Entry"]
    except (configparser.Error, KeyError, OSError, UnicodeDecodeError):
        return None
    if section.get("Type") != "Application":
        return None
    if section.get("Hidden", "").lower() == "true" or section.get("NoDisplay", "").lower() == "true":
        return None
    only = [d for d in section.get("OnlyShowIn", "").split(";") if d]
    never = [d for d in section.get("NotShowIn", "").split(";") if d]
    here = current_desktops()
    if only and not set(only) & set(here):
        return None
    if set(never) & set(here):
        return None
    return {
        "id": entry_id,
        "name": section.get("Name", entry_id),
        "genericName": section.get("GenericName", ""),
        "keywords": [k for k in section.get("Keywords", "").split(";") if k],
        "icon": section.get("Icon", ""),
        "exec": section.get("Exec", ""),
        "terminal": section.get("Terminal", "").lower() == "true",
        "noDisplay": False,
    }


def scan():
    found = {}
    for base in data_dirs():
        root = Path(base) / "applications"
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            entry_id = "-".join(path.relative_to(root).with_suffix("").parts)
            if entry_id in found:
                continue
            found[entry_id] = read_entry(path, entry_id)
    return [e for e in found.values() if e]


class AppLibrary(QObject):
    """Same surface as Omarchy's shell.appLibrary: sortedEntries, launch, iconSource, appsChanged."""
    appsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = scan()
        self._watcher = QFileSystemWatcher(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._rescan)
        self._watcher.directoryChanged.connect(lambda _p: self._debounce.start())
        self._watcher.addPaths([str(Path(b) / "applications") for b in data_dirs()
                                if (Path(b) / "applications").is_dir()])

    def _rescan(self):
        self._entries = scan()
        self.appsChanged.emit()

    @Slot(str, result="QVariant")
    def sortedEntries(self, _query):
        return [{"entry": e} for e in sorted(self._entries, key=lambda e: e["name"].lower())]

    @Slot(str, result=str)
    def iconSource(self, name):
        return icons.resolve(name)

    @Slot(str, str)
    def launch(self, entry_id, _title):
        entry = next((e for e in self._entries if e["id"] == entry_id), None)
        if entry and entry["terminal"]:
            cmd = ["x-terminal-emulator", "-e", "sh", "-c", strip_field_codes(entry["exec"])]
        elif shutil.which("gtk-launch"):
            cmd = ["gtk-launch", entry_id + ".desktop"]
        else:
            cmd = shlex.split(strip_field_codes(entry["exec"])) if entry else None
        if cmd:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)


def strip_field_codes(command):
    out = []
    for token in shlex.split(command):
        if len(token) == 2 and token[0] == "%" and token[1] in "fFuUdDnNickvm":
            continue
        out.append(shlex.quote(token))
    return " ".join(out)


class IconIndex:
    """name -> best file, built once from the icon themes.

    A Python QQuickImageProvider deadlocks: Qt loads images on its own thread
    while the main thread holds the GIL waiting on it. Plain file URLs avoid it.
    """

    WANTED = 48

    def __init__(self):
        self._best = {}
        self._built = False

    @staticmethod
    def _size_of(path_parts):
        for part in path_parts:
            head, _, tail = part.partition("x")
            if head.isdigit() and tail.isdigit():
                return int(head)
        return None

    def _build(self):
        self._built = True
        roots = [str(Path.home() / ".local/share/icons"), str(Path.home() / ".icons")]
        roots += [os.path.join(d, "icons") for d in data_dirs()]
        themes = [t for t in (QIcon.themeName(), "hicolor", "Adwaita", "Humanity") if t]
        best = {}
        for rank, theme in enumerate(dict.fromkeys(themes)):
            for root in roots:
                base = os.path.join(root, theme)
                for dirpath, _dirs, files in os.walk(base):
                    parts = os.path.relpath(dirpath, base).split(os.sep)
                    if "symbolic" in parts or "cursors" in parts:
                        continue
                    size = self._size_of(parts)
                    scalable = "scalable" in parts
                    for f in files:
                        stem, ext = os.path.splitext(f)
                        if ext not in (".png", ".svg"):
                            continue
                        distance = 0 if scalable else abs((size or 0) - self.WANTED)
                        key = (rank, distance, 0 if "apps" in parts else 1)
                        if stem not in best or key < best[stem][0]:
                            best[stem] = (key, os.path.join(dirpath, f))
        for pixmaps in [os.path.join(d, "pixmaps") for d in data_dirs()]:
            if os.path.isdir(pixmaps):
                for f in os.listdir(pixmaps):
                    stem, ext = os.path.splitext(f)
                    if ext in (".png", ".svg", ".xpm") and stem not in best:
                        best[stem] = ((99, 0, 0), os.path.join(pixmaps, f))
        self._best = {k: v[1] for k, v in best.items()}

    def resolve(self, name):
        if not name:
            return ""
        if name.startswith("/"):
            return "file://" + name if os.path.exists(name) else ""
        if not self._built:
            self._build()
        path = self._best.get(name) or self._best.get("application-x-executable")
        return "file://" + path if path else ""


icons = IconIndex()


def init_icon_theme():
    ini = Path.home() / ".config/gtk-3.0/settings.ini"
    theme = None
    if ini.exists():
        parser = configparser.RawConfigParser(strict=False)
        parser.read(ini)
        theme = parser.get("Settings", "gtk-icon-theme-name", fallback=None)
    QIcon.setThemeName(theme or "Adwaita")


class HostShell(QObject):
    """What Launcher.qml expects as `shell`: an app library and summon/hide that decline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library = AppLibrary(self)

    @Property(QObject, constant=True)
    def appLibrary(self): return self._library

    @Slot(str, str, result=bool)
    def summon(self, _plugin_id, _payload): return False

    @Slot(str, result=bool)
    def hide(self, _plugin_id): return False


class Host(QObject):
    """Window placement and shaping that Wayland layer-shell does for free."""

    @Slot(result="QVariant")
    def activeScreenRect(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = screen.geometry()
        return {"x": g.x(), "y": g.y(), "width": g.width(), "height": g.height()}

    @Slot(QObject, int, int, int, int, int)
    def maskWindow(self, window, x, y, width, height, radius):
        if not isinstance(window, QWindow):
            return
        path = QPainterPath()
        path.addRoundedRect(x, y, width, height, radius, radius)
        window.setMask(QRegion(path.toFillPolygon().toPolygon()))
