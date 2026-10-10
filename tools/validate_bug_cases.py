"""List unreviewed screenshots; optionally replay independently reviewed originals.

The default command never initializes OCR. A reviewer must create expected.json
beside frame.png, with schema_version, image_sha256, set_id, patch, scene,
cards=[{"slot": 0, "id": "1625"}, ...], reviewed_by and review_note. Hex
oracles also require round ("2-1" or null). Condition-detail oracles require
kind (hex/equip/hero or null) and one slot; unknown condition scenes have no
cards and kind=null. An explicit null card ID means the identity must be
rejected. Observed output is never used as an expected answer.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import sys
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CASE_NAME = re.compile(r'case-[0-9a-f]{16,64}')
SHA256 = re.compile(r'[0-9a-f]{64}')
ROUND = re.compile(r'[1-9]-[1-9]')
SCENES = {'hex': {'unknown', 'choice_candidates', 'choice_unresolved'},
          'item': {'unknown', 'item_candidates'},
          'condition': {'unknown', 'condition_detail'}}
CONDITION_KINDS = frozenset(('hex', 'equip', 'hero'))


class InvalidCase(ValueError):
    pass


def _no_links(path):
    """Reject links/junctions before reading any archive or report component."""
    for part in (path, *path.parents):
        try:
            details = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(details.st_mode)
                or getattr(details, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise InvalidCase(f'symlink/reparse path is not allowed: {part.name}')


def _read(path):
    _no_links(path)
    if not path.is_file():
        raise InvalidCase(f'missing artifact: {path.name}')
    return path.read_bytes()


def _json_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise InvalidCase(f'duplicate JSON key: {key}')
        output[key] = value
    return output


def _load_json(path):
    try:
        value = json.loads(_read(path).decode('utf-8'), object_pairs_hook=_json_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InvalidCase(f'invalid JSON: {path.name}: {error}') from error
    if not isinstance(value, dict):
        raise InvalidCase(f'{path.name} must be a JSON object')
    return value


def _require(condition, reason):
    if not condition:
        raise InvalidCase(reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _version(value, label):
    _require(type(value) is int and value == 1, f'unsupported {label} schema_version')


def _manifest(case_dir):
    _require(CASE_NAME.fullmatch(case_dir.name), 'invalid case directory name')
    _no_links(case_dir)
    _require(case_dir.is_dir(), 'case artifact must be a directory')
    case = _load_json(case_dir/'case.json')
    _version(case.get('schema_version'), 'case')
    _require(case.get('status') == 'pending_review', 'case status must be pending_review')
    if 'case_id' in case:
        _require(case['case_id'] in (case_dir.name, case_dir.name[5:]), 'case_id differs from directory')
    for key in ('created_at', 'reason'):
        _require(_text(case.get(key)), f'case requires {key}')
    context = case.get('context')
    _require(isinstance(context, dict), 'missing case context')
    _require(all(key in context for key in ('set_id', 'patch', 'target')), 'incomplete version/target context')
    _require(isinstance(context.get('domain'), str) and context['domain'] in SCENES, 'unknown case domain')
    _require(context.get('source') == 'bound_game', 'case source must be bound_game')
    _require(isinstance(case.get('observation'), dict), 'missing recorded observation')
    evidence = case.get('evidence')
    _require(isinstance(evidence, dict) and isinstance(evidence.get('catalog'), dict), 'missing recorded catalog')
    keys = {'hex': ('hex',), 'item': ('equip',),
            'condition': ('hex', 'equip', 'hero', 'trait')}[context['domain']]
    for key in keys:
        catalog = evidence['catalog'].get(key)
        _require(isinstance(catalog, list) and all(isinstance(row, dict) for row in catalog), f'missing catalog.{key} rows')
    metadata = case.get('image')
    _require(isinstance(metadata, dict), 'missing image metadata')
    _require(metadata.get('filename') == 'frame.png', 'image filename must be frame.png')
    _require(isinstance(metadata.get('sha256'), str) and SHA256.fullmatch(metadata['sha256']), 'invalid image SHA-256')
    _require(all(type(metadata.get(key)) is int and metadata[key] > 0 for key in ('width', 'height')), 'invalid image dimensions')
    raw = _read(case_dir/'frame.png')
    digest = hashlib.sha256(raw).hexdigest()
    _require(digest == metadata['sha256'], 'original frame SHA-256 differs from manifest')
    try:
        with Image.open(BytesIO(raw)) as source:
            _require(source.format == 'PNG', 'frame.png is not PNG data')
            _require(source.size == (metadata['width'], metadata['height']), 'image dimensions differ from manifest')
            source.load()
            image = source.convert('RGB')
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise InvalidCase(f'invalid original image: {error}') from error
    return case, image, digest


def _expected(case_dir, case, digest):
    path = case_dir/'expected.json'
    _no_links(path)
    if not path.exists():
        return None
    expected = _load_json(path)
    _version(expected.get('schema_version'), 'expected')
    context = case['context']
    domain = context['domain']
    fields = {'schema_version', 'image_sha256', 'set_id', 'patch', 'scene',
              'cards', 'reviewed_by', 'review_note'}
    if domain == 'hex':
        fields.add('round')
    elif domain == 'condition':
        fields.add('kind')
    _require(not set(expected)-fields,
             'unsupported expected fields; only scene, hex round, detail kind and identity are supported; statistics and rankings are not validated')
    _require(expected.get('image_sha256') == digest, 'expected image SHA-256 differs from original')
    for key in ('set_id', 'patch'):
        _require(key in expected and type(expected[key]) is type(context[key])
                 and expected[key] == context[key], f'expected {key} differs from case context')
    for key in ('reviewed_by', 'review_note'):
        _require(_text(expected.get(key)), f'expected requires nonempty {key}')
    scene = expected.get('scene')
    _require(isinstance(scene, str) and scene in SCENES[domain], 'unknown or wrong-domain expected scene')
    if domain == 'hex':
        _require('round' in expected and (expected['round'] is None
                 or isinstance(expected['round'], str) and ROUND.fullmatch(expected['round'])), 'invalid or missing expected round')
    cards = expected.get('cards')
    _require(isinstance(cards, list), 'expected cards must be a list')
    for card in cards:
        _require(isinstance(card, dict) and type(card.get('slot')) is int and card['slot'] >= 0
                 and 'id' in card and (card['id'] is None or _text(card['id'])), 'invalid expected card')
        _require(not set(card)-{'slot', 'id'},
                 'unsupported expected card fields; only slot/id are supported; statistics and rankings are not validated')
    slots = [card['slot'] for card in cards]
    _require(sorted(slots) == list(range(len(cards))), 'expected slots must be unique, complete and start at zero')
    if domain == 'condition':
        _require('kind' in expected and (expected['kind'] is None
                 or isinstance(expected['kind'], str) and expected['kind'] in CONDITION_KINDS),
                 'expected condition requires kind hex/equip/hero or null')
        if scene == 'unknown':
            _require(not cards and expected['kind'] is None, 'unknown condition requires empty cards and kind null')
        else:
            _require(len(cards) == 1, 'condition_detail requires exactly slot zero')
            _require((cards[0]['id'] is None) == (expected['kind'] is None),
                     'condition ID and kind must both be confirmed or both null')
        return expected
    complete = len(cards) == 3 if domain == 'hex' else 3 <= len(cards) <= 5
    _require(complete or scene == 'unknown' and not cards, 'incomplete expected card row')
    confirmed = sum(card['id'] is not None for card in cards)
    if scene == 'choice_candidates':
        _require(confirmed >= 1, 'choice_candidates requires a confirmed identity')
    if scene == 'choice_unresolved':
        _require(confirmed == 0, 'choice_unresolved cannot contain confirmed identities')
    if scene == 'item_candidates':
        _require(confirmed >= 2, 'item_candidates requires two confirmed identities')
    return expected


def _make_runner():
    """Import the local model only when an intact, reviewed case is replayed."""
    sys.path.insert(0, str(ROOT/'outputs/companion'))
    from vision import Vision
    from item_vision import analyze_items
    vision = Vision()

    def run(image, case):
        catalog = case['evidence']['catalog']
        if case['context']['domain'] == 'hex':
            return vision.analyze_fast(image, catalog['hex'])
        if case['context']['domain'] == 'condition':
            from condition_reader import ConditionReader
            from entity_identity import EntityResolver
            resolver = EntityResolver(catalog, set_id=case['context']['set_id'])
            return ConditionReader(vision, resolver).read(image)
        return analyze_items(image, vision, catalog['equip'])
    return run


def _condition_actual(observation):
    scene = observation.get('scene')
    _require(isinstance(scene, str) and scene in (SCENES['condition'] | {'augment_choice', 'equipment_choice'}),
             'runner returned unknown condition scene')
    status = observation.get('status')
    _require(_text(status), 'runner returned no condition status')
    kind, identity = None, None
    if status == 'resolved':
        entity = observation.get('entity')
        _require(scene == 'condition_detail' and isinstance(entity, dict), 'resolved condition has no detail entity')
        kind, identity = entity.get('kind'), entity.get('id')
        _require(isinstance(kind, str) and kind in CONDITION_KINDS and _text(identity),
                 'resolved condition has invalid kind or ID')
    # Selection scenes are valid refusals to read a primary detail title. Their
    # route/reason remain diagnostic and never stand in for a reviewed identity.
    scene = 'condition_detail' if scene == 'condition_detail' else 'unknown'
    return {'scene': scene, 'kind': kind,
            'cards': [{'slot': 0, 'id': identity}] if scene == 'condition_detail' else [],
            'route': observation.get('route'), 'reason': observation.get('reason')}


def _actual(observation, domain):
    _require(isinstance(observation, dict), 'runner returned no observation')
    if domain == 'condition':
        return _condition_actual(observation)
    scene = observation.get('scene')
    _require(isinstance(scene, str) and scene in SCENES[domain], 'runner returned unknown or wrong-domain scene')
    cards = observation.get('cards')
    _require(isinstance(cards, list), 'runner returned no cards list')
    output = []
    for card in cards:
        _require(isinstance(card, dict) and type(card.get('slot')) is int and card['slot'] >= 0,
                 'runner returned invalid card slot')
        resolution = card.get('resolution')
        _require(isinstance(resolution, dict) and _text(resolution.get('status')), 'runner returned invalid resolution')
        value = resolution.get('id') if resolution['status'] == 'resolved' else None
        _require(resolution['status'] != 'resolved' or _text(value), 'resolved identity has no ID')
        output.append({'slot': card['slot'], 'id': value})
    slots = [card['slot'] for card in output]
    _require(len(slots) == len(set(slots)), 'runner returned duplicate card slots')
    result = {'scene': scene, 'cards': sorted(output, key=lambda card: card['slot'])}
    if domain == 'hex':
        result['round'] = observation.get('round')
    return result


def validate_cases(cases_root, *, run_reviewed=False, runner=None):
    """Inspect archives and optionally replay; runner(image, manifest) is injectable."""
    folder = Path(cases_root).absolute()
    summary = dict.fromkeys(('total', 'pending_review', 'reviewed', 'invalid', 'passed', 'failed', 'skipped'), 0)
    report = {'schema_version': 1, 'kind': 'bug_case_identity_replay',
              'mode': 'run_reviewed' if run_reviewed else 'inventory', 'cases_root': str(folder),
              'limits': ['Offline scene, card/detail identity, detail kind and hex round validation only; statistics and rankings are not validated.',
                         'Unreviewed screenshots provide evidence, never expected answers.'],
              'summary': summary, 'cases': []}
    try:
        _no_links(folder)
        _require(not folder.exists() or folder.is_dir(), 'cases root must be a directory')
        entries = sorted(folder.iterdir(), key=lambda path: path.name) if folder.exists() else []
    except (OSError, InvalidCase) as error:
        entries = []
        summary['invalid'] += 1
        report['cases'].append({'case_id': None, 'state': 'invalid', 'result': 'invalid', 'reason': str(error)})
    for case_dir in entries:
        if not case_dir.name.startswith('case-'):
            continue
        summary['total'] += 1
        record = {'case_id': case_dir.name, 'state': 'invalid', 'result': 'invalid'}
        report['cases'].append(record)
        try:
            case, image, digest = _manifest(case_dir)
            record.update(context=case['context'], reason=case['reason'], image_sha256=digest)
            expected = _expected(case_dir, case, digest)
        except (OSError, InvalidCase) as error:
            summary['invalid'] += 1
            record['reason'] = str(error)
            continue
        if expected is None:
            summary['pending_review'] += 1
            record.update(state='pending_review', result='pending_review')
            continue
        summary['reviewed'] += 1
        record.update(state='reviewed', reviewed_by=expected['reviewed_by'], result='not_run')
        if not run_reviewed:
            summary['skipped'] += 1
            continue
        try:
            if runner is None:
                runner = _make_runner()
            actual = _actual(runner(image, case), case['context']['domain'])
            gold = {'scene': expected['scene'], 'cards': sorted(expected['cards'], key=lambda card: card['slot'])}
            if case['context']['domain'] == 'hex':
                gold['round'] = expected['round']
            elif case['context']['domain'] == 'condition':
                gold['kind'] = expected['kind']
            failures = [key for key in gold if actual[key] != gold[key]]
            record.update(actual=actual, expected=gold, failures=failures, result='failed' if failures else 'passed')
        except Exception as error:
            record.update(result='failed', reason=f'replay error: {type(error).__name__}: {error}')
        summary[record['result']] += 1
    report['status'] = ('failed' if summary['failed'] else 'invalid' if summary['invalid']
                        else 'pending_review' if summary['pending_review'] else 'not_run' if summary['skipped']
                        else 'passed' if summary['passed'] else 'no_cases')
    return report


def exit_code(report):
    baseline = report.get('review_baseline')
    return int(bool(report['summary']['failed'] or report['summary']['invalid']
                    or baseline is not None and exit_code(baseline)))


def validate_report_path(path, cases_root):
    """Return a safe absolute destination outside the immutable case archive."""
    destination = Path(path).absolute()
    folder = Path(cases_root).absolute()
    _no_links(destination)
    _no_links(folder)
    _require(not destination.resolve().is_relative_to(folder.resolve()),
             '--report must be outside the case archive; samples are immutable')
    _require(not destination.exists() or destination.is_file(), 'report destination must be a regular file')
    return destination


def write_report(report, path, cases_root):
    """Atomically replace an external report without modifying linked samples."""
    destination = validate_report_path(path, cases_root)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_report_path(destination, cases_root)
    temporary = None
    try:
        # Replacing an external hard link must not overwrite an archive inode.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix=destination.name+'.', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def _review_baseline_payload(cases_root, baseline_path):
    """Load public hashes only; private originals are deliberately not read."""
    destination = validate_report_path(baseline_path, cases_root)
    baseline = _load_json(destination)
    _version(baseline.get('schema_version'), 'review baseline')
    _require(set(baseline) == {'schema_version', 'cases'}, 'unsupported review baseline fields')
    entries = baseline.get('cases')
    _require(isinstance(entries, list), 'review baseline cases must be a list')
    seen = set()
    fields = {'case_id', 'image_sha256', 'case_sha256', 'expected_sha256'}
    for entry in entries:
        _require(isinstance(entry, dict) and set(entry) == fields, 'invalid review baseline entry fields')
        case_id = entry['case_id']
        _require(isinstance(case_id, str) and CASE_NAME.fullmatch(case_id), 'invalid review baseline case ID')
        _require(case_id not in seen, 'duplicate review baseline case ID')
        seen.add(case_id)
        for key in fields - {'case_id'}:
            _require(isinstance(entry[key], str) and SHA256.fullmatch(entry[key]),
                     f'invalid review baseline {key}')
    return baseline


def _reviewed_case_entry(cases_root, case_id):
    """Read an existing independent oracle; never derive one from observation."""
    _require(isinstance(case_id, str) and CASE_NAME.fullmatch(case_id), 'invalid reviewed case ID')
    folder = Path(cases_root).absolute()
    _no_links(folder)
    case_dir = folder / case_id
    artifacts = {'image_sha256': 'frame.png', 'case_sha256': 'case.json',
                 'expected_sha256': 'expected.json'}
    hashes = {key: hashlib.sha256(_read(case_dir / filename)).hexdigest()
              for key, filename in artifacts.items()}
    case, _, digest = _manifest(case_dir)
    _require(_expected(case_dir, case, digest) is not None, 'approved case requires existing expected.json')
    for key, filename in artifacts.items():
        _require(hashes[key] == hashlib.sha256(_read(case_dir / filename)).hexdigest(),
                 f'{filename} changed while validating reviewed evidence')
    return {'case_id': case_id, **hashes}


def validate_review_baseline(cases_root, baseline_path, *, verify_files=False):
    """Require accepted evidence without inventing or silently dropping oracles.

    Public mode checks only the hash-index schema. Explicit private mode also
    checks every approved original and oracle; new pending captures do not join
    the baseline automatically. This verifies integrity, not OCR correctness.
    """
    summary = dict.fromkeys(('required', 'verified', 'failed', 'invalid', 'not_run'), 0)
    report = {'schema_version': 1, 'kind': 'reviewed_bug_case_baseline',
              'mode': 'verify_files' if verify_files else 'schema_only',
              'baseline_path': str(Path(baseline_path).absolute()),
              'cases_root': str(Path(cases_root).absolute()), 'summary': summary, 'cases': [],
              'limits': ['Hash integrity and existing oracle validity only; no OCR or statistics are replayed.',
                         'Schema-only checks do not verify private files; newly unreviewed cases remain pending.']}
    try:
        baseline = _review_baseline_payload(cases_root, baseline_path)
    except (OSError, InvalidCase) as error:
        summary['invalid'] = 1
        report.update(status='invalid', reason=str(error))
        return report
    summary['required'] = len(baseline['cases'])
    for entry in baseline['cases']:
        record = {'case_id': entry['case_id'], 'result': 'not_run'}
        report['cases'].append(record)
        if not verify_files:
            summary['not_run'] += 1
            continue
        try:
            case_dir = Path(cases_root).absolute() / entry['case_id']
            for key, filename in (('image_sha256', 'frame.png'), ('case_sha256', 'case.json'),
                                  ('expected_sha256', 'expected.json')):
                actual = hashlib.sha256(_read(case_dir / filename)).hexdigest()
                _require(actual == entry[key], f'approved {filename} SHA-256 differs from review baseline')
            actual = _reviewed_case_entry(cases_root, entry['case_id'])
            _require(actual == entry, 'approved evidence changed while validating review baseline')
            record['result'] = 'verified'
            summary['verified'] += 1
        except (OSError, InvalidCase) as error:
            record.update(result='failed', reason=str(error))
            summary['failed'] += 1
    report['status'] = 'failed' if summary['failed'] else 'passed'
    return report


def register_reviewed_case(cases_root, baseline_path, case_id):
    """Explicitly append one independently reviewed case; never replace approvals.

    The caller serializes registrations. Missing or invalid expected.json is
    rejected, and observations are never promoted into expected answers.
    """
    destination = validate_report_path(baseline_path, cases_root)
    baseline = (_review_baseline_payload(cases_root, destination) if destination.exists()
                else {'schema_version': 1, 'cases': []})
    entry = _reviewed_case_entry(cases_root, case_id)
    previous = next((item for item in baseline['cases'] if item['case_id'] == case_id), None)
    if previous is not None:
        _require(previous == entry, 'approved case has changed; registration cannot overwrite old hashes')
        return {'status': 'already_registered', 'entry': previous}
    baseline['cases'].append(entry)
    write_report(baseline, destination, cases_root)
    return {'status': 'registered', 'entry': entry}


def main(argv=None, *, runner=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-dir', type=Path, help='Archive root (default: bootstrap.STATE_DIR/bug-cases)')
    parser.add_argument('--run-reviewed', action='store_true', help='Replay only complete, hash-bound expected.json oracles')
    parser.add_argument('--review-baseline', type=Path, help='Public hash index of approved private originals; verify all accepted files')
    parser.add_argument('--register-reviewed-case', help='Explicitly append this already independently reviewed case ID to --review-baseline')
    parser.add_argument('--report', type=Path, help='Write JSON outside the archive root')
    args = parser.parse_args(argv)
    if args.cases_dir is None:
        sys.path.insert(0, str(ROOT/'outputs/companion'))
        from bootstrap import STATE_DIR
        args.cases_dir = STATE_DIR/'bug-cases'
    if args.report is not None:
        try:
            validate_report_path(args.report, args.cases_dir)
        except (OSError, InvalidCase) as error:
            parser.error(str(error))
    if args.register_reviewed_case and args.review_baseline is None:
        parser.error('--register-reviewed-case requires --review-baseline')
    if args.report is not None and args.review_baseline is not None:
        if args.report.absolute().resolve() == args.review_baseline.absolute().resolve():
            parser.error('--report must not overwrite the approved review baseline')
    if args.register_reviewed_case:
        try:
            registered = register_reviewed_case(args.cases_dir, args.review_baseline, args.register_reviewed_case)
        except (OSError, InvalidCase) as error:
            parser.error(str(error))
        print(f"Reviewed case: {registered['status']} ({registered['entry']['case_id']})")
        return 0
    report = validate_cases(args.cases_dir, run_reviewed=args.run_reviewed, runner=runner)
    if args.review_baseline is not None:
        report['review_baseline'] = validate_review_baseline(args.cases_dir, args.review_baseline, verify_files=True)
    if args.report is not None:
        write_report(report, args.report, args.cases_dir)
    counts = report['summary']
    print(f"Bug cases: {report['status']}; pending={counts['pending_review']}, reviewed={counts['reviewed']}, "
          f"passed={counts['passed']}, failed={counts['failed']}, invalid={counts['invalid']}, skipped={counts['skipped']}")
    for case in report['cases']:
        print(f"  {case['case_id'] or '(archive)'}: {case['result']} ({case.get('reason', '')})")
    if args.review_baseline is not None:
        baseline = report['review_baseline']
        print(f"Reviewed baseline: {baseline['status']}; {baseline['summary']}")
        if baseline.get('reason'):
            print(f"  {baseline['reason']}")
        for case in baseline['cases']:
            if case['result'] == 'failed':
                print(f"  {case['case_id']}: {case['reason']}")
    return exit_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
