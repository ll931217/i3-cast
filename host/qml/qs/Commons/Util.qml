pragma Singleton
import QtQuick
import Quickshell

QtObject {
  function alpha(color, a) { return Qt.rgba(color.r, color.g, color.b, a) }

  function execArgv(argv) { Quickshell.execDetached(argv) }
  function execDetached(command) { Quickshell.execDetached(["sh", "-c", command]) }

  // A key press that edits a text field: printable text, or Backspace.
  function editsFilter(event, current) {
    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return false
    if (event.key === Qt.Key_Backspace) return true
    return event.text.length > 0 && event.text >= " " && event.text !== "\x7f"
  }

  function editedFilter(event, current) {
    if (event.key === Qt.Key_Backspace) return current.slice(0, -1)
    return current + event.text
  }
}
