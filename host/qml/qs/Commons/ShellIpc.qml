import QtQuick
import OmaHost

// Functions declared on an instance are reachable from the host's control socket.
QtObject {
  id: ipc
  property string target

  function dispatch(fn, args) {
    if (typeof ipc[fn] !== "function") return "unknown function " + fn
    return String(ipc[fn].apply(ipc, args))
  }

  Component.onCompleted: IpcRegistry.register(ipc.target, ipc.dispatch)
}
