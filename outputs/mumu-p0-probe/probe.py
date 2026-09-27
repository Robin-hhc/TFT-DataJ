"""Disposable P0 tool, not the Companion product. Local-only, explicit snapshots.

Ctrl+Alt+F9 panel; Ctrl+Alt+F10 snapshot; Ctrl+Alt+F12 quit.
No game clicks, key injection, recommendation values, or persistent recording.
"""
from __future__ import annotations
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import win_capture as win

ROOT = Path(__file__).resolve().parents[2]

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-foreground", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=45)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    dpi_status = win.enable_dpi()
    run_dir = ROOT / "work" / "p0-runs" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir.mkdir(parents=True)
    if args.capture_foreground:
        # Wait for a user-selected MuMu device window; never activate the game.
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            target = win.describe(win.foreground_root())
            if target and target.process.lower() == "mumunxdevice.exe":
                result = win.grab_once(target, run_dir / "game.png")
                result["dpi_setup"] = dpi_status
                write_json(run_dir / "capture.json", result)
                print(json.dumps(result, ensure_ascii=False))
                return 0
            time.sleep(0.25)
        print(json.dumps({"status": "no_foreground_mumu_device", "wait_seconds": args.wait_seconds}))
        return 2

    from PySide6.QtCore import Qt, QTimer, QAbstractNativeEventFilter
    from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QComboBox, QVBoxLayout, QHBoxLayout

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    log = open(run_dir / "events.jsonl", "a", encoding="utf-8")
    def record(event, **data):
        log.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **data}, ensure_ascii=False)+"\n")
        log.flush()

    class Overlay(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                             Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                             Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel("MuMu 浮层测试 · 不显示推荐\nCtrl+Alt+F9 面板   F10 截图   F12 退出\n三个快捷键均需同时按 Ctrl+Alt")
            label.setStyleSheet("background:rgba(18,26,39,215);color:#bce8ff;padding:10px;border:1px solid #5da9ca;border-radius:8px;font-size:12px")
            layout.addWidget(label)
            self.adjustSize()
            self.handle = int(self.winId())
            c.set_last_error(0)
            affinity_ok = bool(win.user.SetWindowDisplayAffinity(self.handle, 0x11))
            affinity_set_error = c.get_last_error() if not affinity_ok else 0
            actual = w.DWORD()
            c.set_last_error(0)
            affinity_read = bool(win.user.GetWindowDisplayAffinity(self.handle, c.byref(actual)))
            affinity_read_error = c.get_last_error() if not affinity_read else 0
            self.excluded = affinity_ok and affinity_read and actual.value == 0x11
            record("overlay_created", excluded_from_capture=self.excluded,
                   affinity_set=affinity_ok, affinity_read=affinity_read, affinity_value=actual.value,
                   affinity_set_error=affinity_set_error, affinity_read_error=affinity_read_error,
                   style=hex(win.user.GetWindowLongPtrW(self.handle, -20)))

        def place(self, binding):
            left, top, right, bottom = binding.rect
            self.show()
            # Physical client coordinates from Win32; no Qt logical/physical mixing.
            scale = binding.dpi / 96
            width, height = round(self.width()*scale), round(self.height()*scale)
            win.user.SetWindowPos(self.handle, c.c_void_p(-1), left+round(16*scale),
                                 top+round(60*scale), min(width, right-left), height, 0x10 | 0x40)
            point = w.POINT(left+round(40*scale), top+round(80*scale))
            hit = win.user.WindowFromPoint(point)
            record("overlay_hit_probe", hit_root=int(win.user.GetAncestor(hit, 2) or hit or 0),
                   target=binding.hwnd, foreground=win.foreground_root(),
                   note="OS point lookup only; actual user click still needs confirmation")

    class Panel(QWidget):
        def __init__(self):
            super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowTitle("DataJ Companion · MuMu 验证")
            self.resize(510, 330)
            self.binding = None
            self.previous_state = None
            self.last_geometry = None
            self.pending_capture = False
            self.overlay = Overlay()
            self.target = QComboBox()
            self.status = QLabel("请选择实际游戏窗口；测试不会点击或操作游戏。")
            self.status.setWordWrap(True)
            self.details = QLabel()
            self.details.setWordWrap(True)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("① 选 MuMu 游戏窗口 → ② 收起面板 → ③ 手动验证浮层"))
            layout.addWidget(self.target)
            refresh = QPushButton("刷新窗口列表")
            bind = QPushButton("绑定并收起")
            capture = QPushButton("收起并保存一张截图")
            hide = QPushButton("收起，返回游戏")
            quit_button = QPushButton("结束测试")
            for button in (refresh, bind, capture, hide, quit_button):
                layout.addWidget(button)
            layout.addWidget(self.status)
            layout.addWidget(self.details)
            layout.addWidget(QLabel("Ctrl+Alt+F9 面板 · Ctrl+Alt+F10 截图 · Ctrl+Alt+F12 退出\n浮层失焦即隐藏；测试默认 5 分钟后自动退出。"))
            refresh.clicked.connect(self.refresh)
            bind.clicked.connect(self.bind_selected)
            capture.clicked.connect(self.capture_from_panel)
            hide.clicked.connect(self.return_to_game)
            quit_button.clicked.connect(app.quit)
            self.refresh()
            current = win.describe(win.foreground_root())
            if current and current.process.lower() == "mumunxdevice.exe":
                self.binding = current
                record("bound_foreground_device", window=current.to_dict())
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.tick)
            self.timer.start(150)

        def refresh(self):
            self.target.clear()
            # MuMu creates shadow/tool windows. Present only its normal top-level windows.
            for item in win.enumerate_mumu():
                if "QWindowTool" not in item.class_name:
                    self.target.addItem(f"{item.title} · {item.rect[2]-item.rect[0]}×{item.rect[3]-item.rect[1]} · {item.process}", item)

        def bind_selected(self):
            item = self.target.currentData()
            current = win.describe(item.hwnd) if item else None
            if not item or not win.same_target(item, current):
                self.status.setText("窗口已变化，请刷新列表后选择。")
                return
            self.binding = current
            record("bound_by_user", window=current.to_dict())
            self.return_to_game()

        def return_to_game(self):
            self.hide()
            if self.binding:
                now = win.describe(self.binding.hwnd)
                if win.same_target(self.binding, now) and not now.minimized:
                    ok = bool(win.user.SetForegroundWindow(now.hwnd))
                    record("focus_restore_requested", accepted=ok)
                    QTimer.singleShot(300, lambda: record("focus_restore_observed", foreground=win.foreground_root(), target=now.hwnd))

        def closeEvent(self, event):
            event.ignore()
            self.return_to_game()

        def toggle(self):
            if self.isVisible():
                self.return_to_game()
            else:
                self.overlay.hide()
                self.show()
                self.raise_()
                self.activateWindow()
                record("panel_opened")

        def capture_from_panel(self):
            self.return_to_game()
            QTimer.singleShot(500, self.snapshot)

        def snapshot(self):
            if not self.binding or self.pending_capture:
                record("capture_rejected", reason="no_binding_or_busy")
                return
            # If capture exclusion was rejected, hide overlay before snapshot.
            self.pending_capture = True
            if not self.overlay.excluded:
                self.overlay.hide()
                QTimer.singleShot(200, self.finish_snapshot)
            else:
                self.finish_snapshot()

        def finish_snapshot(self):
            try:
                result = win.grab_once(self.binding, run_dir / f"game-{time.time_ns()}.png")
                self.status.setText(f"已保存一张 {result['size'][0]}×{result['size'][1]} 截图；耗时 {result['capture_ms']} ms。")
                record("capture", **result)
            except Exception as exc:
                record("capture_rejected", reason=str(exc))
                self.status.setText("截图未保存："+str(exc))
            finally:
                self.pending_capture = False
                self.previous_state = None

        def tick(self):
            if self.pending_capture:
                return
            current = win.describe(self.binding.hwnd) if self.binding else None
            reason = win.capture_block_reason(self.binding, current, win.foreground_root()) if self.binding else "no_binding"
            if self.isVisible():
                reason = "panel_open"
            geometry = (current.rect, current.dpi) if current else None
            state = reason or "overlay_visible"
            if state != self.previous_state or geometry != self.last_geometry:
                record("state", state=state, window=current.to_dict() if current else None)
                self.previous_state, self.last_geometry = state, geometry
                if reason:
                    self.overlay.hide()
                else:
                    self.overlay.place(current)
                if current:
                    self.details.setText(f"{current.title} · DPI {current.dpi}\n画面 {current.rect} · 全屏几何：{current.fullscreen_geometry}\n状态：{state} · 浮层截图排除：{self.overlay.excluded}")

    panel = Panel()
    registered = []

    class Hotkeys(QAbstractNativeEventFilter):
        def nativeEventFilter(self, event_type, message):
            msg = w.MSG.from_address(int(message))
            if msg.message == 0x312:
                action = {1: panel.toggle, 2: panel.snapshot, 3: app.quit}.get(int(msg.wParam))
                if action:
                    record("hotkey", id=int(msg.wParam))
                    action()
                    return True, 0
            return False, 0

    native_filter = Hotkeys()
    app.installNativeEventFilter(native_filter)
    for id_, vk in ((1, 0x78), (2, 0x79), (3, 0x7B)):
        ok = bool(win.user.RegisterHotKey(None, id_, 0x4000 | 0x1 | 0x2, vk))
        record("hotkey_registration", id=id_, success=ok, error=c.get_last_error() if not ok else 0)
        if ok:
            registered.append(id_)
    if len(registered) != 3:
        panel.status.setText("有快捷键被占用；可使用面板按钮，本次测试会自动退出。")
        panel.show()
    elif not panel.binding and not args.self_test:
        panel.show()
    record("started", dpi_setup=dpi_status, run_dir=str(run_dir), auto_exit_seconds=args.seconds)

    if args.self_test:
        panel.timer.stop()
        panel.hide()
        assert panel.overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        assert panel.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert panel.overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        record("self_test_passed", note="Flags and construction only; no game interaction asserted")
        QTimer.singleShot(200, app.quit)
    else:
        QTimer.singleShot(max(10, args.seconds)*1000, app.quit)

    def cleanup():
        panel.timer.stop()
        panel.overlay.hide()
        for id_ in registered:
            win.user.UnregisterHotKey(None, id_)
        record("stopped")
        log.close()
    app.aboutToQuit.connect(cleanup)
    print(json.dumps({"run_dir": str(run_dir), "binding": panel.binding.to_dict() if panel.binding else None}, ensure_ascii=False), flush=True)
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
