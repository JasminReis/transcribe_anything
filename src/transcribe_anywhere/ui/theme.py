"""Colours and programmatically drawn icons (no image assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

STATE_COLORS = {
    "idle": "#64748b",          # slate
    "recording": "#e5484d",     # red
    "transcribing": "#f5a524",  # amber
}
SPEAKER_COLORS = {"Ich": "#2563eb", "Andere": "#16a34a", "Gast": "#16a34a", "⚑": "#f5a524"}

ACCENT = "#7c3aed"      # violet
ACCENT_2 = "#2563eb"    # blue
ACCENT_3 = "#06b6d4"    # cyan

STYLE = """
QPushButton#recordButton {
    background: #e5484d; color: white; font-weight: 600; font-size: 14px;
    border: none; border-radius: 8px; padding: 10px 18px;
}
QPushButton#recordButton:hover { background: #d13d42; }
QPushButton#recordButton[recording="true"] { background: #334155; }

QPushButton#primary, QToolButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #2563eb);
    color: white; font-weight: 600; border: none; border-radius: 8px; padding: 7px 14px;
}
QPushButton#primary:hover, QToolButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #1d4ed8);
}
QPushButton#primary:disabled, QToolButton#primary:disabled { background: #cbd5e1; color: #f8fafc; }

QComboBox#modeBox {
    border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 12px; background: white;
    font-size: 13px; font-weight: 600; color: #334155; min-width: 200px;
}
QComboBox#modeBox:hover { border-color: #7c3aed; }
QComboBox#modeBox:disabled { color: #94a3b8; background: #f8fafc; }
QComboBox#modeBox::drop-down { border: none; width: 22px; }

QPushButton#settingsButton {
    background: white; color: #334155; font-weight: 600; font-size: 13px;
    border: 1px solid #cbd5e1; border-radius: 8px; padding: 9px 16px;
}
QPushButton#settingsButton:hover { background: #f5f3ff; border-color: #7c3aed; color: #6d28d9; }
QPushButton#settingsButton:pressed { background: #ede9fe; }
QToolButton#primary::menu-button { border: none; width: 18px; }

QTabWidget::pane { border: none; }
QTabBar::tab {
    padding: 7px 16px; margin-right: 4px; border: none; border-bottom: 2px solid transparent;
    font-weight: 500; color: #64748b;
}
QTabBar::tab:selected { color: #7c3aed; border-bottom: 2px solid #7c3aed; }

QListWidget { font-size: 13px; }
QListWidget::item { padding: 8px 6px; }
QProgressBar#thin { border: none; background: rgba(124,58,237,0.12); border-radius: 2px; max-height: 4px; }
QProgressBar#thin::chunk { border-radius: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #06b6d4); }
QLabel#toast {
    background: rgba(15,23,42,0.92); color: white; border-radius: 16px; padding: 8px 18px; font-weight: 500;
}
"""


def state_icon(state: str, size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("white"), size * 0.06))
    p.setBrush(QColor(STATE_COLORS.get(state, STATE_COLORS["idle"])))
    m = size * 0.08
    p.drawEllipse(QRectF(m, m, size - 2 * m, size - 2 * m))
    # A small "waveform" glyph so the icon reads as audio, not just a dot
    p.setPen(QPen(QColor("white"), size * 0.07, Qt.SolidLine, Qt.RoundCap))
    cx, cy = size / 2, size / 2
    for dx, h in ((-0.18, 0.12), (-0.06, 0.24), (0.06, 0.18), (0.18, 0.08)):
        x = cx + dx * size
        p.drawLine(QLineF(x, cy - h * size * 0.7, x, cy + h * size * 0.7))
    p.end()
    return QIcon(pm)


def app_icon_image(size: int = 256):
    """The application icon: violet→blue rounded square with a white sound wave."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QLinearGradient, QPainterPath

    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    m = size * 0.04
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    grad = QLinearGradient(QPointF(rect.left(), rect.top()), QPointF(rect.right(), rect.bottom()))
    grad.setColorAt(0, QColor(ACCENT))
    grad.setColorAt(1, QColor(ACCENT_2))
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    p.fillPath(path, grad)
    # sound wave: rounded bars, tallest in the middle
    bars = (0.22, 0.42, 0.62, 0.42, 0.22) if size < 40 else (0.18, 0.36, 0.58, 0.40, 0.26, 0.14)
    width = size * (0.085 if size < 40 else 0.07)
    gap = size * (0.055 if size < 40 else 0.045)
    total = len(bars) * width + (len(bars) - 1) * gap
    x = (size - total) / 2
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    for h in bars:
        hh = size * h
        p.drawRoundedRect(QRectF(x, (size - hh) / 2, width, hh), width / 2, width / 2)
        x += width + gap
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(app_icon_image(s)))
    return icon


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Save the app icon as a multi-size Windows .ico (PNG entries)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    blobs = []
    for s in sizes:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        app_icon_image(s).save(buf, "PNG")
        blobs.append((s, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, images = b"", b""
    for s, png in blobs:
        dim = 0 if s >= 256 else s                     # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        images += png
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + images)


def gear_icon(color: str = "#334155", size: int = 40) -> QIcon:
    """Settings gear: a toothed wheel with a hole (drawn, no image assets)."""
    import math

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainterPath, QPolygonF

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c, outer, inner, teeth = size / 2, size * 0.47, size * 0.36, 8
    points = []
    for i in range(teeth * 4):
        angle = 2 * math.pi * (i - 0.5) / (teeth * 4)
        r = outer if i % 4 in (1, 2) else inner
        points.append(QPointF(c + r * math.cos(angle), c + r * math.sin(angle)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(QPointF(c, c), size * 0.15, size * 0.15)
    p.fillPath(path.subtracted(hole), QColor(color))
    p.end()
    return QIcon(pm)


def rms_to_level(rms: float) -> float:
    """Map RMS (0..1) to a 0..1 meter value on a -60..0 dB scale."""
    import math

    db = 20 * math.log10(max(rms, 1e-9))
    return min(max((db + 60) / 60, 0.0), 1.0)
