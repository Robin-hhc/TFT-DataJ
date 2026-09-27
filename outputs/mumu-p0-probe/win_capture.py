"""P0 experiment: observe a selected MuMu window and capture only while foreground.

No input injection, game memory access, network access, or continuous recording.
"""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

user = c.WinDLL("user32", use_last_error=True)
kernel = c.WinDLL("kernel32", use_last_error=True)

def api(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn

CALLBACK = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
api(user, "EnumWindows", [CALLBACK, w.LPARAM], w.BOOL)
api(user, "IsWindow", [w.HWND], w.BOOL)
api(user, "IsWindowVisible", [w.HWND], w.BOOL)
api(user, "IsIconic", [w.HWND], w.BOOL)
api(user, "GetForegroundWindow", [], w.HWND)
api(user, "WindowFromPoint", [w.POINT], w.HWND)
api(user, "GetAncestor", [w.HWND, w.UINT], w.HWND)
api(user, "GetWindowTextW", [w.HWND, w.LPWSTR, c.c_int], c.c_int)
api(user, "GetClassNameW", [w.HWND, w.LPWSTR, c.c_int], c.c_int)
api(user, "GetWindowThreadProcessId", [w.HWND, c.POINTER(w.DWORD)], w.DWORD)
api(user, "GetClientRect", [w.HWND, c.POINTER(w.RECT)], w.BOOL)
api(user, "ClientToScreen", [w.HWND, c.POINTER(w.POINT)], w.BOOL)
api(user, "GetDpiForWindow", [w.HWND], w.UINT)
api(user, "SetProcessDpiAwarenessContext", [w.HANDLE], w.BOOL)
api(user, "MonitorFromWindow", [w.HWND, w.DWORD], w.HANDLE)
api(user, "SetWindowPos", [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT], w.BOOL)
api(user, "SetWindowDisplayAffinity", [w.HWND, w.DWORD], w.BOOL)
api(user, "GetWindowDisplayAffinity", [w.HWND, c.POINTER(w.DWORD)], w.BOOL)
api(user, "GetWindowLongPtrW", [w.HWND, c.c_int], c.c_ssize_t)
api(user, "SetForegroundWindow", [w.HWND], w.BOOL)
api(user, "RegisterHotKey", [w.HWND, c.c_int, w.UINT, w.UINT], w.BOOL)
api(user, "UnregisterHotKey", [w.HWND, c.c_int], w.BOOL)
api(kernel, "OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE)
api(kernel, "QueryFullProcessImageNameW", [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)], w.BOOL)
api(kernel, "CloseHandle", [w.HANDLE], w.BOOL)

class MonitorInfo(c.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]

api(user, "GetMonitorInfoW", [w.HANDLE, c.POINTER(MonitorInfo)], w.BOOL)

@dataclass(frozen=True)
class Binding:
    hwnd: int
    pid: int
    process: str
    title: str
    class_name: str
    rect: tuple[int, int, int, int]
    monitor: tuple[int, int, int, int]
    dpi: int
    minimized: bool

    @property
    def fullscreen_geometry(self):
        return all(abs(a-b) <= 2 for a, b in zip(self.rect, self.monitor))

    def to_dict(self):
        return {**asdict(self), "fullscreen_geometry": self.fullscreen_geometry}

def enable_dpi():
    # Must happen before any Qt window is created. Failure is recorded, not ignored.
    c.set_last_error(0)
    ok = bool(user.SetProcessDpiAwarenessContext(c.c_void_p(-4)))
    return {"per_monitor_v2_requested": ok, "error": c.get_last_error() if not ok else 0}

def rect_tuple(rect):
    return rect.left, rect.top, rect.right, rect.bottom

def describe(hwnd: int) -> Binding | None:
    if not user.IsWindow(hwnd) or not user.IsWindowVisible(hwnd):
        return None
    pid = w.DWORD()
    user.GetWindowThreadProcessId(hwnd, c.byref(pid))
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    process = ""
    if handle:
        try:
            buf, size = c.create_unicode_buffer(32768), w.DWORD(32768)
            if kernel.QueryFullProcessImageNameW(handle, 0, buf, c.byref(size)):
                process = Path(buf.value).name
        finally:
            kernel.CloseHandle(handle)
    # A title alone is insufficient to bind a potentially unrelated window.
    if not process.lower().startswith(("mumu", "nemu")):
        return None
    title, cls = c.create_unicode_buffer(1024), c.create_unicode_buffer(256)
    user.GetWindowTextW(hwnd, title, len(title))
    user.GetClassNameW(hwnd, cls, len(cls))
    rect = w.RECT()
    if not user.GetClientRect(hwnd, c.byref(rect)):
        return None
    tl, br = w.POINT(rect.left, rect.top), w.POINT(rect.right, rect.bottom)
    if not user.ClientToScreen(hwnd, c.byref(tl)) or not user.ClientToScreen(hwnd, c.byref(br)):
        return None
    mon = MonitorInfo()
    mon.cbSize = c.sizeof(mon)
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), c.byref(mon)):
        return None
    return Binding(int(hwnd), pid.value, process, title.value, cls.value,
                   (tl.x, tl.y, br.x, br.y), rect_tuple(mon.rcMonitor),
                   user.GetDpiForWindow(hwnd), bool(user.IsIconic(hwnd)))

