from pathlib import Path
from datetime import datetime
import sys
import traceback
import faulthandler
from bootstrap import STATE_DIR

log=(STATE_DIR/("run-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".log")).open("a",encoding="utf-8")
sys.stdout=log
sys.stderr=log
faulthandler.enable(file=log, all_threads=True)
try:
    from app import main
    raise SystemExit(main())
except Exception:
    traceback.print_exc()
    log.flush()
    raise
finally:
    log.close()
