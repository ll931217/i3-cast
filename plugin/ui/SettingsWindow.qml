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

  readonly property string docsUrl: "https://github.com/ll931217/i3-cast/blob/main/docs/plugins.md"
  property bool adding: false
  property string pluginNote: ""
  property bool pluginNoteOk: false
  property string confirmRemove: ""
  property int pluginsRevision: 0

  Connections {
    target: PluginHost
    function onChanged() { win.pluginsRevision++ }
    function onInstalled(json) {
      var r = JSON.parse(json)
      win.adding = false
      win.pluginNoteOk = r.ok
      win.pluginNote = r.ok ? "Added " + r.name + "." : r.error
      if (r.ok) addInput.text = ""
    }
  }

  // The Plugins page: x-cast's own providers, then every plugin file.
  readonly property var pluginRows: {
    win.pluginsRevision
    win.providers
    var counts = ({})
    win.providers.forEach(function(p) { counts[p.id] = p.commands })
    var hosted = JSON.parse(PluginHost.plugins())
    var hostedIds = ({})
    var rows = []
    hosted.forEach(function(p) {
      p.providers.forEach(function(q) { hostedIds[q.id] = true })
      rows.push({
        name: p.name, title: p.name + ".py", kind: p.bundled ? "ships with x-cast" : "added by you",
        removable: !p.bundled, error: p.error || "",
        providers: p.providers.map(function(q) {
          return { id: q.id, enabled: q.enabled, locked: q.locked, toggleable: true,
                   detail: q.enabled ? win.commandCount(counts[q.id]) : "off" }
        })
      })
    })
    var builtIn = win.providers.filter(function(p) { return !hostedIds[p.id] })
    if (builtIn.length) rows.unshift({
      name: "", title: "Built in", kind: "", removable: false, error: "",
      providers: builtIn.map(function(p) { return { id: p.id, enabled: true, locked: false, toggleable: false, detail: win.commandCount(p.commands) } })
    })
    return rows
  }

  function commandCount(n) {
    return n === 0 || n === undefined ? "rows appear as you type" : n === 1 ? "1 command" : n + " commands"
  }

  function addPlugin(source) {
    win.pluginNote = ""
    win.adding = true
    PluginHost.install(source)
  }

  function removePlugin(name) {
    if (win.confirmRemove !== name) { win.confirmRemove = name; return }
    win.confirmRemove = ""
    var r = JSON.parse(PluginHost.remove(name))
    win.pluginNoteOk = r.ok
    win.pluginNote = r.ok ? "Removed " + name + "." : r.error
  }

  function togglePlugin(id, enabled) {
    var r = JSON.parse(PluginHost.setEnabled(id, enabled))
    if (!r.ok) { win.pluginNoteOk = false; win.pluginNote = r.error }
  }

  function label(value) { return String(value).replace(/-/g, " ") }
  function overridden(key) { return win.backend.config.general[key] !== undefined }

  Item {
    id: keys
    anchors.fill: parent
    focus: true
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape || ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_W)) { win.shown = false; event.accepted = true }
      else if (addInput.activeFocus) return
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

    // ? opens the plugin guide on GitHub.
    Rectangle {
      visible: win.page === 2
      anchors.left: heading.right
      anchors.leftMargin: 10
      anchors.verticalCenter: heading.verticalCenter
      width: 24
      height: 24
      radius: 12
      color: Util.alpha(win.fg, 0.1)
      Text {
        anchors.centerIn: parent
        textFormat: Text.PlainText
        text: "?"
        color: win.fg
        font.family: Style.font.menuFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: win.backend.callSync("system.openUrl", { url: win.docsUrl })
      }
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
    Item {
      id: pluginsPage
      anchors.top: heading.bottom
      anchors.topMargin: 24
      anchors.bottom: parent.bottom
      anchors.left: parent.left
      anchors.right: parent.right
      visible: win.page === 2

      // Add: a path or link to a .py file.
      Row {
        id: addRow
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 8

        Rectangle {
          width: parent.width - addButton.width - parent.spacing
          height: 32
          radius: 6
          color: Util.alpha(win.fg, 0.08)
          border.width: addInput.activeFocus ? 1 : 0
          border.color: win.accent

          TextInput {
            id: addInput
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            color: win.fg
            selectionColor: win.accent
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
            onAccepted: win.addPlugin(addInput.text)
            Keys.onEscapePressed: win.shown = false
          }
          Text {
            anchors.fill: addInput
            verticalAlignment: Text.AlignVCenter
            visible: addInput.text.length === 0
            textFormat: Text.PlainText
            text: "Path or https:// link to a plugin .py file"
            color: win.fg
            opacity: 0.4
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
          }
        }
        Rectangle {
          id: addButton
          width: 110
          height: 32
          radius: 6
          color: win.adding ? Util.alpha(win.fg, 0.08) : Util.alpha(win.accent, 0.3)
          Text {
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: win.adding ? "Adding…" : "Add plugin"
            color: win.fg
            font.family: Style.font.menuFamily
            font.pixelSize: Style.font.body
          }
          MouseArea { anchors.fill: parent; enabled: !win.adding; cursorShape: Qt.PointingHandCursor; onClicked: win.addPlugin(addInput.text) }
        }
      }

      Text {
        id: addNote
        anchors.top: addRow.bottom
        anchors.topMargin: 6
        anchors.left: parent.left
        anchors.right: parent.right
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: win.pluginNote || "A plugin is a Python file that runs with your permissions. Only add ones you trust."
        color: win.pluginNote && !win.pluginNoteOk ? Commons.Color.menu.error : win.fg
        opacity: win.pluginNote ? 1 : 0.55
        font.family: Style.font.menuFamily
        font.pixelSize: Style.font.bodySmall
      }

      ListView {
        anchors.top: addNote.bottom
        anchors.topMargin: 14
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        clip: true
        spacing: 10
        boundsBehavior: Flickable.StopAtBounds
        model: win.pluginRows

        delegate: Rectangle {
          required property var modelData
          width: ListView.view.width
          height: body.implicitHeight + 20
          radius: 8
          color: Util.alpha(win.fg, 0.05)

          Column {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 10
            spacing: 6

            Item {
              width: parent.width
              height: 26
              Text {
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: modelData.title + (modelData.kind ? "   " + modelData.kind : "")
                color: win.fg
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              Rectangle {
                visible: modelData.removable
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 80
                height: 24
                radius: 6
                color: win.confirmRemove === modelData.name ? Util.alpha(Commons.Color.menu.error, 0.4) : Util.alpha(win.fg, 0.08)
                Text {
                  anchors.centerIn: parent
                  textFormat: Text.PlainText
                  text: win.confirmRemove === modelData.name ? "Sure?" : "Remove"
                  color: win.fg
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.bodySmall
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.removePlugin(modelData.name) }
              }
            }

            Text {
              visible: modelData.error.length > 0
              width: parent.width
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              text: "Could not load: " + modelData.error
              color: Commons.Color.menu.error
              font.family: Style.font.menuFamily
              font.pixelSize: Style.font.bodySmall
            }

            Repeater {
              model: modelData.providers
              delegate: Item {
                required property var modelData
                width: body.width
                height: 28
                Text {
                  anchors.left: parent.left
                  anchors.right: toggle.left
                  anchors.rightMargin: 8
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  text: modelData.id + "   " + modelData.detail
                  color: win.fg
                  opacity: modelData.enabled ? 1 : 0.45
                  font.family: Style.font.menuFamily
                  font.pixelSize: Style.font.body
                }
                Rectangle {
                  id: toggle
                  visible: modelData.toggleable
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  width: modelData.locked ? 150 : 80
                  height: 24
                  radius: 6
                  opacity: modelData.locked ? 0.5 : 1
                  color: modelData.enabled ? Util.alpha(win.accent, 0.25) : Util.alpha(win.fg, 0.08)
                  Text {
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: modelData.locked ? "Off (config.yaml)" : (modelData.enabled ? "Enabled" : "Disabled")
                    color: win.fg
                    font.family: Style.font.menuFamily
                    font.pixelSize: Style.font.bodySmall
                  }
                  MouseArea {
                    anchors.fill: parent
                    enabled: !modelData.locked
                    cursorShape: Qt.PointingHandCursor
                    onClicked: win.togglePlugin(modelData.id, !modelData.enabled)
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
