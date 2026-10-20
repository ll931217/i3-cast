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
    root.opened = true
    root.openedAt = Date.now()
    launcher.prepare(payload)
  }

  function close() {
    if (!root.opened) return
    root.opened = false
  }

  // ---------------------------------------------------------- our controls

  function show() {
    if (!root.opened) root.open("{}")
  }

  function hide() {
    root.close()
  }

  function openSettings() {
    root.hide()
    settingsWindow.shown = true
  }

  function toggle() {
    if (root.opened) root.hide()
    else root.show()
  }

  // Open a command directly (`x-cast run <id>`, later per-command
  // hotkeys). It counts as a launch for frecency, like Raycast's hotkeys.
  function present(result, owned) {
    if (!result.ok) {
      if (root.opened) launcher.showToast("failure", result.error, [{ title: "Copy Error", copy: result.error }])
      else launcher.hud(result.error)
      return
    }
    var outcome = result.data || {}
    if (outcome.prompt) {
      root.show()
      launcher.showPrompt(outcome, owned === true)
    } else if (outcome.push) {
      root.show()
      launcher.applyOutcome(outcome)
    } else if (root.opened) {
      launcher.applyOutcome(outcome)
    } else {
      if (outcome.settings) root.openSettings()
      if (outcome.hud) launcher.hud(outcome.hud)
      if (outcome.toast) launcher.hud(outcome.toast.title)
    }
  }

  function run(commandId) {
    var r = backend.callSync("rootSearch.performAction", { id: commandId })
    root.present(r, true)
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
    onSettingsRequested: root.openSettings()
    onOutcomeRequested: function(result) { root.present(result, true) }
  }

  SettingsWindow {
    id: settingsWindow
    backend: backend
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

    function settings(): string {
      root.openSettings()
      return "settings"
    }

    function search(text: string): string {
      root.open(JSON.stringify({ query: text }))
      return "shown"
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
      var result = backend.callSync(method, data)
      if (method === "rootSearch.openLink" || method === "rootSearch.performAction") root.present(result, false)
      return JSON.stringify(result)
    }
  }
}
