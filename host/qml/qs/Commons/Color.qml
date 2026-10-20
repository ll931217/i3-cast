pragma Singleton
import QtQuick

// Fixed dark palette until the i3 host reads a theme. [D]
QtObject {
  readonly property QtObject menu: QtObject {
    readonly property color background: "#1a1b26"
    readonly property color text: "#c0caf5"
    readonly property color selectedText: "#7aa2f7"
    readonly property color selectedBackground: "#2a2e45"
    readonly property color border: "#3b4261"
  }
}
