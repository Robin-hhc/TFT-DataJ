"""Exercise the real pythonw launch environment with a hidden Qt portrait request."""
import json,subprocess,sys,time,os
from pathlib import Path

if '--child' in sys.argv:
    from bootstrap import STATE_DIR
    from PySide6.QtWidgets import QApplication,QWidget
    from PySide6.QtNetwork import QSslSocket
    from comp_browser import Portraits
    qt=QApplication([]);parent=QWidget();store=Portraits(parent)
    assert QSslSocket.activeBackend()=='schannel'
    store.request('https://img.dataj.cc/images/s18/hero/s18_head_sivir.png')
    end=time.monotonic()+12
    while (store.active or store.queue) and time.monotonic()<end:
        qt.processEvents();time.sleep(.01)
    assert len(store.images)==1,'Portrait HTTPS request did not complete'
    (STATE_DIR/'tls-startup-result.json').write_text(json.dumps({'pythonw':'passed','portrait_https':'passed','backend':QSslSocket.activeBackend()}))
else:
    # Inherit caller PATH, including the conflicting Poppler directory if present.
    original_env=os.environ.copy()
    from bootstrap import STATE_DIR
    result=STATE_DIR/'tls-startup-result.json'
    before=result.stat().st_mtime if result.exists() else 0
    subprocess.run([str(Path(sys.executable).with_name('pythonw.exe')),str(Path(__file__).resolve()),'--child'],timeout=20,check=True,env=original_env)
    assert result.exists() and result.stat().st_mtime>before
    print(result.read_text())
