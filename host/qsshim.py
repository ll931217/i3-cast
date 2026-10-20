"""The slice of Quickshell's QML API that plugin/ uses, implemented on plain Qt for the X11 host."""
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import (Property, QFileSystemWatcher, QObject, QProcess, QTimer, Signal, Slot)
import apps
from PySide6.QtQml import qmlRegisterSingletonInstance, qmlRegisterType


class SplitParser(QObject):
    read = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffer = ""

    def feed(self, data):
        self._buffer += data
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            self.read.emit(line)

    def flush(self):
        if self._buffer:
            line, self._buffer = self._buffer, ""
            self.read.emit(line)


class Process(QObject):
    commandChanged = Signal()
    runningChanged = Signal()
    stdoutChanged = Signal()
    exited = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._command = []
        self._running = False
        self._stdout = None
        self._proc = None

    def _get_command(self): return self._command
    def _set_command(self, value):
        self._command = [str(v) for v in (value or [])]
        self.commandChanged.emit()
    command = Property(list, _get_command, _set_command, notify=commandChanged)

    def _get_stdout(self): return self._stdout
    def _set_stdout(self, value):
        self._stdout = value
        self.stdoutChanged.emit()
    stdout = Property(QObject, _get_stdout, _set_stdout, notify=stdoutChanged)

    def _get_running(self): return self._running
    def _set_running(self, value):
        if bool(value) == self._running:
            return
        if value:
            self._start()
        elif self._proc:
            self._proc.kill()
    running = Property(bool, _get_running, _set_running, notify=runningChanged)

    def _start(self):
        if not self._command:
            return
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(lambda err: self._on_finished(127, QProcess.ExitStatus.CrashExit)
                                   if err == QProcess.ProcessError.FailedToStart else None)
        self._proc = proc
        self._running = True
        self.runningChanged.emit()
        proc.start(self._command[0], self._command[1:])

    def _on_stdout(self):
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        if self._stdout is not None:
            self._stdout.feed(data)

    def _on_finished(self, code, status):
        if not self._running:
            return
        if self._stdout is not None:
            self._on_stdout()
            self._stdout.flush()
        self._running = False
        self.runningChanged.emit()
        self.exited.emit(int(code), 0 if status == QProcess.ExitStatus.NormalExit else 1)


class FileViewError(QObject):
    FILE_NOT_FOUND, OPEN_FAILED, WRITE_FAILED = 1, 2, 3
    _names = {1: "file not found", 2: "could not open", 3: "could not write"}

    @Property(int, constant=True)
    def FileNotFound(self): return self.FILE_NOT_FOUND

    @Slot(int, result=str)
    def toString(self, error): return self._names.get(error, "error %d" % error)


class FileView(QObject):
    pathChanged = Signal()
    watchChangesChanged = Signal()
    atomicWritesChanged = Signal()
    printErrorsChanged = Signal()
    loaded = Signal()
    loadFailed = Signal(int)
    saveFailed = Signal(int)
    fileChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self._text = ""
        self._watch = False
        self._atomic = False
        self._print_errors = True
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_watch)
        self._watcher.directoryChanged.connect(self._on_watch)

    def _get_path(self): return self._path
    def _set_path(self, value):
        value = str(value or "")
        if value == self._path:
            return
        self._path = value
        self.pathChanged.emit()
        self._rewatch()
        if value:
            QTimer.singleShot(0, self.reload)
    path = Property(str, _get_path, _set_path, notify=pathChanged)

    def _get_watch(self): return self._watch
    def _set_watch(self, value):
        self._watch = bool(value)
        self.watchChangesChanged.emit()
        self._rewatch()
    watchChanges = Property(bool, _get_watch, _set_watch, notify=watchChangesChanged)

    def _get_atomic(self): return self._atomic
    def _set_atomic(self, value):
        self._atomic = bool(value)
        self.atomicWritesChanged.emit()
    atomicWrites = Property(bool, _get_atomic, _set_atomic, notify=atomicWritesChanged)

    def _get_print(self): return self._print_errors
    def _set_print(self, value):
        self._print_errors = bool(value)
        self.printErrorsChanged.emit()
    printErrors = Property(bool, _get_print, _set_print, notify=printErrorsChanged)

    def _rewatch(self):
        old = self._watcher.files() + self._watcher.directories()
        if old:
            self._watcher.removePaths(old)
        if self._watch and self._path:
            parent = str(Path(self._path).parent)
            if os.path.isdir(parent):
                self._watcher.addPath(parent)
            if os.path.exists(self._path):
                self._watcher.addPath(self._path)

    def _on_watch(self, _changed):
        self._rewatch()
        self.fileChanged.emit()

    @Slot()
    def reload(self):
        if not self._path:
            return
        try:
            self._text = Path(self._path).read_text(encoding="utf-8")
        except FileNotFoundError:
            self.loadFailed.emit(FileViewError.FILE_NOT_FOUND)
            return
        except OSError:
            self.loadFailed.emit(FileViewError.OPEN_FAILED)
            return
        self.loaded.emit()

    @Slot(result=str)
    def text(self): return self._text

    @Slot(str)
    def setText(self, text):
        try:
            target = Path(self._path)
            if self._atomic:
                tmp = target.with_name(target.name + ".tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, target)
            else:
                target.write_text(text, encoding="utf-8")
            self._text = text
        except OSError:
            self.saveFailed.emit(FileViewError.WRITE_FAILED)


class Quickshell(QObject):
    @Slot(str, result="QVariant")
    def env(self, name): return os.environ.get(name, "")

    @Slot(list)
    def execDetached(self, command):
        subprocess.Popen([str(c) for c in command], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot(str, str, result=str)
    def iconPath(self, name, fallback=""):
        return apps.icons.resolve(name or fallback)


class DesktopEntryList(QObject):
    valuesChanged = Signal()

    @Property(list, constant=True)
    def values(self): return []


class DesktopEntries(QObject):
    applicationsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._applications = DesktopEntryList(self)

    @Property(QObject, constant=True)
    def applications(self): return self._applications


_singletons = []


def register():
    quickshell, entries, errors = Quickshell(), DesktopEntries(), FileViewError()
    _singletons.extend([quickshell, entries, errors])
    qmlRegisterSingletonInstance(Quickshell, "Quickshell", 1, 0, "Quickshell", quickshell)
    qmlRegisterSingletonInstance(DesktopEntries, "Quickshell", 1, 0, "DesktopEntries", entries)
    qmlRegisterType(SplitParser, "Quickshell.Io", 1, 0, "SplitParser")
    qmlRegisterType(Process, "Quickshell.Io", 1, 0, "Process")
    qmlRegisterType(FileView, "Quickshell.Io", 1, 0, "FileView")
    qmlRegisterSingletonInstance(FileViewError, "Quickshell.Io", 1, 0, "FileViewError", errors)
