"""Windowless entry point with persistent diagnostics and a visible startup error."""
from datetime import datetime
import sys
import traceback
import faulthandler


def main():
    log=None
    try:
        from bootstrap import STATE_DIR
        log=(STATE_DIR/("run-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".log")).open("a",encoding="utf-8")
        sys.stdout=log;sys.stderr=log
        faulthandler.enable(file=log,all_threads=True)
        if '--diagnose' in sys.argv:
            from portable_check import main as run
        else:
            from app import main as run
        return run()
    except Exception:
        traceback.print_exc()
        if log:log.flush()
        if '--diagnose' not in sys.argv:
            import ctypes
            location=str(log.name) if log else '无法创建日志，请检查用户目录的写入权限。'
            ctypes.windll.user32.MessageBoxW(None,
                '助手启动失败。请保留整个解压文件夹，不要单独移动EXE。\n\n日志：'+location,
                '金铲铲 DataJ Companion',0x10)
        return 1
    finally:
        if log:
            faulthandler.disable();log.flush()


if __name__=='__main__':raise SystemExit(main())
