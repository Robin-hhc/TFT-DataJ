"""Confirmed selection history for one game, separate from query revisions.

This is a history of choices, never an inventory or a list of visible candidates.
No image pixels or statistics responses are retained here.
"""
from dataclasses import dataclass
import math
from uuid import uuid4


@dataclass(frozen=True)
class SelectionEntity:
    kind: str
    entity_id: str
    name: str
    category: str = ''
    picture: str = ''
    identity_confirmed: bool = False

    @property
    def key(self):
        return self.kind, self.entity_id

    @property
    def valid(self):
        return (self.identity_confirmed is True and self.kind in ('hex', 'equip', 'hero')
                and isinstance(self.entity_id, str) and bool(self.entity_id.strip())
                and isinstance(self.name, str) and bool(self.name.strip()))


@dataclass(frozen=True)
class SelectedEvent:
    selection_event_id: str
    session_id: str
    kind: str
    entity_id: str
    name: str
    category: str
    round: str | None
    selected_at: float
    source: str
    picture: str = ''
    evidence_reference: str = ''

    @property
    def entity(self):
        return SelectionEntity(self.kind, self.entity_id, self.name, self.category,
                               self.picture, identity_confirmed=True)


class SelectedResources:
    SOURCES = frozenset(('automatic_verified', 'direct_selected_detail', 'manual_confirmation'))

    def __init__(self, session_id, *, max_events=256):
        if not session_id or max_events < 1:
            raise ValueError('A game identity and positive history bound are required')
        self.session_id = str(session_id)
        self.max_events = max_events
        self.window_identity = None
        self._events = {}

    @property
    def events(self):
        return tuple(self._events.values())

    @property
    def shortcuts(self):
        """Newest unique entity first. Repeated selections remain separate events."""
        seen = set()
        result = []
        for event in reversed(self.events):
            if event.entity.key not in seen:
                seen.add(event.entity.key)
                result.append(event)
        return tuple(result)

    def confirm(self, entity, *, selection_event_id, session_id, selected_at,
                source, round=None, evidence_reference=''):
        if source not in self.SOURCES:
            raise ValueError('Only confirmed selection sources can enter game history')
        if (session_id != self.session_id or not isinstance(entity, SelectionEntity)
                or not entity.valid or not isinstance(selection_event_id, str)
                or not selection_event_id.strip() or not isinstance(selected_at, (int, float))
                or isinstance(selected_at, bool) or not math.isfinite(selected_at)):
            return None
        if source != 'manual_confirmation' and not evidence_reference:
            return None
        previous = self._events.get(selection_event_id)
        if previous:
            return previous if previous.entity == entity else None
        if len(self._events) >= self.max_events:
            # Do not evict event IDs and then accidentally admit duplicate callbacks.
            return None
        event = SelectedEvent(selection_event_id, self.session_id, entity.kind, entity.entity_id,
                              entity.name, entity.category, round, float(selected_at), source,
                              entity.picture, str(evidence_reference))
        self._events[selection_event_id] = event
        return event

    def reset(self, session_id=None):
        self.session_id = str(session_id or uuid4().hex)
        self._events.clear()
        self.window_identity = None

    def bind_window(self, identity, *, session_id=None):
        """A changed/closed game window never retains shortcuts from the old game."""
        if self.window_identity is not None and self.window_identity != identity:
            self.reset(session_id)
        self.window_identity = identity
