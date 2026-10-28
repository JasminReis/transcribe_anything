"""The small always-on-top recording widget shown during a meeting."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QToolButton, QWidget

from transcribe_anywhere.ui.theme import STATE_COLORS, rms_to_level

MUTED_COLOR = "#f87171"


def mic_icon(muted: bool, size: int = 32) -> QIcon:
    """Microphone glyph, crossed out when muted (drawn, no image assets)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 16
    color = QColor(MUTED_COLOR if muted else "white")
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(5.5 * s, 1.5 * s, 5 * s, 8.5 * s), 2.5 * s, 2.5 * s)   # capsule
    pen = QPen(color, 1.4 * s, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(3.5 * s, 4 * s, 9 * s, 8.5 * s), 180 * 16, 180 * 16)            # holder
    p.drawLine(QLineF(8 * s, 12.5 * s, 8 * s, 14.5 * s))                              # stem
    if muted:
        p.setPen(QPen(QColor("#0f172a"), 3.2 * s, Qt.SolidLine, Qt.RoundCap))         # gap
        p.drawLine(QLineF(2.5 * s, 2.5 * s, 13.5 * s, 13.5 * s))
        p.setPen(QPen(color, 1.5 * s, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QLineF(2.5 * s, 2.5 * s, 13.5 * s, 13.5 * s))
    p.end()
    return QIcon(pix)


class LevelMeter(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.label = label
        self.value = 0.0
        self.muted = False
        self.setFixedSize(92, 22)

    def set_value(self, value: float) -> None:
        # fast attack, slow release, like a real meter
        self.value = value if value > self.value else self.value * 0.8 + value * 0.2
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(MUTED_COLOR if self.muted else "#cbd5e1"))
        p.drawText(QRectF(0, 0, 44, 22), Qt.AlignVCenter | Qt.AlignLeft,
                   "Stumm" if self.muted else self.label)
        bars, x0, w, gap = 6, 46, 5, 2
        for i in range(bars):
            on = not self.muted and self.value * bars > i + 0.15
            color = "#22c55e" if i < 4 else ("#eab308" if i < 5 else "#ef4444")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color if on else "#334155"))
            h = 8 + i * 2
            p.drawRoundedRect(QRectF(x0 + i * (w + gap), 18 - h, w, h), 1.5, 1.5)


class RecordingPill(QWidget):
    stop_requested = Signal()
    marker_requested = Signal()

    def __init__(self, controller):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.controller = controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag: QPoint | None = None

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {STATE_COLORS['recording']}; font-size: 16px;")
        keep = self.dot.sizePolicy()
        keep.setRetainSizeWhenHidden(True)   # blinking must not shift the layout
        self.dot.setSizePolicy(keep)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("color: white; font: 600 14px monospace;")
        self.mic = LevelMeter("Mic")
        self.system = LevelMeter("System")
        self.live = QLabel()
        self.live.setStyleSheet("font: 600 12px;")

        self.mute = QToolButton(checkable=True)
        self.mute.setIconSize(QSize(16, 16))
        marker = QToolButton(text="⚑", toolTip="Marker setzen")
        stop = QToolButton(text="■", toolTip="Aufnahme beenden")
        for b in (self.mute, marker, stop):
            b.setStyleSheet(
                "QToolButton { color: white; background: #334155; border: none; border-radius: 6px;"
                " font-size: 14px; min-width: 28px; min-height: 26px; }"
                "QToolButton:hover { background: #475569; }"
                "QToolButton:checked { background: #4c1d24; }"
                "QToolButton:checked:hover { background: #5f2630; }"
            )
        stop.setStyleSheet(stop.styleSheet().replace("#334155", "#e5484d").replace("#475569", "#d13d42"))
        self.mute.toggled.connect(self._on_mute_toggled)
        marker.clicked.connect(self.marker_requested)
        stop.clicked.connect(self.stop_requested)
        self._show_mute(False)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(10)
        for w in (self.dot, self.timer_label, self.mic, self.system, self.live, self.mute, marker, stop):
            row.addWidget(w)

        self._tick = QTimer(self, interval=100, timeout=self._refresh)

    def _on_mute_toggled(self, muted: bool) -> None:
        self.controller.set_mic_muted(muted)
        self._show_mute(muted)

    def _show_mute(self, muted: bool) -> None:
        self.mute.setIcon(mic_icon(muted))
        self.mute.setToolTip("Mikrofon einschalten" if muted else "Mikrofon stummschalten")
        self.mic.muted = muted
        self.mic.update()

    def show_at_default_position(self) -> None:
        self.mute.setChecked(self.controller.mic_muted)   # every recording starts unmuted
        self._show_mute(self.controller.mic_muted)
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.top() + 24)
        self.show()
        self._tick.start()

    def hideEvent(self, event) -> None:
        self._tick.stop()
        super().hideEvent(event)

    def _refresh(self) -> None:
        secs = int(self.controller.elapsed)
        self.timer_label.setText(f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}")
        levels = self.controller.levels()
        self.mic.set_value(rms_to_level(levels.get("mic", 0.0)))
        self.system.set_value(rms_to_level(levels.get("system", 0.0)))
        live = self.controller.live_status()
        self.live.setVisible(live is not None)
        if live:
            self.live.setText(live[0])
            self.live.setStyleSheet(f"color: {live[1]}; font: 600 12px;")
            self.adjustSize()
        self.dot.setVisible(int(self.controller.elapsed * 2) % 2 == 0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        p.fillPath(path, QColor(15, 23, 42, 235))

    # drag anywhere to move
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None
