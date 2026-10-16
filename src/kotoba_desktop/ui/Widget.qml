// Windows 標準の音声入力（Win+H）に似た小さなパネル。
// 左から設定・マイク・ヘルプ、右上が閉じる。上に状態を示す吹き出しを置く。
// controller（状態・吹き出し・音量）と widget（ボタン操作・位置の保存）は Python から渡される。
import QtQuick

Window {
    id: root
    width: 280
    height: 178  // パネルの下にツールチップの分の余白を取る
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
        width: 240
        height: 84
        radius: 12
        color: root.panelColor
        border.color: "#30ffffff"
        border.width: 1

        MouseArea {
            anchors.fill: parent
            property point start
            property point origin
            onPressed: (mouse) => {
                start = mapToGlobal(mouse.x, mouse.y)
                origin = Qt.point(root.x, root.y)
            }
            onPositionChanged: (mouse) => {
                const p = mapToGlobal(mouse.x, mouse.y)
                root.x = origin.x + p.x - start.x
                root.y = origin.y + p.y - start.y
            }
            onReleased: widget.savePosition(root.x, root.y)
        }

        IconButton {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            glyph: ""  // 設定
            tip: "設定"
            onClicked: widget.openSettings()
        }

        IconButton {
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            glyph: ""  // ヘルプ
            tip: "ヘルプ"
            onClicked: widget.showHelp()
        }

        IconButton {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 4
            size: 22
            glyph: ""  // 閉じる
            glyphSize: 9
            tip: "閉じる"
            onClicked: widget.close()
        }

        // マイクボタン
        Rectangle {
            id: mic
            anchors.centerIn: parent
            width: 56
            height: 56
            radius: 28
            color: root.recording || root.busy ? root.accent : (micArea.containsMouse ? "#20ffffff" : "transparent")
            border.width: 2
            border.color: controller.error ? root.errorColor : (root.unavailable ? "#60ffffff" : root.accent)

            Text {
                anchors.centerIn: parent
                visible: !root.recording && !root.busy
                text: ""  // マイク
                font.family: root.iconFont
                font.pixelSize: 22
                color: root.unavailable ? "#80ffffff" : "white"
            }

            // 録音中: 音量に合わせて点が伸びる。認識中: 点が回る
            Item {
                id: dots
                anchors.centerIn: parent
                width: 30
                height: 30
                visible: root.recording || root.busy

                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        readonly property real gain: [0.7, 1.0, 0.7][index]
                        width: 6
                        radius: 3
                        color: "#1b1b1b"
                        x: root.busy ? 12 + 9 * Math.cos(index * 2 * Math.PI / 3) : 3 + index * 9
                        height: root.busy ? 6 : 6 + 18 * Math.min(1, controller.level * gain)
                        y: root.busy ? 12 + 9 * Math.sin(index * 2 * Math.PI / 3) : (30 - height) / 2
                        Behavior on height { NumberAnimation { duration: 60 } }
                    }
                }

                RotationAnimator on rotation {
                    running: root.busy
                    from: 0
                    to: 360
                    duration: 900
                    loops: Animation.Infinite
                }
                onVisibleChanged: if (!root.busy) rotation = 0
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
    }

    component IconButton: Rectangle {
        id: button
        property string glyph
        property string tip
        property int size: 34
        property int glyphSize: 15
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
        anchors.topMargin: 4
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
