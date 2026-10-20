import QtQuick
import QtQuick.Window
import OmaHost
import qs.Commons as Commons

// X11 stand-in for omarchy-shell's full-screen layer-shell overlay: a small
// frameless window, shaped to the card, centred on the screen under the pointer.
Window {
  id: overlay
  property bool shown: false
  readonly property real uiScale: overlay["zoom"] > 0 ? overlay["zoom"] : 1
  readonly property int pad: Commons.Style.gapsOut

  flags: Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
  transientParent: null
  color: Commons.Color.menu.background
  width: Math.round(750 * uiScale) + pad * 2
  height: Math.round(475 * uiScale) + pad * 2
  visible: false

  property Item surface: null

  function findSurface(item) {
    if (item.isBorderSurface) return item
    for (var i = 0; i < item.children.length; i++) {
      var found = findSurface(item.children[i])
      if (found) return found
    }
    return null
  }

  function applyMask() {
    if (!surface) return
    Host.maskWindow(overlay, surface.x, surface.y, surface.width, surface.height, surface.radius)
  }

  function place() {
    var s = Host.activeScreenRect()
    overlay.x = s.x + Math.round((s.width - overlay.width) / 2)
    overlay.y = s.y + Math.round(s.height * 0.2)
  }

  onShownChanged: {
    if (shown) {
      place()
      overlay.visible = true
      requestActivate()
    } else {
      overlay.visible = false
    }
  }

  onActiveChanged: {
    if (!active && shown && typeof overlay["dismissRequested"] === "function") overlay["dismissRequested"]()
  }

  Connections {
    target: overlay.surface
    ignoreUnknownSignals: true
    function onXChanged() { overlay.applyMask() }
    function onYChanged() { overlay.applyMask() }
    function onWidthChanged() { overlay.applyMask() }
    function onHeightChanged() { overlay.applyMask() }
  }

  onVisibleChanged: if (visible) {
    if (!surface) surface = findSurface(contentItem)
    applyMask()
  }
}
