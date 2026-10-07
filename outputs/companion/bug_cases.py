"""Append-only local screenshots awaiting review; no uploads or background work.

The caller serializes saves (the companion uses a dedicated single worker).
The semantic case fingerprint is independent of the PNG's content hash.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import unicodedata


def _json_safe(value, ancestors=None):
    """Keep normal metadata intact and mark only unsupported/cyclic leaves."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'nonfinite_number': str(value)}
    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        return {'unserializable_type': type(value).__name__, 'reason': 'circular_reference'}
    ancestors.add(identity)
    try:
        if isinstance(value, Mapping):
            result = {}
            for key, item in value.items():
                try:
                    name = key if isinstance(key, str) else str(key)
                except Exception:
                    name = '<unsupported-key>'
                result[name] = _json_safe(item, ancestors)
            return result
        if isinstance(value, (list, tuple)):
            return [_json_safe(item, ancestors) for item in value]
        if isinstance(value, (set, frozenset)):
            values = [_json_safe(item, ancestors) for item in value]
            return sorted(values, key=lambda item: json.dumps(item, sort_keys=True))
        if isinstance(value, Enum):
            return _json_safe(value.value, ancestors)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bytes):
            return {'encoding': 'base64', 'data': base64.b64encode(value).decode('ascii')}
        if is_dataclass(value) and not isinstance(value, type):
            return {field.name: _json_safe(getattr(value, field.name), ancestors)
                    for field in fields(value)}
    except Exception:
        pass
    finally:
        ancestors.remove(identity)
    return {'unserializable_type': f'{type(value).__module__}.{type(value).__qualname__}'}


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _text(value):
    """Normalize OCR spacing/Unicode without conflating suffixes or punctuation."""
    if value is None:
        return ''
    if not isinstance(value, (str, int, float, bool)):
        value = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
    return ''.join(unicodedata.normalize('NFKC', str(value)).split())


def _first(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _is_link(info):
    # Junctions and other Windows reparse points are not necessarily symlinks.
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, 'st_file_attributes', 0)
                    & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)))


def _check_path(path):
    """Check each existing ancestor before any operation that can write."""
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise OSError('The case directory must not traverse links or files')


def _regular_file(path):
    info = path.lstat()
    if _is_link(info) or not stat.S_ISREG(info.st_mode):
        raise OSError('Case contents must be regular files')
    return info


