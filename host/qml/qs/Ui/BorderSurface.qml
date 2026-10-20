import QtQuick

Rectangle {
  id: surface
  property var borderSpec: null
  readonly property bool isBorderSurface: true
  readonly property int borderTop: borderSpec ? borderSpec.width : 0
  readonly property int borderBottom: borderTop
  readonly property int borderLeft: borderTop
  readonly property int borderRight: borderTop
  border.width: borderTop
  border.color: borderSpec ? borderSpec.color : "transparent"
}
