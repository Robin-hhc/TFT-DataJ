"""Conservative selection transactions; mouse input is intent, never a receipt.

The caller supplies calibrated card regions and independently validated completion
evidence. Automatic confirmation is disabled until that layout is explicitly
accepted. Query revisions, overlays, OCR retries and unknown frames are irrelevant
to a frozen transaction, while real refresh/context changes cancel it.
"""
from dataclasses import dataclass, replace
import math
from uuid import uuid4

from selected_resources import SelectedEvent, SelectionEntity


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def valid(self):
        return (all(finite(v) for v in (self.left, self.top, self.right, self.bottom))
                and self.left < self.right and self.top < self.bottom)

    def contains(self, x, y):
        return self.valid and self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class CardSnapshot:
    slot: str
    entity: SelectionEntity
    selectable: Rect


@dataclass(frozen=True)
class OfferSnapshot:
    session_id: str
    offer_id: str
    revision: int
    window_identity: object
    window_hwnd: int
    geometry_revision: object
    frame_time: float
    layout_id: str
    cards: tuple
    exclusions: tuple = ()
    fingerprint: str = ''
    round: str | None = None
    layout_verified: bool = False

    @property
    def flow(self):
        return self.session_id, self.offer_id, self.revision

    @property
    def identity(self):
        return (self.flow, self.window_identity, self.geometry_revision, self.layout_id,
                self.cards, self.exclusions, self.fingerprint)

    @property
    def valid(self):
        return (all(isinstance(value, str) and bool(value.strip())
                    for value in (self.session_id, self.offer_id, self.layout_id))
                and type(self.revision) is int and self.revision >= 0
                and type(self.window_hwnd) is int and self.window_hwnd > 0 and self.window_identity is not None
                and self.geometry_revision is not None and finite(self.frame_time)
                and self.layout_verified is True and isinstance(self.cards, tuple)
                and 1 <= len(self.cards) <= 5
                and all(isinstance(card, CardSnapshot) and isinstance(card.entity, SelectionEntity)
                        and card.entity.valid and isinstance(card.slot, str) and bool(card.slot)
                        and isinstance(card.selectable, Rect) and card.selectable.valid
                        for card in self.cards)
                and len({card.slot for card in self.cards}) == len(self.cards)
                and isinstance(self.exclusions, tuple)
                and all(isinstance(rect, Rect) and rect.valid for rect in self.exclusions))

    def card_at(self, x, y):
        if any(rect.contains(x, y) for rect in self.exclusions):
            return None
        hits = [card for card in self.cards if card.selectable.contains(x, y)]
        return hits[0] if len(hits) == 1 else None


@dataclass(frozen=True)
class MouseNotice:
    action: str
    x: float
    y: float
    at: float
    foreground: int
    injected: bool = False


@dataclass(frozen=True)
class CompletionEvidence:
    session_id: str
    offer_id: str
    revision: int
    window_identity: object
    geometry_revision: object
    layout_id: str
    slot: str
    at: float
    kind: str
    reference: str

    @property
    def flow(self):
        return self.session_id, self.offer_id, self.revision


@dataclass(frozen=True)
class SelectionProposal:
    selection_event_id: str
    snapshot: OfferSnapshot
    card: CardSnapshot
    down: MouseNotice
    up: MouseNotice | None = None
    completion: CompletionEvidence | None = None

    @property
    def entity(self):
        return self.card.entity


