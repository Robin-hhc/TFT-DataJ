"""Replay labelled, original screenshots without controlling or capturing a game."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'outputs/companion'))
from PIL import Image
from condition_reader import ConditionReader
from entity_identity import EntityResolver
from vision import Vision


def percentile95(values):
    if not values:
        return None
    return round(sorted(values)[min(len(values)-1, int(len(values)*.95))], 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'work/condition-input-experiment/manifest.json')
    parser.add_argument('--report', type=Path, default=ROOT/'work/condition-input-experiment/report.json')
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 10:
        parser.error('--rounds must be between 1 and 10')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    catalog_path = Path(manifest['catalogue'])
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    vision = Vision()
    started = time.perf_counter()
    vision.prepare()
    prepare_ms = (time.perf_counter()-started)*1000
    started = time.perf_counter()
    reader = ConditionReader(vision, EntityResolver(catalog))
    resolver_ms = (time.perf_counter()-started)*1000
    cases = []
    all_times, positive_times = [], []
    for sample in manifest['samples']:
        path = Path(sample['path'])
        if not path.exists():
            cases.append({'sample': sample, 'passed': False, 'failure': 'missing original fixture'})
            continue
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if sample.get('sha256') and sample['sha256'] != sha256:
            cases.append({'sample': sample, 'passed': False, 'failure': 'fixture SHA-256 changed'})
            continue
        with Image.open(path) as source:
            image = source.convert('RGB')
        options = sample.get('options', {})
        cold = reader.read(image, **options)
        elapsed = []
        for _ in range(args.rounds):
            started = time.perf_counter()
            result = reader.read(image, **options)
            elapsed.append((time.perf_counter()-started)*1000)
        all_times.extend(elapsed)
        if sample.get('expected_id'):
            positive_times.extend(elapsed)
        expected_id = sample.get('expected_id')
        actual_id = result['entity']['id'] if result.get('entity') else None
        valid = actual_id == expected_id
        if 'expected_status' in sample:
            valid &= result['status'] == sample['expected_status']
        if 'allowed_routes' in sample:
            valid &= result['route'] in sample['allowed_routes']
        valid &= result['records_selected'] is False
        cases.append({'sample': sample, 'sha256': sha256, 'size': image.size,
                      'passed': bool(valid), 'first_read_ms': cold['elapsed_ms'],
                      'warm_read_ms': [round(value, 2) for value in elapsed], 'result': result})
    passed = sum(case['passed'] for case in cases)
    report = {
        'claim': 'Offline primary-title/route replay only; no side-key/capture/FPS/accepted-click claim',
        'catalogue': str(catalog_path),
        'catalogue_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        'vision_prepare_ms': round(prepare_ms, 2),
        'resolver_prepare_ms': round(resolver_ms, 2),
        'cases_passed': passed, 'cases_total': len(cases),
        'warm_primary_title_p95_ms': percentile95(positive_times),
        'warm_all_routes_p95_ms': percentile95(all_times),
        'event_group_count': len({sample.get('event_group') for sample in manifest['samples']}),
        'limits': manifest.get('limits', []), 'cases': cases,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Primary-title replay: {passed}/{len(cases)}; warm positive P95 {report['warm_primary_title_p95_ms']} ms")
    print(args.report)
    return 0 if passed == len(cases) else 1


if __name__ == '__main__':
    raise SystemExit(main())
