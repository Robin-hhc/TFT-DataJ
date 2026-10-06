"""Explicit Android long-press experiment; capture while the pointer is held.

This tool sends game input when explicitly run. It is not a background sampler,
and Android input does not validate the Windows passive mouse hook.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--x', type=int, required=True)
    parser.add_argument('--y', type=int, required=True)
    parser.add_argument('--duration-ms', type=int, default=2000)
    parser.add_argument('--delay-ms', type=int, default=200)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='explicit native Android long-press screenshot')
    args = parser.parse_args()
    if not args.adb.is_file():
        parser.error('--adb must name the installed adb executable')
    if args.x < 0 or args.y < 0 or not 500 <= args.duration_ms <= 10000:
        parser.error('coordinates must be nonnegative and duration must be 500..10000 ms')
    if not 0 <= args.delay_ms < args.duration_ms:
        parser.error('--delay-ms must be within the hold duration')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    prefix = [str(args.adb), '-s', args.serial]
    command = prefix + ['shell', 'input', 'swipe', str(args.x), str(args.y),
                        str(args.x), str(args.y), str(args.duration_ms)]
    # Root explicitly runs this experiment. Launch input without waiting so the
    # screenshot is requested before Android sends the final pointer release.
    hold = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(args.delay_ms/1000)
    capture_started = time.monotonic()
    try:
        shot = subprocess.run(prefix+['exec-out', 'screencap', '-p'], capture_output=True, timeout=20)
    except (subprocess.TimeoutExpired, OSError) as exc:
        shot = SimpleNamespace(returncode=-1, stdout=b'', stderr=str(exc).encode('utf-8'))
    capture_done = time.monotonic()
    try:
        hold_out, hold_error = hold.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        hold.terminate()
        hold_out, hold_error = hold.communicate(timeout=5)
    valid_png = shot.returncode == 0 and shot.stdout.startswith(b'\x89PNG\r\n\x1a\n')
    size = None
    if valid_png:
        try:
            with Image.open(BytesIO(shot.stdout)) as image:
                size = image.size
                image.verify()
        except (OSError, ValueError, SyntaxError):
            valid_png = False
    if valid_png:
        args.output.write_bytes(shot.stdout)
    metadata = {
        'label': args.label, 'utc_time': timestamp, 'serial': args.serial,
        'source': 'Android native screencap', 'input': 'same-coordinate shell input swipe',
        'point': [args.x, args.y], 'hold_duration_ms': args.duration_ms,
        'capture_request_after_start_ms': round((capture_started-started)*1000, 2),
        'capture_ms': round((capture_done-capture_started)*1000, 2),
        'total_ms': round((time.monotonic()-started)*1000, 2),
        'hold_returncode': hold.returncode, 'capture_returncode': shot.returncode,
        'valid_png': valid_png, 'path': str(args.output.resolve()) if valid_png else None,
        'sha256': hashlib.sha256(shot.stdout).hexdigest() if valid_png else None,
        'png_bytes': len(shot.stdout) if valid_png else 0,
        'size': size,
        'capture_error': shot.stderr.decode('utf-8', 'replace')[:1000],
        'hold_error': hold_error.decode('utf-8', 'replace')[:1000],
        'limits': ['Not a Windows physical mouse event or side-key experiment.',
                   'Screenshot request timing is measured; image frame timing is not asserted.',
                   'A long-press alone does not prove a selected resource.'],
    }
    args.output.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: metadata[key] for key in ('valid_png', 'path', 'hold_returncode', 'capture_ms', 'sha256')}))
    return 0 if valid_png and hold.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
