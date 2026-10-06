"""Passive Windows mouse notifications; never consume mouse input.

MSLLHOOKSTRUCT: https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msllhookstruct
"""
import ctypes as c
from ctypes import wintypes as w
import time
from PySide6.QtCore import QObject, Signal
from selection_tracker import MouseNotice


class MouseEvent(c.Structure):
    _fields_ = [('pt', w.POINT), ('mouseData', w.DWORD), ('flags', w.DWORD),
                ('time', w.DWORD), ('dwExtraInfo', c.c_size_t)]


def released_button(code, message, event):
    if code < 0 or message != 0x020C or event.flags & 1:
        return 0
    button = event.mouseData >> 16
    return button if button in (1, 2) else 0


class MouseShortcut(QObject):
    released = Signal(int, object)
    # Connect this using Qt.QueuedConnection: game selection work must not run
    # synchronously inside LowLevelMouseProc on the GUI/native hook thread.
    left_event = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.handle = None
        self.left_down = None
        self.drag_notified = False
        self.user = c.WinDLL('user32', use_last_error=True)
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.proc_type = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, w.WPARAM, w.LPARAM)
        self.user.SetWindowsHookExW.argtypes = [c.c_int, self.proc_type, w.HINSTANCE, w.DWORD]
        self.user.SetWindowsHookExW.restype = w.HANDLE
        self.user.CallNextHookEx.argtypes = [w.HANDLE, c.c_int, w.WPARAM, w.LPARAM]
        self.user.CallNextHookEx.restype = c.c_ssize_t
        self.user.UnhookWindowsHookEx.argtypes = [w.HANDLE]
        self.user.UnhookWindowsHookEx.restype = w.BOOL
        self.user.GetForegroundWindow.restype = w.HWND
        self.kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.kernel.GetModuleHandleW.restype = w.HMODULE
        self.callback = self.proc_type(self.dispatch)

    def dispatch(self, code, message, data):
        try:
            if code >= 0 and message == 0x020C:
                event = c.cast(data, c.POINTER(MouseEvent)).contents
                button = released_button(code, message, event)
                if button:
                    # Only enqueue notification. No capture, OCR or queries in hook.
                    self.released.emit(button, int(self.user.GetForegroundWindow() or 0))
            elif code >= 0 and (message in (0x0201, 0x0202)
                                or (message == 0x0200 and getattr(self, 'left_down', None)
                                    and not self.drag_notified)):
                event = c.cast(data, c.POINTER(MouseEvent)).contents
                if not event.flags & 3:
                    x, y = int(event.pt.x), int(event.pt.y)
                    action = 'down' if message == 0x0201 else 'up' if message == 0x0202 else 'move'
                    notify = True
                    if action == 'down':
                        self.left_down = (x, y)
                        self.drag_notified = False
                    elif action == 'up':
                        self.left_down = None
                        self.drag_notified = False
                    else:
                        # At most one excursion notification per press. Idle moves
                        # do no extra Win32 calls and never enqueue OCR/capture.
                        dx, dy = x - self.left_down[0], y - self.left_down[1]
                        notify = dx * dx + dy * dy > 8 * 8
                        if notify:
                            self.drag_notified = True
                    if notify:
                        self.left_event.emit(MouseNotice(action, x, y, time.monotonic(),
                                            int(self.user.GetForegroundWindow() or 0)))
        finally:
            return self.user.CallNextHookEx(self.handle, code, message, data)

    def start(self):
        if not self.handle:
            self.handle = self.user.SetWindowsHookExW(14, self.callback,
                                                     self.kernel.GetModuleHandleW(None), 0)
        return bool(self.handle)

    def stop(self):
        if self.handle:
            if self.user.UnhookWindowsHookEx(self.handle):
                self.handle = None
