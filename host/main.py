#!/usr/bin/env python3
"""x-cast host for X11 window managers (i3): runs plugin/Launcher.qml under plain Qt."""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtQml import QJSValue, qmlRegisterSingletonInstance
from PySide6.QtQuick import QQuickView

import apps
import plugins
import qsshim
import userconfig

HERE = Path(__file__).resolve().parent


class IpcRegistry(QObject):
    """ShellIpc targets declared in QML, reached over the control socket."""

    def __init__(self):
        super().__init__()
        self._targets = {}
        self.engine = None

    @Slot(str, QJSValue)
    def register(self, target, dispatch):
        self._targets[target] = dispatch

    def call(self, target, fn, args):
        dispatch = self._targets.get(target)
        if dispatch is None:
            return "unknown target " + target
        result = dispatch.call([self.engine.toScriptValue(fn), self.engine.toScriptValue(args)])
        return result.toString()


def serve(registry, path):
    server = QLocalServer()
    QLocalServer.removeServer(path)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(path):
        sys.exit("x-cast: cannot listen on %s: %s" % (path, server.errorString()))

    def on_connection():
        conn = server.nextPendingConnection()

        def on_ready():
            if not conn.canReadLine():
                return
            line = bytes(conn.readLine()).decode("utf-8", "replace").strip()
            fn, _, rest = line.partition(" ")
            # Typed ShellIpc parameters turn a missing argument into the string "undefined", so pad.
            args = (rest.split(" ", 1) + [""])[:2] if fn == "call" else ([rest] if rest else [])
            conn.write((registry.call("x-cast", fn, args) + "\n").encode())
            conn.disconnectFromServer()

        conn.readyRead.connect(on_ready)

    server.newConnection.connect(on_connection)
    return server


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("x-cast")
    app.setDesktopFileName("x-cast")
    # Quit through Qt so the backend's onDestruction flushes settings.json and frecency.json.
    # A timer lets the Python-level handler run while Qt owns the main thread.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    tick = QTimer()
    tick.start(250)
    tick.timeout.connect(lambda: None)

    apps.init_icon_theme()
    apps.icons.warm()
    qsshim.register()
    registry = IpcRegistry()
    user = userconfig.HostConfig()
    shell = apps.HostShell()
    qmlRegisterSingletonInstance(IpcRegistry, "OmaHost", 1, 0, "IpcRegistry", registry)
    qmlRegisterSingletonInstance(userconfig.HostConfig, "OmaHost", 1, 0, "HostConfig", user)
    qmlRegisterSingletonInstance(apps.HostShell, "OmaHost", 1, 0, "HostShell", shell)
    extensions = plugins.PluginHost(userconfig.config_dir(), lambda: user.config)
    extensions.notice.connect(lambda style, text: subprocess.Popen(
        ["notify-send", "-a", "x-cast", "-u", "critical" if style == "failure" else "normal", text]))
    extensions.load_all(HERE / "plugins", bundled=True)
    extensions.load_all(extensions.plugin_dir)
    qmlRegisterSingletonInstance(plugins.PluginHost, "OmaHost", 1, 0, "PluginHost", extensions)
    host = apps.Host()
    qmlRegisterSingletonInstance(apps.Host, "OmaHost", 1, 0, "Host", host)

    view = QQuickView()
    registry.engine = view.engine()
    view.engine().addImportPath(str(HERE / "qml"))
    view.setSource(QUrl.fromLocalFile(str(HERE / "qml" / "main.qml")))
    if view.status() != QQuickView.Status.Ready:
        for e in view.errors():
            print(e.toString(), file=sys.stderr)
        sys.exit(1)

    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    server = serve(registry, os.path.join(runtime, "x-cast.sock"))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
