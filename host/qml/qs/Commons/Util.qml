pragma Singleton
import QtQuick
import Quickshell

QtObject {
  function alpha(color, a) { return Qt.rgba(color.r, color.g, color.b, a) }

  function execArgv(argv) { Quickshell.execDetached(argv) }
  function execDetached(command) { Quickshell.execDetached(["sh", "-c", command]) }

  // Readline-style edits: Ctrl+U clears, Ctrl+W deletes the last word.
  function isLineEdit(event) {
    return (event.modifiers & Qt.ControlModifier) && !(event.modifiers & (Qt.AltModifier | Qt.MetaModifier))
      && (event.key === Qt.Key_U || event.key === Qt.Key_W)
  }

  // A key press that edits a text field: printable text, Backspace, or a readline edit.
  function editsFilter(event, current) {
    if (isLineEdit(event)) return true
    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return false
    if (event.key === Qt.Key_Backspace) return true
    return event.text.length > 0 && event.text >= " " && event.text !== "\x7f"
  }

  function editedFilter(event, current) {
    if (isLineEdit(event)) return event.key === Qt.Key_U ? "" : current.replace(/\s*\S*\s*$/, "")
    if (event.key === Qt.Key_Backspace) return current.slice(0, -1)
    return current + event.text
  }
}
