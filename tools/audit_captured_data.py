"""Compare a bounded live-capture directory with the actual application UI.

Writes a new candidate and report under work/. Never accepts golden changes.
Run collect_display_fixtures.py separately for each explicit batch.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
from build_display_golden import propose

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.resolve().is_relative_to((ROOT/'outputs/companion/fixtures').resolve()):p.error('Cannot replace accepted fixtures')
    if args.output.exists():p.error('Choose a new output directory; evidence is immutable')
    args.output.mkdir(parents=True);candidate=args.output/'candidate.json.gz'
    candidate.write_bytes(gzip.compress(json.dumps(propose(args.capture),ensure_ascii=False).encode(),mtime=0))
    sys.path.insert(0,str(ROOT/'outputs/companion'))
    from display_audit import run
    report=run(candidate)
    report['status']='mismatch' if report['failed'] else 'source_unavailable' if report['gaps'] or report['not_verified'] else 'pass'
    report['evidence']='Captured API response + independently frozen display rules; no website DOM equality claim'
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ['status','passed','failed']},ensure_ascii=False))
    return int(report['status']!='pass')


if __name__=='__main__':raise SystemExit(main())
