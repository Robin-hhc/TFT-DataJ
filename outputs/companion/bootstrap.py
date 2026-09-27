"""Local workspace layout; shared P0 capture/OCR primitives remain versioned beside us."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/mumu-p0-probe'))
STATE_DIR = ROOT / 'work/companion'
STATE_DIR.mkdir(parents=True, exist_ok=True)
