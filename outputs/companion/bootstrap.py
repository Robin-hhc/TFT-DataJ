"""Read-only application resources and writable per-user state for packaged builds."""
from pathlib import Path
import sys
import os

# Qt probes installed TLS backends even when Schannel is selected. Keep the
# Python runtime's matching DLL pair ahead of unrelated application DLLs.
# This affects this process and its children only, never the system PATH.
tls_dir=Path(sys.base_prefix)/'DLLs'
if (tls_dir/'libssl-3-x64.dll').is_file() and (tls_dir/'libcrypto-3-x64.dll').is_file():
    os.environ['PATH']=str(tls_dir)+os.pathsep+os.environ.get('PATH','')

FROZEN = bool(getattr(sys, 'frozen', False))
RESOURCE_DIR = Path(__file__).resolve().parent
ROOT = Path(sys._MEIPASS) if FROZEN else RESOURCE_DIR.parents[1]
if FROZEN:
    local_app_data = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
    STATE_DIR = local_app_data/'TFT-DataJ'
else:
    sys.path.insert(0, str(ROOT / 'outputs/mumu-p0-probe'))
    STATE_DIR = ROOT / 'work/companion'
STATE_DIR.mkdir(parents=True, exist_ok=True)
