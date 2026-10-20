pragma Singleton
import QtQuick

// Stand-in for omarchy-shell's Commons/Style.qml: unit scale 1, fixed sizes. [I]
QtObject {
  readonly property int cornerRadius: 8
  readonly property int gapsOut: 10
  function space(n) { return n }
  readonly property QtObject spacing: QtObject { readonly property int hairline: 1 }
  readonly property QtObject font: QtObject {
    readonly property string menuFamily: "Sans"
    readonly property int caption: 12
    readonly property int bodySmall: 13
    readonly property int body: 14
    readonly property int title: 16
    readonly property int heading: 20
  }
}
