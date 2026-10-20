import QtQuick

// A row follows the pointer only after it really moved, not when the list scrolls under it.
QtObject {
  property Item referenceItem: null
  property point last: Qt.point(-1, -1)
  property bool armed: false

  function reset() { armed = false; last = Qt.point(-1, -1) }

  function moved(item, mouse) {
    var p = item.mapToItem(referenceItem, mouse.x, mouse.y)
    if (!armed) { armed = true; last = Qt.point(p.x, p.y); return false }
    if (p.x === last.x && p.y === last.y) return false
    last = Qt.point(p.x, p.y)
    return true
  }
}
