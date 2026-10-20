import QtQuick
import Quickshell
import qs.Commons
import "ui"

// x-cast: a Raycast-style launcher for X11 window managers (i3).
//
// The host (host/main.py) loads this once and keeps it alive. `x-cast toggle`
// reaches toggle()/show()/hide() through the host's control socket, which
// dispatches to the ShellIpc object at the bottom of this file.
Item {
  id: root

  // Injected by the host: the desktop-entry app library.
  property var shell: null

  property bool opened: false
  property double openedAt: 0

  // ------------------------------------------------------- window lifecycle

  function open(payloadJson) {
    var payload = ({})
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) { payload = ({}) }
    var wasOpen = root.opened
    root.opened = true
    root.openedAt = Date.now()
    launcher.prepare(payload)
    if (!wasOpen) backend.emit("window.visibilityChanged", { visible: true })
  }

  function close() {
    if (!root.opened) return
    root.opened = false
    backend.emit("window.visibilityChanged", { visible: false })
  }

  // ---------------------------------------------------------- our controls

  function show() {
    if (!root.opened) root.open("{}")
  }

  function hide() {
    root.close()
  }

  function toggle() {
    if (root.opened) root.hide()
    else root.show()
  }

  // Open a command directly (`x-cast run <id>`, later per-command
  // hotkeys). It counts as a launch for frecency, like Raycast's hotkeys.
  function run(commandId) {
    var r = backend.callSync("rootSearch.performAction", { id: commandId, action: "open", query: "" })
    if (!r.ok) return r
    var outcome = r.data || {}
    if (outcome.push) {
      root.show()
      launcher.popToRoot()
      launcher.push(outcome.push)
    } else if (outcome.close) {
      root.hide()
      if (outcome.hud) launcher.hud(outcome.hud)
    }
    return r
  }

  Backend {
    id: backend
    appLibrary: root.shell ? root.shell.appLibrary : null
  }

  LauncherWindow {
    id: launcher
    shown: root.opened
    backend: backend
    appLibrary: backend.appLibrary
    onDismissRequested: root.hide()
  }

  ShellIpc {
    target: "x-cast"

    function toggle(): string {
      root.toggle()
      return root.opened ? "shown" : "hidden"
    }

    function show(): string {
      root.show()
      return "shown"
    }

    function hide(): string {
      root.hide()
      return "hidden"
    }

    function isOpen(): string {
      return root.opened ? "true" : "false"
    }

    function ping(): string {
      return "ok"
    }

    // Ids as rootSearch.search reports them: app:<desktop-id>.
    function run(commandId: string): string {
      return JSON.stringify(root.run(commandId))
    }

    // Dispatch any backend method: x-cast call system.healthPing '{}'.
    function call(method: string, dataJson: string): string {
      var data = null
      if (dataJson && dataJson.length > 0) {
        try { data = JSON.parse(dataJson) } catch (e) {
          return JSON.stringify({ ok: false, error: "data is not JSON: " + e })
        }
      }
      return JSON.stringify(backend.callSync(method, data))
    }
  }
}
