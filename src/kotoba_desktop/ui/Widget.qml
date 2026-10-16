// 横長のカプセル形のバー。左にマイクボタン、中央に波形、右に閉じるボタン、上に状態を示す吹き出しを置く。
// 設定とヘルプはトレイのメニューから開く。
// controller（状態・吹き出し・音量）と widget（ボタン操作・ドラッグ）は Python から渡される。
import QtQuick

Window {
    id: root
    width: 300
    height: 140  // 吹き出しとツールチップの分の余白を取る
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus

    readonly property string iconFont: "Segoe Fluent Icons"
    readonly property color panelColor: "#f22b2b2b"
    readonly property color accent: "#4cc2ff"
    readonly property color errorColor: "#ff6b6b"
    readonly property bool recording: controller.state === "recording"
    readonly property bool busy: controller.state === "recognizing" || controller.state === "injecting"
    readonly property bool unavailable: controller.state === "loading" || controller.state === "failed"

    // 吹き出し
    Rectangle {
        id: bubble
        visible: controller.bubble !== ""
        anchors.horizontalCenter: panel.horizontalCenter
        anchors.bottom: panel.top
        anchors.bottomMargin: 8
        width: Math.min(bubbleText.implicitWidth + 28, root.width - 8)
        height: bubbleText.implicitHeight + 14
        radius: 8
        color: root.panelColor
        border.color: controller.error ? root.errorColor : "#40ffffff"
        border.width: 1

        Text {
            id: bubbleText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, root.width - 36)
            text: controller.bubble
            color: controller.error ? root.errorColor : "white"
            font.pixelSize: 13
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // パネル本体。背景をドラッグすると動かせる
    Rectangle {
        id: panel
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        anchors.horizontalCenter: parent.horizontalCenter
        width: 260
        height: 52
        radius: height / 2
        color: root.panelColor
        border.color: controller.error ? root.errorColor : (root.recording ? "#804cc2ff" : "#30ffffff")
        border.width: 1

        // root.x / root.y で動かすと DPI の違うモニターをまたいだときに縮むので、移動は Python 側で行う
        MouseArea {
            anchors.fill: parent
            onPressed: widget.dragStarted()
            onPositionChanged: widget.dragMoved()
            onReleased: widget.dragFinished()
            onCanceled: widget.dragFinished()
        }

        // マイクボタン。録音中は停止ボタンになる
        Rectangle {
            id: mic
            anchors.left: parent.left
            anchors.leftMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 40
            height: 40
            radius: 20
            color: root.recording || root.busy ? root.accent : (micArea.containsMouse ? "#20ffffff" : "transparent")
            border.width: 2
            border.color: controller.error ? root.errorColor : (root.unavailable ? "#60ffffff" : root.accent)
            Behavior on color { ColorAnimation { duration: 120 } }

            Text {
                anchors.centerIn: parent
                visible: !root.recording
                text: ""  // マイク
                font.family: root.iconFont
                font.pixelSize: 17
                color: root.busy ? "#1b1b1b" : (root.unavailable ? "#80ffffff" : "white")
            }

            Rectangle {
                anchors.centerIn: parent
                visible: root.recording
                width: 12
                height: 12
                radius: 3
                color: "#1b1b1b"
            }

            MouseArea {
                id: micArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: widget.micClicked()
            }

            ToolTipText {
                visible: micArea.containsMouse
                text: (root.recording ? "停止" : "開始") + "（" + controller.hotkeyText + "）"
            }
        }

        // 中央。待機中は案内、録音中は音量の波形、認識中は流れる波
        Item {
            id: center
            anchors.left: mic.right
            anchors.leftMargin: 12
            anchors.right: closeButton.left
            anchors.rightMargin: 8
            anchors.top: parent.top
            anchors.bottom: parent.bottom

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: !root.recording && !root.busy && !root.unavailable
                text: controller.hotkeyText + " かクリックで話す"
                color: "#a0ffffff"
                font.pixelSize: 12
                elide: Text.ElideRight
                width: parent.width
            }

            Item {
                id: wave
                anchors.fill: parent
                anchors.topMargin: 12
                anchors.bottomMargin: 12
                visible: root.recording || root.busy

                readonly property int barWidth: 3
                readonly property int gap: 3
                readonly property int count: Math.max(1, Math.floor((width + gap) / (barWidth + gap)))
                property var levels: []  // 古い順。右端が最新
                property real phase: 0

                function reset() {
                    levels = new Array(count).fill(0)
                }
                Component.onCompleted: reset()
                onCountChanged: reset()
                onVisibleChanged: if (visible) reset()

                // 音量が変わらない間も波形を流すため、一定間隔で取り込む
                Timer {
                    interval: 40
                    repeat: true
                    running: root.recording
                    onTriggered: {
                        const next = wave.levels.slice(1)
                        // 小さい声でも動きが見えるように平方根で持ち上げる
                        next.push(Math.sqrt(Math.min(1, controller.level)))
                        wave.levels = next
                    }
                }

                NumberAnimation on phase {
                    running: root.busy
                    from: 0
                    to: 2 * Math.PI
                    duration: 1200
                    loops: Animation.Infinite
                }

                Row {
                    anchors.centerIn: parent
                    spacing: wave.gap
                    Repeater {
                        model: wave.count
                        Rectangle {
                            required property int index
                            readonly property real value: root.busy
                                ? 0.15 + 0.35 * (0.5 + 0.5 * Math.sin(wave.phase * 2 - index * 0.45))
                                : (wave.levels[index] ?? 0)
                            anchors.verticalCenter: parent.verticalCenter
                            width: wave.barWidth
                            height: Math.max(wave.barWidth, wave.height * value)
                            radius: width / 2
                            color: root.busy ? root.accent : "white"
                            opacity: root.busy ? 0.9 : 0.55 + 0.45 * value
                            Behavior on height { NumberAnimation { duration: 60 } }
                        }
                    }
                }
            }
        }

        IconButton {
            id: closeButton
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            glyph: ""  // 閉じる
            tip: "閉じる"
            onClicked: widget.close()
        }
    }

    component IconButton: Rectangle {
        id: button
        property string glyph
        property string tip
        property int size: 28
        property int glyphSize: 10
        signal clicked
        width: size
        height: size
        radius: size / 2
        color: area.containsMouse ? "#20ffffff" : "transparent"

        Text {
            anchors.centerIn: parent
            text: button.glyph
            font.family: root.iconFont
            font.pixelSize: button.glyphSize
            color: "white"
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            onClicked: button.clicked()
        }
        ToolTipText {
            visible: area.containsMouse && button.tip !== ""
            text: button.tip
        }
    }

    component ToolTipText: Rectangle {
        property alias text: label.text
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.bottom
        anchors.topMargin: 8
        width: label.implicitWidth + 12
        height: label.implicitHeight + 6
        radius: 4
        color: "#e0000000"
        z: 10
        Text {
            id: label
            anchors.centerIn: parent
            color: "white"
            font.pixelSize: 11
        }
    }
}
