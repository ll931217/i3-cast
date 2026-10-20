import QtQuick
import QtQuick.Window
import OmaHost
import qs.Commons
import qs.Commons as Commons
import "../core/Schema.js" as Schema

// Settings window: General (generated from Schema.generalFields), Commands (re-enable,
// see aliases) and Plugins. A normal dialog, so i3 floats it. Click a value to step
// through its options, right-click to step back.
Window {
  id: win

  required property var backend
  property bool shown: false

  title: "x-cast Settings"
  flags: Qt.Dialog
  transientParent: null
  width: 760
  height: 520
  minimumWidth: 560
  minimumHeight: 360
  color: Commons.Color.menu.background
  visible: win.shown

  readonly property color fg: Commons.Color.menu.text
  readonly property color accent: Commons.Color.menu.selectedText
  readonly property var pages: ["General", "Commands", "Plugins"]
  property int page: 0
  property string note: ""

  readonly property var general: {
    win.backend.storeRevision
    var r = win.backend.ready ? win.backend.callSync("settings.getGeneralSettings", null) : null
    return r && r.ok ? r.data : ({})
  }
  readonly property var commands: {
    win.backend.storeRevision
    win.backend.candidatesRevision
    var r = win.backend.ready ? win.backend.callSync("settings.listCommands", null) : null
    return r && r.ok ? r.data : []
  }
  readonly property var providers: {
    win.backend.candidatesRevision
    var r = win.backend.ready ? win.backend.callSync("settings.listProviders", null) : null
    return r && r.ok ? r.data : []
  }

  onVisibleChanged: if (visible) { win.place(); win.requestActivate(); keys.forceActiveFocus() }
  onClosing: win.shown = false

  function place() {
    var s = Host.activeScreenRect("mouse-screen")
    win.x = s.x + Math.round((s.width - win.width) / 2)
    win.y = s.y + Math.round((s.height - win.height) / 2)
  }

  function setGeneral(key, value) {
    var patch = ({})
    patch[key] = value
    var r = win.backend.callSync("settings.updateGeneralSettings", patch)
    win.note = r.ok ? "" : r.error
  }

  function step(field, direction) {
    var options = field.options
    var at = options.indexOf(win.general[field.key])
    win.setGeneral(field.key, options[(at + direction + options.length) % options.length])
  }

  function setEnabled(id, enabled) {
    var r = win.backend.callSync("settings.updateCommandSettings", { commandId: id, enabled: enabled })
    win.note = r.ok ? "" : r.error
  }

  function label(value) { return String(value).replace(/-/g, " ") }
  function overridden(key) { return win.backend.config.general[key] !== undefined }

  Item {
    id: keys
    anchors.fill: parent
    focus: true
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape || ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_W)) { win.shown = false; event.accepted = true }
      else if (event.key === Qt.Key_Tab) { win.page = (win.page + 1) % win.pages.length; event.accepted = true }
      else if (event.key === Qt.Key_Backtab) { win.page = (win.page + win.pages.length - 1) % win.pages.length; event.accepted = true }
    }
  }

  Rectangle {
    id: sidebar
    width: 170
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    anchors.left: parent.left
    color: Util.alpha(win.fg, 0.05)

    Column {
      anchors.fill: parent
      anchors.margins: 10
      spacing: 4
      Repeater {
        model: win.pages
        delegate: Rectangle {
          required property string modelData
          required property int index
          width: parent.width
          height: 34
          radius: 6
          color: win.page === index ? Commons.Color.menu.selectedBackground : "transparent"
          Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 12
            textFormat: Text.PlainText
            text: modelData
            color: win.fg
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
          }
          MouseArea { anchors.fill: parent; onClicked: win.page = index }
        }
      }
    }
  }

  Item {
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    anchors.left: sidebar.right
    anchors.right: parent.right
    anchors.margins: 20

    Text {
      id: heading
      textFormat: Text.PlainText
      text: win.pages[win.page]
      color: win.fg
      font.family: Style.font.menuFamily
      font.pixelSize: Style.font.title
      font.bold: true
    }

    Text {
      id: noteText
      anchors.top: heading.bottom
      anchors.topMargin: 6
      textFormat: Text.PlainText
      visible: text.length > 0
      text: win.note
      color: Commons.Color.menu.error
      font.family: Style.font.menuFamily
      font.pixelSize: Style.font.bodySmall
    }

    // ------------------------------------------------------ General
    ListView {
      anchors.top: heading.bottom
      anchors.topMargin: 30
      anchors.bottom: parent.bottom
      anchors.left: parent.left
      anchors.right: parent.right
      visible: win.page === 0
      clip: true
      model: Schema.generalFields
      boundsBehavior: Flickable.StopAtBounds
      delegate: Item {
        required property var modelData
        readonly property bool locked: win.overridden(modelData.key)
        width: ListView.view.width
        height: 44

        Text {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: modelData.title + (parent.locked ? "  (set in config.yaml)" : "")
          color: win.fg
          opacity: parent.locked ? 0.5 : 1
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.body
        }
        Rectangle {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          width: 190
          height: 28
          radius: 6
          color: Util.alpha(win.fg, 0.08)
          opacity: parent.locked ? 0.4 : 1
          Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: win.label(win.general[modelData.key]) + "  ▾"
            color: win.fg
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
          }
          MouseArea {
            anchors.fill: parent
            enabled: !parent.parent.locked
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) { win.step(modelData, mouse.button === Qt.RightButton ? -1 : 1) }
          }
        }
      }
    }

    // ----------------------------------------------------- Commands
    ListView {
      anchors.top: heading.bottom
      anchors.topMargin: 30
      anchors.bottom: parent.bottom
      anchors.left: parent.left
      anchors.right: parent.right
      visible: win.page === 1
      clip: true
      model: win.commands
      boundsBehavior: Flickable.StopAtBounds
      delegate: Item {
        required property var modelData
        width: ListView.view.width
        height: 38
        Text {
          anchors.left: parent.left
          anchors.right: state.left
          anchors.rightMargin: 10
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          elide: Text.ElideRight
          text: modelData.title + (modelData.alias ? "   alias: " + modelData.alias : "") + "   " + modelData.typeLabel
          color: win.fg
          opacity: modelData.enabled ? 1 : 0.45
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.body
        }
        Rectangle {
          id: state
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          width: 80
          height: 26
          radius: 6
          color: modelData.enabled ? Util.alpha(win.accent, 0.25) : Util.alpha(win.fg, 0.08)
          Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: modelData.enabled ? "Enabled" : "Disabled"
            color: win.fg
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.bodySmall
          }
          MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.setEnabled(modelData.id, !modelData.enabled) }
        }
      }
    }

    // ------------------------------------------------------ Plugins
    Column {
      anchors.top: heading.bottom
      anchors.topMargin: 30
      anchors.left: parent.left
      anchors.right: parent.right
      visible: win.page === 2
      spacing: 10

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Add a plugin by putting a .py file in ~/.config/x-cast/plugins/. Script Commands read scripts from ~/.config/x-cast/script-commands."
        color: win.fg
        opacity: 0.6
        font.family: Style.font.menuFamily
        font.pixelSize: Style.font.bodySmall
      }
      Repeater {
        model: win.providers
        delegate: Text {
          required property var modelData
          width: parent.width
          textFormat: Text.PlainText
          text: modelData.id + "   " + modelData.commands + (modelData.commands === 1 ? " command" : " commands")
          color: win.fg
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.body
        }
      }
    }
  }
}