class SelectionTracker:
    COMPLETION_KINDS = frozenset(('selected_animation', 'selected_result'))

    def __init__(self, session_id, *, on_selected=None, accepted_layouts=(),
                 max_offer_age=1.0, timeout=2.0, drag_distance=8.0):
        if (not session_id or not finite(max_offer_age) or not finite(timeout)
                or not finite(drag_distance) or min(max_offer_age, timeout, drag_distance) <= 0):
            raise ValueError('A game identity and positive bounded timing are required')
        self.session_id = str(session_id)
        self.on_selected = on_selected
        self.accepted_layouts = frozenset(accepted_layouts)
        self.max_offer_age = max_offer_age
        self.timeout = timeout
        self.drag_distance = drag_distance
        self.offer = None
        self.proposal = None
        self.last_cancel_reason = ''
        self._blocked_flow = None
        self._finished_flows = set()

    @property
    def pending_confirmation(self):
        """Only a unique, paired click can be explicitly confirmed by the user."""
        return self.proposal if self.proposal and self.proposal.up else None

    @property
    def state(self):
        if self.proposal:
            return 'pending' if self.proposal.up else 'pressed'
        return 'offer_ready' if self.offer else 'idle'

    def observe_offer(self, snapshot, *, now):
        self.tick(now)
        if (not isinstance(snapshot, OfferSnapshot) or not snapshot.valid
                or snapshot.session_id != self.session_id or not finite(now)
                or not 0 <= now - snapshot.frame_time <= self.max_offer_age):
            return False
        if snapshot.flow in self._finished_flows or snapshot.flow == self._blocked_flow:
            return False
        previous = self.offer or (self.proposal.snapshot if self.proposal else None)
        if previous and previous.offer_id == snapshot.offer_id and snapshot.revision < previous.revision:
            return False
        if previous and snapshot.identity != previous.identity:
            self.invalidate('offer_changed')
            if snapshot.flow == previous.flow:
                # A changed candidate set cannot reuse an earlier evidence key.
                # The observer must issue a new revision or offer identity first.
                return False
        # A repeated read only updates freshness. It cannot restart or extend a click.
        self.offer = snapshot
        if self._blocked_flow != snapshot.flow:
            self._blocked_flow = None
        return True

    def scene_left(self, *, now):
        """Unknown/normal frames hide current offers but supply no completion proof."""
        self.tick(now)
        self.offer = None

    def guard(self, *, window_identity, geometry_revision, foreground):
        snapshot = self.offer or (self.proposal.snapshot if self.proposal else None)
        if snapshot and (window_identity != snapshot.window_identity
                         or geometry_revision != snapshot.geometry_revision
                         or foreground != snapshot.window_hwnd):
            self.invalidate('window_or_geometry_changed')
            return False
        return True

    def invalidate(self, reason='invalidated'):
        snapshot = self.offer or (self.proposal.snapshot if self.proposal else None)
        if snapshot:
            self._blocked_flow = snapshot.flow
        self.offer = None
        self.proposal = None
        self.last_cancel_reason = str(reason)

    def reset(self, session_id):
        self.session_id = str(session_id)
        self.offer = None
        self.proposal = None
        self._blocked_flow = None
        self._finished_flows.clear()
        self.last_cancel_reason = ''

    def tick(self, now):
        if self.proposal and (not finite(now) or now < self.proposal.down.at
                              or now - self.proposal.down.at > self.timeout):
            self.invalidate('confirmation_timeout')

    def mouse(self, notice):
        if not isinstance(notice, MouseNotice) or not all(finite(v) for v in (notice.x, notice.y, notice.at)):
            return None
        self.tick(notice.at)
        if notice.injected or notice.action not in ('down', 'up', 'move'):
            return None
        proposal = self.proposal
        snapshot = proposal.snapshot if proposal else self.offer
        if not snapshot:
            return None
        if notice.foreground != snapshot.window_hwnd:
            self.invalidate('lost_foreground')
            return None
        card = snapshot.card_at(notice.x, notice.y)
        if proposal:
            if (notice.at < proposal.down.at or card is None or card.slot != proposal.card.slot
                    or math.hypot(notice.x - proposal.down.x, notice.y - proposal.down.y) > self.drag_distance):
                self.invalidate('conflicting_or_dragged_click')
                return None
            if notice.action == 'up' and not proposal.up:
                self.proposal = replace(proposal, up=notice)
                return self._complete_if_ready()
            # Same-card repeat down/up merges into the existing transaction.
            return None
        if (notice.action != 'down' or card is None
                or not 0 <= notice.at - snapshot.frame_time <= self.max_offer_age):
            return None
        self.proposal = SelectionProposal(uuid4().hex, snapshot, card, notice)
        return None

    def evidence(self, evidence, *, now=None):
        now = evidence.at if now is None and isinstance(evidence, CompletionEvidence) else now
        self.tick(now)
        proposal = self.proposal
        if not proposal or not isinstance(evidence, CompletionEvidence):
            return None
        snapshot = proposal.snapshot
        if (evidence.flow != snapshot.flow or evidence.window_identity != snapshot.window_identity
                or evidence.geometry_revision != snapshot.geometry_revision
                or evidence.layout_id != snapshot.layout_id or evidence.slot != proposal.card.slot
                or evidence.layout_id not in self.accepted_layouts
                or evidence.kind not in self.COMPLETION_KINDS
                or not isinstance(evidence.reference, str) or not evidence.reference.strip()
                or not finite(evidence.at) or evidence.at < proposal.down.at
                or not finite(now) or evidence.at > now
                or evidence.at - proposal.down.at > self.timeout):
            return None
        self.proposal = replace(proposal, completion=evidence)
        return self._complete_if_ready()

    def manual_confirm(self, selection_event_id, *, now):
        self.tick(now)
        if not self.pending_confirmation or self.proposal.selection_event_id != selection_event_id:
            return None
        return self._publish(now, 'manual_confirmation', '')

    def _complete_if_ready(self):
        proposal = self.proposal
        if proposal and proposal.up and proposal.completion:
            return self._publish(max(proposal.up.at, proposal.completion.at), 'automatic_verified',
                                 proposal.completion.reference)
        return None

    def _publish(self, at, source, reference):
        proposal = self.proposal
        if not proposal or not proposal.up or not proposal.entity.valid:
            return None
        snapshot = proposal.snapshot
        if snapshot.flow in self._finished_flows or len(self._finished_flows) >= 256:
            self.invalidate('flow_already_finished_or_bound_reached')
            return None
        entity = proposal.entity
        event = SelectedEvent(proposal.selection_event_id, snapshot.session_id, entity.kind,
                              entity.entity_id, entity.name, entity.category, snapshot.round,
                              float(at), source, entity.picture, reference)
        self._finished_flows.add(snapshot.flow)
        self.offer = None
        self.proposal = None
        if self.on_selected:
            self.on_selected(event)
        return event
