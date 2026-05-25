from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def create_app_icon():
    """Create a local PDF/chat icon without requiring an image file at runtime."""
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    background = QPainterPath()
    background.addRoundedRect(8, 8, 112, 112, 24, 24)
    painter.fillPath(background, QColor("#2457A6"))

    document = QPainterPath()
    document.moveTo(38, 24)
    document.lineTo(78, 24)
    document.lineTo(96, 42)
    document.lineTo(96, 94)
    document.quadTo(96, 102, 88, 102)
    document.lineTo(38, 102)
    document.quadTo(30, 102, 30, 94)
    document.lineTo(30, 32)
    document.quadTo(30, 24, 38, 24)
    painter.fillPath(document, QColor("#FFFFFF"))

    fold = QPainterPath()
    fold.moveTo(78, 24)
    fold.lineTo(96, 42)
    fold.lineTo(82, 42)
    fold.quadTo(78, 42, 78, 38)
    fold.closeSubpath()
    painter.fillPath(fold, QColor("#CFE0FF"))

    painter.setPen(QPen(QColor("#2457A6"), 5, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(44, 54, 78, 54)
    painter.drawLine(44, 68, 82, 68)
    painter.drawLine(44, 82, 66, 82)

    bubble = QPainterPath()
    bubble.addRoundedRect(58, 70, 48, 34, 12, 12)
    bubble.moveTo(72, 100)
    bubble.lineTo(62, 112)
    bubble.lineTo(84, 102)
    painter.fillPath(bubble, QColor("#31C48D"))

    painter.setPen(QPen(QColor("#FFFFFF"), 5, Qt.SolidLine, Qt.RoundCap))
    painter.drawPoint(QPoint(72, 87))
    painter.drawPoint(QPoint(84, 87))
    painter.drawPoint(QPoint(96, 87))

    painter.end()
    return QIcon(pixmap)
