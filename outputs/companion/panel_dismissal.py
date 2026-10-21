"""Conservative Qt-side completion of passive outside mouse clicks."""
from contextlib import contextmanager
from dataclasses import dataclass
import math
import time
import weakref

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid


@dataclass(frozen=True)
class PanelMouseNotice:
    action: str
    x: int
    y: int
    at: float
    inside: bool | None
    blocked: bool = False


class PanelDismissal(QObject):
    """Collapse only after both ends of a current outside click are known.

    Native input is observed elsewhere. This object runs on the Qt thread and
    protects popup/modal interactions even when their native notices are queued
    until after the blocking window has closed.
    """

    tracking_changed = Signal(bool, bool)

    def __init__(self, parent, collapse):
        super().__init__(parent)
        self._collapse = collapse
        self._enabled = True
        self._opened = False
        self._alive = True
        self._down = None
        self._pressed = False
        self._barrier = time.perf_counter()
        self._last_notice_at = self._barrier
        self._blockers = {}
        self._blocker_subscriptions = {}
        self._suspensions = 0
        self._application = QApplication.instance()
        if self._application is not None:
            for widget in self._application.topLevelWidgets():
                if widget.isVisible() and self._is_blocker(widget):
                    self._add_blocker(widget)
            self._application.installEventFilter(self)

    @property
    def tracking(self):
        return self._alive and self._enabled and self._opened

    @property
    def blocked(self):
        return bool(self._blockers) or self._suspensions > 0

    def _reset(self):
        self._down = None
        self._pressed = False
        self._barrier = time.perf_counter()
        self._last_notice_at = self._barrier

    def _emit_tracking(self):
        self.tracking_changed.emit(self.tracking, self.blocked)

    def set_open(self, opened):
        opened = bool(opened)
        if self._alive and opened != self._opened:
            self._opened = opened
            self._reset()
            self._emit_tracking()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if self._alive and enabled != self._enabled:
            self._enabled = enabled
            self._reset()
            self._emit_tracking()

    @contextmanager
    def suspended(self):
        """Block native dialog interactions that have no Qt popup Show event."""
        active = self._alive
        if active:
            self._suspensions += 1
            self._reset()
            self._emit_tracking()
        try:
            yield
        finally:
            if active and self._alive:
                self._suspensions -= 1
                self._reset()
                self._emit_tracking()

    @staticmethod
    def _is_blocker(widget):
        return (widget.isWindow()
                and (widget.windowType() == Qt.WindowType.Popup
                     or widget.windowModality() != Qt.WindowModality.NonModal))

    def _add_blocker(self, widget):
        key = id(widget)
        self._blockers[key] = widget
        if key in self._blocker_subscriptions:
            return
        owner_ref = weakref.ref(self)

        def destroyed(_object=None):
            owner = owner_ref()
            if owner is None or not isValid(owner) or not owner._alive:
                return
            owner._blocker_subscriptions.pop(key, None)
            if owner._blockers.pop(key, None) is not None:
                owner._reset()
                owner._emit_tracking()

        self._blocker_subscriptions[key] = (weakref.ref(widget), destroyed)
        widget.destroyed.connect(destroyed)

    def eventFilter(self, watched, event):
        if self._alive and isinstance(watched, QWidget):
            kind = event.type()
            key = id(watched)
            if kind == QEvent.Type.Show and self._is_blocker(watched):
                self._add_blocker(watched)
                self._reset()
                self._emit_tracking()
            elif kind in (QEvent.Type.Hide, QEvent.Type.Destroy) and key in self._blockers:
                self._blockers.pop(key, None)
                # The click that closed a popup must stay invalid after Hide.
                self._reset()
                self._emit_tracking()
        return False

    @Slot(object)
    def on_mouse(self, notice):
        if not self.tracking or self.blocked:
            self._down = None
            self._pressed = False
            return
        if (not isinstance(notice, PanelMouseNotice)
                or notice.action not in ('down', 'up', 'move')
                or type(notice.x) is not int or type(notice.y) is not int
                or type(notice.at) not in (int, float)
                or not math.isfinite(notice.at)
                or type(notice.blocked) is not bool
                or not (notice.inside is True or notice.inside is False
                        or notice.inside is None)):
            self._down = None
            self._pressed = False
            return
        now = time.perf_counter()
        if (notice.blocked or notice.at <= self._barrier
                or notice.at <= self._last_notice_at
                or notice.at > now or now - notice.at > 0.75):
            self._down = None
            self._pressed = False
            return
        self._last_notice_at = notice.at
        if notice.action == 'move':
            # The passive hook sends move only for a drag excursion. Once
            # cancelled, returning to the original point cannot restore a click.
            self._down = None
            return
        if notice.action == 'down':
            if self._pressed:
                self._down = None
                return
            self._pressed = True
            self._down = notice if notice.inside is False else None
            return
        down, self._down = self._down, None
        self._pressed = False
        if down is None or notice.inside is not False:
            return
        dx, dy = notice.x - down.x, notice.y - down.y
        if dx * dx + dy * dy <= 8 * 8:
            self._collapse()

    def shutdown(self):
        if not self._alive:
            return
        self._alive = False
        self._reset()
        if self._application is not None:
            self._application.removeEventFilter(self)
            self._application = None
        for widget_ref, callback in self._blocker_subscriptions.values():
            widget = widget_ref()
            if widget is not None and isValid(widget):
                widget.destroyed.disconnect(callback)
        self._blocker_subscriptions.clear()
        self._blockers.clear()
        self._suspensions = 0
        self._emit_tracking()
