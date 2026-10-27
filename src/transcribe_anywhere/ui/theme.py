"""Colours and programmatically drawn icons (no image assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

STATE_COLORS = {
    "idle": "#64748b",          # slate
    "recording": "#e5484d",     # red
    "transcribing": "#f5a524",  # amber
}
SPEAKER_COLORS = {"Ich": "#2563eb", "Andere": "#16a34a", "⚑": "#f5a524"}

STYLE = """
QPushButton#recordButton {
    background: #e5484d; color: white; font-weight: 600; font-size: 14px;
    border: none; border-radius: 8px; padding: 10px 18px;
}
QPushButton#recordButton:hover { background: #d13d42; }
QPushButton#recordButton[recording="true"] { background: #334155; }
QListWidget { font-size: 13px; }
QListWidget::item { padding: 8px 6px; }
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


def rms_to_level(rms: float) -> float:
    """Map RMS (0..1) to a 0..1 meter value on a -60..0 dB scale."""
    import math

    db = 20 * math.log10(max(rms, 1e-9))
    return min(max((db + 60) / 60, 0.0), 1.0)
