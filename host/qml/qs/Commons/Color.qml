pragma Singleton
import QtQuick
import OmaHost

// Colors come from ~/.config/x-cast/theme.yaml `colors`; a missing or malformed value keeps its default.
QtObject {
  readonly property var colors: HostConfig.theme.colors || ({})

  function pick(key, fallback) {
    var v = colors[key]
    return typeof v === "string" && /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(v) ? v : fallback
  }

  readonly property QtObject menu: QtObject {
    readonly property color background: pick("background", "#1a1b26")
    readonly property color text: pick("text", "#c0caf5")
    readonly property color selectedText: pick("selectedText", "#7aa2f7")
    readonly property color selectedBackground: pick("selectedBackground", "#2a2e45")
    readonly property color border: pick("border", "#3b4261")
    readonly property color error: pick("error", "#e06c75")
  }
}
