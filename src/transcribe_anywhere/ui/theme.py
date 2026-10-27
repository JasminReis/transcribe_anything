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


def rms_to_level(rms: float) -> float:
    """Map RMS (0..1) to a 0..1 meter value on a -60..0 dB scale."""
    import math

    db = 20 * math.log10(max(rms, 1e-9))
    return min(max((db + 60) / 60, 0.0), 1.0)
