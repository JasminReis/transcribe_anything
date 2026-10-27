"""Animated progress card shown while a session is being transcribed."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from transcribe_anywhere.session.export import fmt_duration
from transcribe_anywhere.ui.theme import ACCENT, ACCENT_2, ACCENT_3

STAGES = [("analyse", "Audio analysieren"), ("load", "Modell laden"), ("transcribe", "Transkribieren")]
TITLES = {
    "queued": "Wartet …",
    "analyse": "Sprache wird gesucht",
    "load": "Spracherkennung startet",
    "transcribe": "Transkribiere",
    "live": "Live-Transkription",
    "finish": "Letzte Abschnitte werden transkribiert",
    "done": "Fertig",
}


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class ProgressRing(QWidget):
    """Gradient ring; spins while the duration is unknown, fills smoothly otherwise."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(92, 92)
        self._value = 0.0
        self._target = 0.0
        self._spin = 0.0
        self.indeterminate = True
        self.center_text = ""
        self._anim = QVariantAnimation(self, duration=450, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_value)
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._timer.start()

    def set_value(self, value: float) -> None:
        value = min(max(value, 0.0), 1.0)
        if abs(value - self._target) < 1e-4:
            return
        self._target = value
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(value)
        self._anim.start()

    def _set_value(self, v) -> None:
        self._value = float(v)
        self.update()

    def _tick(self) -> None:
        self._spin = (self._spin + 4.0) % 360
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(8, 8, self.width() - 16, self.height() - 16)
        track = QColor(self.palette().text().color())
        track.setAlpha(28)
        p.setPen(QPen(track, 8, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(r)

        grad = QConicalGradient(r.center(), 90 - self._spin)
        for pos, color in ((0.0, ACCENT), (0.33, ACCENT_2), (0.66, ACCENT_3), (1.0, ACCENT)):
            grad.setColorAt(pos, QColor(color))
        p.setPen(QPen(grad, 8, Qt.SolidLine, Qt.RoundCap))
        f = QFont(self.font())
        f.setWeight(QFont.DemiBold)
        if self.indeterminate:
            p.drawArc(r, int((90 - self._spin) * 16), int(-100 * 16))
            if self.center_text:
                f.setPointSizeF(11)
                p.setFont(f)
                p.setPen(QColor(ACCENT))
                p.drawText(r, Qt.AlignCenter, self.center_text)
        else:
            # the gradient keeps slowly rotating → the ring looks alive even when progress is slow
            p.drawArc(r, 90 * 16, int(-360 * 16 * max(self._value, 0.01)))
            p.setPen(self.palette().text().color())
            f.setPointSizeF(13)
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, f"{int(self._value * 100)} %")


class StageChip(QLabel):
    def set_state(self, label: str, state: str) -> None:
        mark = {"done": "✓", "active": "●", "todo": "○"}[state]
        color = {"done": "#16a34a", "active": ACCENT, "todo": "#94a3b8"}[state]
        weight = 600 if state == "active" else 400
        self.setText(f"<span style='color:{color}; font-weight:{weight}'>{mark}&nbsp;{label}</span>")


class ProgressCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.ring = ProgressRing()
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.eta = QLabel()
        self.eta.setStyleSheet("color: #64748b;")
        self.chips = [StageChip() for _ in STAGES]
        self.stats = QLabel()
        self.stats.setStyleSheet("color: #64748b;")
        self.ticker = QLabel()
        self.ticker.setWordWrap(True)
        self.ticker.setStyleSheet("font-style: italic;")
        self._fade = QGraphicsOpacityEffect(self.ticker)
        self.ticker.setGraphicsEffect(self._fade)
        self._fade_anim = QPropertyAnimation(self._fade, b"opacity", self, duration=500)

        head = QHBoxLayout()
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.eta)
        chips = QHBoxLayout()
        chips.setSpacing(16)
        for c in self.chips:
            chips.addWidget(c)
        chips.addStretch(1)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addLayout(head)
        text.addLayout(chips)
        text.addWidget(self.stats)
        text.addWidget(self.ticker)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 18, 14)
        row.setSpacing(18)
        row.addWidget(self.ring, 0, Qt.AlignVCenter)
        row.addLayout(text, 1)
        self._last_text = ""
        self.set_queued()

    def set_queued(self, live: bool = False) -> None:
        self.ring.indeterminate = True
        self.ring.center_text = "LIVE" if live else ""
        self.title.setText(TITLES["live"] if live else TITLES["queued"])
        self.eta.clear()
        self._set_chips("queued")
        for c in self.chips:
            c.setVisible(not live)
        self.stats.setText("Live-Transkription startet …" if live else "Die Transkription startet gleich.")
        self.ticker.clear()
        self._last_text = ""

    def update_progress(self, p) -> None:
        self.title.setText(TITLES.get(p.stage, p.stage))
        self._set_chips(p.stage)
        live = p.stage in ("live", "finish")
        for c in self.chips:
            c.setVisible(not live)
        self.ring.center_text = "LIVE" if p.stage == "live" else ""
        if p.stage == "load":
            self.ring.indeterminate = True
            self.stats.setText(f"{p.engine or 'Spracherkennung'} wird geladen – "
                               "beim ersten Mal wird das Modell heruntergeladen.")
            self.eta.clear()
        elif p.stage == "live":
            self.ring.indeterminate = True
            state = "aktuell" if p.lag < 45 else f"Rückstand {_clock(p.lag)}"
            self.stats.setText(f"Mitgeschrieben bis {_clock(p.done_seconds)} von {_clock(p.audio_seconds)}"
                               f" · {state} · {p.engine}")
            self.eta.clear()
        elif p.stage == "finish":
            self.ring.indeterminate = False
            self.ring.set_value(p.fraction)
            self.stats.setText(f"Noch {_clock(p.lag)} Aufnahme offen · {p.engine}")
            eta = p.eta
            self.eta.setText(f"noch ca. {_eta_text(eta)}" if eta is not None else "")
        elif p.stage == "analyse":
            self.ring.indeterminate = False
            self.ring.set_value(0.1 * p.fraction)
            self.stats.setText(f"Stille und Geräusche werden entfernt · {fmt_duration(p.audio_seconds)} Audio")
            self.eta.clear()
        elif p.stage in ("transcribe", "done"):
            self.ring.indeterminate = False
            self.ring.set_value(0.1 + 0.9 * p.fraction)
            removed = 1 - p.speech_seconds / p.audio_seconds if p.audio_seconds else 0
            line = (f"{_clock(p.done_seconds)} von {_clock(p.speech_seconds)} Sprache"
                    f" · Stille entfernt: {removed:.0%}")
            if p.speed:
                line += f" · {p.speed:.1f}× Echtzeit"
            self.stats.setText(line)
            eta = p.eta
            self.eta.setText(f"noch ca. {_eta_text(eta)}" if eta is not None else "")
        if p.last_text and p.last_text != self._last_text:
            self._last_text = p.last_text
            text = p.last_text if len(p.last_text) < 160 else p.last_text[:157] + "…"
            self.ticker.setText(f"„{text}“")
            self._fade_anim.stop()
            self._fade_anim.setStartValue(0.15)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

    def _set_chips(self, stage: str) -> None:
        order = [s for s, _ in STAGES]
        current = order.index(stage) if stage in order else (len(order) if stage == "done" else -1)
        for i, ((_, label), chip) in enumerate(zip(STAGES, self.chips)):
            chip.set_state(label, "done" if i < current else ("active" if i == current else "todo"))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        base = QColor(self.palette().base().color())
        p.fillPath(path, base)
        border = QColor(ACCENT)
        border.setAlpha(70)
        p.setPen(QPen(border, 1.2))
        p.drawPath(path)


def _eta_text(seconds: float) -> str:
    if seconds < 60:
        return "1 min"
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 90 else f"{minutes / 60:.1f} h".replace(".", ",")
