"""Local workspace layout; shared P0 capture/OCR primitives remain versioned beside us."""
from pathlib import Path
import sys
import os

# Qt probes installed TLS backends even when Schannel is selected. Keep the
# Python runtime's matching DLL pair ahead of unrelated application DLLs.
# This affects this process and its children only, never the system PATH.
tls_dir=Path(sys.base_prefix)/'DLLs'
if (tls_dir/'libssl-3-x64.dll').is_file() and (tls_dir/'libcrypto-3-x64.dll').is_file():
    os.environ['PATH']=str(tls_dir)+os.pathsep+os.environ.get('PATH','')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/mumu-p0-probe'))
STATE_DIR = ROOT / 'work/companion'
STATE_DIR.mkdir(parents=True, exist_ok=True)
