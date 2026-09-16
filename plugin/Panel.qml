import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

Panel {
  id: root
  moduleName: "user.ai-models"
  ipcTarget: "user.ai-models"

  // Give the bar item an intrinsic size; without this the BarIconButton
  // (anchors.fill: parent) inherits a 0x0 root and the glyph never renders.
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  readonly property int refreshIntervalSec: {
    var n = parseInt(String(setting("refreshIntervalSec", 10)), 10)
    if (!isFinite(n) || n < 3) n = 10
    return n
  }

  property var models: []
  property bool loading: false
  property bool anyRunning: models.some(function(m) { return m.status === "running" })
  // id of the model whose start/stop is currently in flight, "" when idle
  property string busyId: ""
  property string lastError: ""

  function refresh() {
    if (listProc.running) return
    loading = true
    listProc.command = [Quickshell.env("HOME") + "/.local/bin/ai-models-ctl", "list"]
    listProc.running = true
  }

  function startModel(id) {
    if (busyId !== "") return
    busyId = id
    actionProc.command = [Quickshell.env("HOME") + "/.local/bin/ai-models-ctl", "start", id]
    actionProc.running = true
  }

  function stopModel(id) {
    if (busyId !== "") return
    busyId = id
    actionProc.command = [Quickshell.env("HOME") + "/.local/bin/ai-models-ctl", "stop", id]
    actionProc.running = true
  }

  Process {
    id: listProc
    running: false
    command: []
    stdout: StdioCollector {
      id: listStdout
      waitForEnd: true
      onStreamFinished: {
        root.loading = false
        try {
          var parsed = JSON.parse(text)
          root.models = parsed
          root.lastError = ""
        } catch (e) {
          root.lastError = "Parse error"
        }
      }
    }
    stderr: StdioCollector { id: listStderr; waitForEnd: true }
    onExited: function(exitCode) {
      root.loading = false
      if (exitCode !== 0 && root.models.length === 0) root.lastError = "ai-models-ctl not found"
    }
  }

  Process {
    id: actionProc
    running: false
    command: []
    onExited: function(exitCode) {
      root.busyId = ""
      root.refresh()
    }
  }

  Timer {
    interval: root.refreshIntervalSec * 1000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
  }

  onOpenedChanged: if (opened) refresh()

  Component.onCompleted: refresh()

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.anyRunning ? "󰚩" : "󰚥"
    active: root.anyRunning
    onPressed: function(buttonCode) { root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(520))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      ScrollView {
        id: scrollArea
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: panelColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

        Column {
          id: panelColumn
          width: scrollArea.availableWidth
          spacing: Style.space(10)

          Item {
            width: parent.width
            implicitHeight: heroLabel.implicitHeight + Style.space(6)

            Text {
              id: heroLabel
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: "AI Models"
              textFormat: Text.PlainText
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }

            Button {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              bordered: true
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              text: root.loading ? "…" : "↻ Refresh"
              onClicked: root.refresh()
            }
          }

          PanelSeparator { foreground: root.bar.foreground }

          Text {
            visible: root.lastError !== ""
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: root.lastError
            color: root.bar.urgent
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            visible: !root.loading && root.models.length === 0 && root.lastError === ""
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: "No local models found. Checked Ollama and ~/.cache/huggingface GGUFs."
            color: Qt.darker(root.bar.foreground, 1.4)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
          }

          Repeater {
            model: root.models

            Column {
              id: row
              required property var modelData
              width: panelColumn.width
              spacing: Style.space(2)

              Rectangle {
                width: parent.width
                implicitHeight: rowInner.implicitHeight + Style.space(16)
                radius: Style.cornerRadius
                color: modelData.status === "running"
                  ? Style.selectedFillFor(root.bar.foreground, Color.accent)
                  : "transparent"
                border.width: 1
                border.color: Qt.darker(root.bar.foreground, 2.2)

                Row {
                  id: rowInner
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: Style.space(10)
                  anchors.rightMargin: Style.space(8)
                  spacing: Style.space(8)

                  Rectangle {
                    width: Style.space(9)
                    height: Style.space(9)
                    radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    color: modelData.status === "running" ? "#4caf50" : Qt.darker(root.bar.foreground, 1.8)
                  }

                  Column {
                    width: rowInner.width - Style.space(9) - Style.space(78) - Style.space(16)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0

                    Text {
                      textFormat: Text.PlainText
                      text: modelData.name
                      elide: Text.ElideRight
                      width: parent.width
                      color: root.bar.foreground
                      font.family: root.bar.fontFamily
                      font.pixelSize: Style.font.body
                    }

                    Text {
                      textFormat: Text.PlainText
                      text: modelData.detail + (modelData.status === "running" ? " · running" : " · stopped")
                      elide: Text.ElideRight
                      width: parent.width
                      color: Qt.darker(root.bar.foreground, 1.5)
                      font.family: root.bar.fontFamily
                      font.pixelSize: Style.font.caption
                    }
                  }

                  Button {
                    id: actionButton
                    anchors.verticalCenter: parent.verticalCenter
                    width: Style.space(70)
                    bordered: true
                    fontFamily: root.bar.fontFamily
                    foreground: modelData.status === "running" ? root.bar.urgent : root.bar.foreground
                    text: {
                      if (root.busyId === modelData.id) return "…"
                      return modelData.status === "running" ? "■ Stop" : "▶ Play"
                    }
                    // One model at a time: while any model runs, only its Stop
                    // button stays enabled; every other Play is greyed out.
                    enabled: root.busyId === "" && (modelData.status === "running" || !root.anyRunning)
                    onClicked: {
                      if (modelData.status === "running") root.stopModel(modelData.id)
                      else root.startModel(modelData.id)
                    }
                  }
                }
              }
            }
          }

          Item { width: parent.width; height: Style.space(4) }
        }
      }
    }
  }
}
