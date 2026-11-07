import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation {
    id: presentation

    function nextSlide() { presentation.goToNextSlide(); }

    Timer {
        id: advance
        interval: 7000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: nextSlide()
    }

    Slide {
        Rectangle { anchors.fill: parent; color: "#0C1A2A" }
        Image { id: logo1; source: "logo.png"; width: 120; height: 120; fillMode: Image.PreserveAspectFit
                anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.18 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; anchors.top: logo1.bottom; anchors.topMargin: 28
               text: "Say it. Done."; color: "#F3E9D8"; font.pixelSize: 34; font.bold: true }
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.62
               text: "Press Super + Space to open the Say Bar, then type what you want."
               color: "#9FB3C8"; font.pixelSize: 16 }
    }
    Slide {
        Rectangle { anchors.fill: parent; color: "#0C1A2A" }
        Text { anchors.centerIn: parent; horizontalAlignment: Text.AlignHCenter
               text: "Works when the grid doesn't\n\nYour session is protected during power cuts,\nand your data use is counted in your own currency."
               color: "#F3E9D8"; font.pixelSize: 24; lineHeight: 1.2 }
    }
    Slide {
        Rectangle { anchors.fill: parent; color: "#0C1A2A" }
        Text { anchors.centerIn: parent; horizontalAlignment: Text.AlignHCenter
               text: "Born in Africa. Built for the world.\n\nSayMy OS is open source and made to run well on the\ncomputers people actually have."
               color: "#F5B93A"; font.pixelSize: 24; lineHeight: 1.2 }
    }

    function onActivate() { }
    function onLeave() { }
}
