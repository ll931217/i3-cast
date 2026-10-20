#!/usr/bin/env python3
"""x-cast host for X11 window managers (i3): runs plugin/Launcher.qml under plain Qt."""
import json
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtQml import QJSValue, qmlRegisterSingletonInstance
from PySide6.QtQuick import QQuickView

import apps
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
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    apps.init_icon_theme()
    apps.icons.warm()
    qsshim.register()
    registry = IpcRegistry()
    user = userconfig.HostConfig()
    shell = apps.HostShell()
    qmlRegisterSingletonInstance(IpcRegistry, "OmaHost", 1, 0, "IpcRegistry", registry)
    qmlRegisterSingletonInstance(userconfig.HostConfig, "OmaHost", 1, 0, "HostConfig", user)
    qmlRegisterSingletonInstance(apps.HostShell, "OmaHost", 1, 0, "HostShell", shell)
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
