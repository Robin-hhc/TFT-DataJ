"""Connect existing observations and queued mouse notices to selection transactions.

No screenshot, OCR, timer, network call or game input lives here. Layout geometry
is a proposal until independently qualified; the production whitelist is empty.
Ordinary scene/query invalidation hides offers but cannot turn disappearance into
completion. Bounded receipt probes are requests for the caller's existing queue.
"""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
import time
from uuid import uuid4

from selected_resources import SelectedEvent, SelectionEntity
from selection_layout import augment_geometry, item_geometry
from selection_tracker import CompletionEvidence, MouseNotice, OfferSnapshot, SelectionTracker, finite


ITEM_CATEGORIES = {'成型装备': 'completed', '神器装备': 'artifact', '光明武器': 'radiant'}


def window_identity(binding):
    if binding is None or any(not hasattr(binding,key) for key in ('hwnd','pid','process')):return None
    return (binding.hwnd, binding.pid, binding.process)


def geometry_revision(binding):
    return (tuple(binding.rect), binding.dpi) if binding is not None else None


@dataclass(frozen=True)
class ReceiptProbe:
    selection_event_id: str
    generation: int
    attempt: int
    requested_at: float
    snapshot: OfferSnapshot
    slot: str


class SelectionController:
    """Invoke on the Qt main queue, never directly from the native mouse hook."""
    def __init__(self, session_id, resolver, *, on_selected=None, verified_layouts=(),
                 win_api=None, clock=time.monotonic, on_context_reset=None):
        self.resolver = resolver
        self.clock = clock
        self.on_selected = on_selected
        self.on_context_reset = on_context_reset
        self.verified_layouts = frozenset(verified_layouts)
        self.win = win_api
        self.tracker = SelectionTracker(session_id, on_selected=self._publish,
                                        accepted_layouts=self.verified_layouts)
        self.binding = None
        self.snapshot = None
        self.generation = 0
        self._signature = None
        self._regions = None
        self._last_frame_time = None
        self._minimum_frame_time = None
        self._force_new_offer = False
        self._probe_event = None
        self._probe_attempts = 0
        self._manual_events = set()

    @property
    def session_id(self):
        return self.tracker.session_id

    def _native(self):
        if self.win is None:
            import bootstrap  # Make the existing packaged/native module available.
            import win_capture
            self.win = win_capture
        return self.win

    def _publish(self, event):
        if self.on_selected:
            self.on_selected(event)

    def _clear_context(self):
        self.generation += 1
        self.tracker.reset(self.session_id)
        self.snapshot = None
        self._signature = None
        self._regions = None
        self._last_frame_time = None
        self._force_new_offer = False
        self._probe_event = None
        self._probe_attempts = 0
        self._manual_events.clear()

    def binding_changed(self, binding):
        previous = window_identity(self.binding)
        current = window_identity(binding)
        if previous is not None and previous != current:
            self._clear_context()
            if self.on_context_reset:
                self.on_context_reset('binding_changed', current)
        elif self.binding is not None and geometry_revision(self.binding) != geometry_revision(binding):
            self.cancel('window_geometry_changed')
        self.binding = binding

    def window_closed(self):
        had_context = self.binding is not None or self.snapshot is not None
        self._clear_context()
        self.binding = None
        self._minimum_frame_time = self.clock()
        if had_context and self.on_context_reset:
            self.on_context_reset('window_closed', None)

    def new_game(self, session_id):
        self.tracker.reset(session_id)
        self._clear_context()
        self._minimum_frame_time = self.clock()

    def scene_left(self):
        self.tracker.scene_left(now=self.clock())

    def invalidate(self):
        """Ordinary UI/query invalidation is not a refresh or a new game."""
        self.scene_left()

    def cancel(self, reason='invalidated'):
        self.generation += 1
        self.tracker.invalidate(reason)
        self.snapshot = None
        self._signature = None
        self._regions = None
        self._force_new_offer = True
        self._probe_event = None
        self._probe_attempts = 0

    def start_new_offer(self, reason='new_selection'):
        """Use only for an independently observed refresh/new reward event.

        A single unknown frame must never invoke this method. Identical equipment
        selected in a separate offer needs a new flow, not an entity-ID dedup key.
        """
        self.cancel(reason)

    def tick(self):
        self.tracker.tick(self.clock())

    def _guard(self):
        if self.binding is None:
            return False
        native = self._native()
        current = native.describe(self.binding.hwnd)
        if window_identity(current) != window_identity(self.binding):
            self.window_closed()
            return False
        foreground = native.foreground_root()
        if getattr(current,'minimized',True):
            self.cancel('minimized')
            return False
        if geometry_revision(current) != geometry_revision(self.binding):
            self.cancel('window_geometry_changed')
            return False
        if foreground != current.hwnd:
            self.cancel('lost_foreground')
            return False
        return self.tracker.guard(window_identity=window_identity(current),
            geometry_revision=geometry_revision(current), foreground=foreground)

    def _entity(self, kind, resolution):
        if not isinstance(resolution, dict) or resolution.get('status') != 'resolved':
            return None
        # The existing two-view reader already resolves the visible title/description.
        # Still validate its row against the shared identity contract; never trust ID alone.
        candidates = resolution.get('candidates', ())
        candidates = candidates if isinstance(candidates, (tuple, list)) else ()
        matches = [row for row in candidates if isinstance(row, dict)
                   and str(row.get('id')) == str(resolution.get('id'))
                   and row.get('name') == resolution.get('name')]
        row = matches[0] if len(matches) == 1 else resolution
        resolved = self.resolver.resolve_selection(kind, row)
        if not resolved.confirmed:
            return None
        row = resolved.entity
        return SelectionEntity(kind, str(row['id']), row['name'],
            row.get('category', row.get('type', '')), row.get('picture', ''), True)

    def observe(self, observation, image_size, binding, frame_time):
        now = self.clock()
        if (window_identity(binding) is None or not isinstance(observation, dict) or not finite(frame_time) or not finite(now)
                or not 0 <= now - frame_time <= self.tracker.max_offer_age
                or (self._minimum_frame_time is not None and frame_time < self._minimum_frame_time)
                or (self._last_frame_time is not None and frame_time < self._last_frame_time)):
            return None
        self.binding_changed(binding)
        if not self._guard():
            return None
        self._last_frame_time = frame_time
        scene = observation.get('scene')
        if scene not in ('choice_candidates', 'item_candidates'):
            self.scene_left()
            return None
        cards = observation.get('cards')
        if (not isinstance(cards, (tuple, list)) or not cards
                or any(not isinstance(card, dict) or 'slot' not in card for card in cards)
                or len({str(card.get('slot')) for card in cards}) != len(cards)):
            self.scene_left()
            return None
        kind = 'hex' if scene == 'choice_candidates' else 'equip'
        entities = {}
        for card in cards:
            entity = self._entity(kind, card.get('resolution'))
            if entity is not None:
                entities[str(card['slot'])] = entity
        if not entities:
            self.cancel('candidate_identity_unconfirmed')
            return None
        if kind == 'hex':
            geometry = augment_geometry(observation, image_size, screen_rect=binding.rect)
        else:
            if [str(card['slot']) for card in cards] != [str(i) for i in range(len(cards))]:
                self.cancel('invalid_item_slot_order')
                return None
            categories = {ITEM_CATEGORIES.get(entity.category) for entity in entities.values()}
            if len(categories) != 1 or None in categories:
                self.cancel('unsupported_or_mixed_item_categories')
                return None
            boxes = []
            for card in cards:
                points = card.get('box')
                try:
                    xs, ys = zip(*points)
                    boxes.append((min(xs), min(ys), max(xs), max(ys)))
                except (TypeError, ValueError):
                    self.cancel('invalid_item_geometry')
                    return None
            geometry = item_geometry(boxes, image_size, category=next(iter(categories)),
                                     screen_rect=binding.rect)
        if geometry is None:
            self.cancel('layout_unconfirmed')
            return None
        round_info = observation.get('round')
        stage = round_info if isinstance(round_info, str) else (
            round_info.get('value') if isinstance(round_info, dict)
            and round_info.get('status') == 'resolved' else None)
        if not isinstance(stage, str) or not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*', stage):
            stage = None
        if (stage is None and self.snapshot is not None
                and self.snapshot.layout_id == geometry.layout_id
                and {card.slot: card.entity.key for card in self.snapshot.cards}
                    == {slot: entity.key for slot, entity in entities.items()}):
            # Losing the round OCR for one read is not a refreshed offer. This
            # preserves only the existing candidate context, never signals a reset.
            stage = self.snapshot.round
        # Canonical identity is stable across OCR retries. OCR box jitter must not
        # remap an already frozen hit region while a click is being completed.
        metadata = {'layout': geometry.layout_id, 'round': stage,
                    'image_size': tuple(image_size),
                    'window': window_identity(binding), 'geometry': geometry_revision(binding),
                    'slots': [(str(card['slot']), entities[str(card['slot'])].key
                               if str(card['slot']) in entities else None,
                               card.get('description_signature')) for card in cards]}
        signature = sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode('utf8')).hexdigest()
        regions_stable = (self._regions is not None and len(self._regions) == len(geometry.regions)
            and all(a_slot == b_slot and max(abs(a - b) for a, b in zip(
                (a_rect.left, a_rect.top, a_rect.right, a_rect.bottom),
                (b_rect.left, b_rect.top, b_rect.right, b_rect.bottom))) <= 8
                    for (a_slot, a_rect), (b_slot, b_rect) in zip(self._regions, geometry.regions)))
        if (self.snapshot is not None and self._signature == signature
                and regions_stable and not self._force_new_offer):
            snapshot = replace(self.snapshot, frame_time=float(frame_time))
        else:
            if self.snapshot is not None or self.tracker.proposal is not None:
                self.cancel('offer_changed')
            snapshot = OfferSnapshot(self.session_id, uuid4().hex, 0,
                window_identity(binding), binding.hwnd, geometry_revision(binding), float(frame_time),
                geometry.layout_id, geometry.cards(entities), geometry.exclusions, signature, stage,
                geometry.layout_id in self.verified_layouts)
            self._regions = geometry.regions
        self.snapshot = snapshot
        self._signature = signature
        self._force_new_offer = False
        if snapshot.layout_verified:
            self.tracker.observe_offer(snapshot, now=now)
        return snapshot

    def on_mouse(self, notice):
        """Queued slot: native hook has already returned/forwarded the input."""
        if not isinstance(notice, MouseNotice) or notice.injected:
            return None
        self.tick()
        if not (self.tracker.offer or self.tracker.proposal) or not self._guard():
            return None
        now = self.clock()
        if not finite(notice.at) or not 0 <= now - notice.at <= self.tracker.max_offer_age:
            self.cancel('stale_mouse_notice')
            return None
        return self.tracker.mouse(notice)

    def next_receipt_probe(self):
        """At most three requests, inside the original two-second transaction."""
        self.tick()
        proposal = self.tracker.pending_confirmation
        if proposal is None or not self._guard():
            return None
        if self._probe_event != proposal.selection_event_id:
            self._probe_event = proposal.selection_event_id
            self._probe_attempts = 0
        if self._probe_attempts >= 3:
            return None
        self._probe_attempts += 1
        return ReceiptProbe(proposal.selection_event_id, self.generation, self._probe_attempts,
                            self.clock(), proposal.snapshot, proposal.card.slot)

    def probe_current(self, probe):
        self.tick()
        p = self.tracker.proposal
        return (isinstance(probe, ReceiptProbe) and p is not None
                and probe.generation == self.generation
                and probe.selection_event_id == p.selection_event_id
                and probe.snapshot.identity == p.snapshot.identity)

    def accept_evidence(self, evidence):
        if not isinstance(evidence, CompletionEvidence) or not self._guard():
            return None
        return self.tracker.evidence(evidence, now=self.clock())

    def confirm_detail(self, kind, row, *, explicitly_confirmed=False,
                       selection_event_id, session_id, round=None):
        """Explicit UI confirmation; reading/querying a detail is insufficient."""
        if (explicitly_confirmed is not True or session_id != self.session_id
                or kind not in ('hex', 'equip', 'hero')
                or not isinstance(selection_event_id, str) or not selection_event_id.strip()
                or selection_event_id in self._manual_events or len(self._manual_events) >= 256):
            return None
        resolution = self.resolver.resolve_selection(kind, row)
        now = self.clock()
        if not resolution.confirmed or not finite(now):
            return None
        entity = resolution.entity
        event = SelectedEvent(selection_event_id, self.session_id, kind, str(entity['id']),
            entity['name'], entity.get('category', entity.get('type', '')), round, float(now),
            'manual_confirmation', entity.get('picture', ''))
        self._manual_events.add(selection_event_id)
        self._publish(event)
        return event
