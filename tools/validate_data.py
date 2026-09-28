"""One offline entrypoint for both source directories and real display replay."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
PRIVATE={'test_user_layout','test_live_failure','test_scene_gate','test_live_choice','test_item_vision'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-private',action='store_true',help='Also run local screenshot/OCR checks; absent files fail explicitly')
    parser.add_argument('--release-gate',action='store_true',help='Also reject live capture coverage gaps')
    parser.add_argument('--report',type=Path,default=ROOT/'work/data-validation/offline.json')
    args=parser.parse_args()
    for path in ['outputs/mumu-p0-probe','outputs/companion']:sys.path.insert(0,str(ROOT/path))
    suite=unittest.TestSuite();excluded=[]
    for folder in ['outputs/companion','outputs/mumu-p0-probe']:
        for file in sorted((ROOT/folder).glob('test_*.py')):
            if file.stem in PRIVATE and not args.include_private:
                excluded.append({'suite':file.stem,'status':'not_run','reason':'Private screenshot/OCR extension; use --include-private'})
            else:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(file.stem))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    from test_display_replay import REPORTS
    cases=[case for r in REPORTS for case in r['cases']]
    gaps=REPORTS[0]['gaps'] if REPORTS else [{'status':'missing_fixture'}]
    failed=not result.wasSuccessful() or bool(result.skipped) or not REPORTS or (args.release_gate and bool(gaps))
    report={'status':'failed' if failed else 'passed','tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
            'skipped':[{'test':str(t),'reason':reason} for t,reason in result.skipped],
            'extensions':excluded,'display_cases':cases,'display_summary':dict(Counter(r['domain']+':'+r['status'] for r in cases)),
            'source_gaps':gaps,'reference':'API + verified website display rules; not website DOM comparison',
            'source_revision':None}
    import subprocess
    report['source_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ['status','tests','display_summary']},ensure_ascii=False))
    print('Report:',args.report)
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
