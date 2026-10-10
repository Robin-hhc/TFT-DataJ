"""Small jobs for the existing Qt worker pools.

The optional predicate runs on the worker just before invoking the source
callable. It must read thread-safe state, not GUI widgets. Stale queued work
emits ``cancelled`` without invoking the callable or reporting a source error.

This does not interrupt an already running callable. Callers must retain their
completion-time generation checks and connect all terminal signals using
QueuedConnection. Admission limits, job ownership and signal disconnection
remain with the existing submitter.
"""
from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class Job(QRunnable):
    """Emit one of done/failed/cancelled and release both callable references."""

    def __init__(self, fn, *, is_current=None):
        super().__init__()
        self.fn = fn
        self.is_current = is_current
        self.signals = Signals()

    def run(self):
        try:
            if self.is_current is not None and not self.is_current():
                self.signals.cancelled.emit()
                return
            self.signals.done.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.fn = None
            self.is_current = None