def enumerate_mumu():
    found = []
    @CALLBACK
    def visitor(hwnd, _):
        binding = describe(hwnd)
        # MuMu fullscreen creates a same-size Qt tool window alongside the game.
        if binding and not user.GetWindowLongPtrW(hwnd,-20)&0x80 and binding.rect[2]-binding.rect[0] >= 300 and binding.rect[3]-binding.rect[1] >= 200:
            found.append(binding)
        return True
    user.EnumWindows(visitor, 0)
    return found

def foreground_root():
    hwnd = user.GetForegroundWindow()
    return int(user.GetAncestor(hwnd, 2) or hwnd or 0)

def same_target(original: Binding, current: Binding | None):
    return current is not None and (original.hwnd, original.pid, original.process) == (current.hwnd, current.pid, current.process)

def capture_block_reason(original: Binding, current: Binding | None, foreground: int):
    if not same_target(original, current):
        return "target_changed_or_closed"
    if current.minimized:
        return "minimized"
    if foreground != current.hwnd:
        return "not_foreground"
    if current.rect[2] <= current.rect[0] or current.rect[3] <= current.rect[1]:
        return "empty_rect"
    return None

def grab_once(original: Binding, destination: Path):
    import mss
    from PIL import Image, ImageStat
    before = describe(original.hwnd)
    blocked = capture_block_reason(original, before, foreground_root())
    if blocked:
        raise RuntimeError(blocked)
    left, top, right, bottom = before.rect
    start = time.perf_counter()
    with mss.mss() as screen:
        shot = screen.grab({"left": left, "top": top, "width": right-left, "height": bottom-top})
    elapsed = (time.perf_counter()-start)*1000
    after = describe(original.hwnd)
    blocked = capture_block_reason(original, after, foreground_root())
    if blocked or before.rect != after.rect or before.dpi != after.dpi:
        raise RuntimeError("discarded_frame_after_context_change")
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    stat = ImageStat.Stat(image.resize((256, 144)))
    mean, stddev = stat.mean, stat.stddev
    # This is only a black/solid-frame heuristic, not game scene recognition.
    suspicious = max(mean) < 3 or max(stddev) < 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return {"window": after.to_dict(), "capture_ms": round(elapsed, 2),
            "size": image.size, "rgb_mean": mean, "rgb_stddev": stddev,
            "black_or_solid_suspected": suspicious, "file": str(destination)}

if __name__ == "__main__":
    enable_dpi()
    print(json.dumps([b.to_dict() for b in enumerate_mumu()], ensure_ascii=False, indent=2))