def _sha256(path):
    _regular_file(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class BugCaseStore:
    def __init__(self, directory=None, max_cases=100, max_bytes=500 * 1024 * 1024):
        if directory is None:
            from bootstrap import STATE_DIR
            directory = STATE_DIR / 'bug-cases'
        # abspath preserves the lexical route, unlike resolve() which hides links.
        self.directory = Path(os.path.abspath(os.fspath(directory)))
        self.max_cases = max(0, int(max_cases))
        self.max_bytes = max(0, int(max_bytes))

    def fingerprint(self, observation, reason, context):
        observation, context = _mapping(observation), _mapping(context)
        cards = observation.get('cards', ())
        cards = cards if isinstance(cards, (list, tuple)) else ()
        slots = []
        for index, item in enumerate(cards):
            card = _mapping(item)
            resolution = _mapping(card.get('resolution'))
            raw = _first(card, 'raw_text', 'text')
            if raw is None:
                raw = resolution.get('name')
            if raw is None:
                readings = resolution.get('readings', ())
                if isinstance(readings, (list, tuple)):
                    raw = sorted({_text(text) for text in readings if _text(text)})
            candidates = resolution.get('candidates', ())
            candidates = candidates if isinstance(candidates, (list, tuple)) else ()
            candidate_ids = {_text(candidate.get('id') if isinstance(candidate, Mapping)
                                   else candidate) for candidate in candidates}
            extra_ids = resolution.get('candidate_ids', ())
            if isinstance(extra_ids, (list, tuple, set, frozenset)):
                candidate_ids.update(_text(value) for value in extra_ids)
            slots.append({'slot': _text(card.get('slot', index)), 'raw_text': _text(raw),
                          'status': _text(resolution.get('status')),
                          'id': _text(resolution.get('id')),
                          'suggested_id': _text(resolution.get('suggested_id')),
                          'excluded_id': _text(resolution.get('excluded_id')),
                          'candidate_ids': sorted(candidate_ids - {''})})
        slots.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        identity = {
            'schema_version': 1, 'reason': _text(reason),
            'set_id': _text(_first(context, 'set_id', 'set', 'season')),
            'patch': _text(_first(context, 'patch', 'version')),
            'target': _json_safe(_first(context, 'target', 'target_id')),
            'domain': _text(context.get('domain')),
            'source': _text(context.get('source')),
            'frame_scope': _text(context.get('frame_scope')),
            'scene': _text(observation.get('scene')),
            'stage': _text(_first(observation, 'stage', 'round')), 'slots': slots,
        }
        if reason == 'manual_report':
            # The capture worker supplies a pixel hash for intentionally reported
            # unknown screens, which otherwise have no semantic slot identity.
            identity['manual_frame_id'] = _text(observation.get('manual_frame_id'))
        if context.get('domain') == 'condition':
            # Detail failures have no choice slots. Keep their observed title and
            # route identity so unrelated failed requests are independently reviewable.
            evidence = _mapping(observation.get('evidence'))
            readings = evidence.get('readings', ())
            readings = readings if isinstance(readings, (list, tuple)) else ()
            candidates = observation.get('candidates', ())
            candidates = candidates if isinstance(candidates, (list, tuple)) else ()
            candidate_ids = {(_text(_mapping(candidate).get('kind')),
                              _text(_mapping(candidate).get('id')))
                             for candidate in candidates}
            identity['condition'] = {
                'reason': _text(observation.get('reason')),
                'status': _text(observation.get('status')),
                'route': _text(observation.get('route')),
                'readings': sorted({_text(value) for value in readings if _text(value)}),
                'title_rect': _json_safe(evidence.get('title_rect')),
                'popup_rect': _json_safe(evidence.get('popup_rect')),
                'candidates': sorted(candidate_ids),
            }
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def _usage(self, exclude=None):
        """Count damaged cases too; account for every existing byte without links."""
        count = 0
        size = 0
        pending = [self.directory]
        while pending:
            directory = pending.pop()
            _check_path(directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if exclude is not None and path == exclude:
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if _is_link(info):
                        raise OSError('Links inside the case store require manual review')
                    if directory == self.directory and entry.name.startswith('case-'):
                        count += 1
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        size += info.st_size
                    else:
                        raise OSError('Unsupported file inside the case store')
        return count, size

    def _existing_case(self, path, case_id):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise OSError('The existing case path is unsafe')
        _check_path(path)
        metadata = path / 'case.json'
        _regular_file(metadata)
        with metadata.open('r', encoding='utf-8') as stream:
            payload = json.load(stream)
        image = _mapping(_mapping(payload).get('image'))
        if (payload.get('schema_version') != 1 or payload.get('case_id') != case_id
                or image.get('filename') != 'frame.png'
                or image.get('sha256') != _sha256(path / 'frame.png')):
            raise OSError('An existing case is incomplete or damaged')
        return True

    def _cleanup(self, temporary):
        if temporary is None:
            return
        try:
            # Only this invocation's fixed files may be removed. Do not recurse
            # into unexpected paths or delete abandoned samples from older runs.
            if temporary.parent != self.directory or not temporary.name.startswith('.pending-'):
                return
            _check_path(temporary)
            for name in ('frame.png', 'case.json'):
                path = temporary / name
                try:
                    _regular_file(path)
                    path.unlink()
                except FileNotFoundError:
                    pass
            temporary.rmdir()
        except OSError:
            pass

    def save(self, image, observation, *, reason, context, evidence=None):
        case_id = None
        case_path = None
        temporary = None

        def result(status, error=None):
            value = {'status': status, 'case_id': case_id,
                     'path': str(case_path) if status in ('saved', 'duplicate') else None}
            if error is not None:
                value['error'] = type(error).__name__
            return value

        try:
            case_id = self.fingerprint(observation, reason, context)
            case_path = self.directory / f'case-{case_id}'
            _check_path(self.directory)
            self.directory.mkdir(parents=True, exist_ok=True)
            _check_path(self.directory)
            if self._existing_case(case_path, case_id):
                return result('duplicate')
            count, size = self._usage()
            if count >= self.max_cases or size >= self.max_bytes:
                return result('limit')

            temporary = Path(tempfile.mkdtemp(prefix='.pending-', dir=self.directory))
            _check_path(temporary)
            image_path = temporary / 'frame.png'
            with image_path.open('xb') as stream:
                image.save(stream, format='PNG', compress_level=1)
            _check_path(temporary)
            width, height = image.size
            payload = {'schema_version': 1, 'case_id': case_id, 'status': 'pending_review',
                       'created_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                       'reason': _json_safe(reason), 'context': _json_safe(context),
                       'observation': _json_safe(observation), 'evidence': _json_safe(evidence),
                       'image': {'filename': 'frame.png', 'sha256': _sha256(image_path),
                                 'width': int(width), 'height': int(height)}}
            _check_path(temporary)
            with (temporary / 'case.json').open('x', encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
            case_size = sum(_regular_file(temporary / name).st_size
                            for name in ('frame.png', 'case.json'))
            count, size = self._usage(exclude=temporary)
            if count >= self.max_cases or size + case_size > self.max_bytes:
                return result('limit')
            _check_path(self.directory)
            _check_path(temporary)
            if self._existing_case(case_path, case_id):
                return result('duplicate')
            # On Windows rename refuses an existing destination. Completed case
            # directories are nonempty, so rename cannot replace them on POSIX.
            try:
                os.rename(temporary, case_path)
            except OSError:
                if self._existing_case(case_path, case_id):
                    return result('duplicate')
                raise
            temporary = None
            return result('saved')
        except Exception as error:
            return result('error', error)
        finally:
            self._cleanup(temporary)
