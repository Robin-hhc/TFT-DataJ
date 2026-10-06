"""Selection-region proposals from existing S18 observations, without capture/OCR.

These interiors are visually annotated proposals. A screenshot does not establish
that the game accepts a click there; layout_verified is deliberately always False.
Live input/receipt evidence must independently qualify a layout before automatic
selection tracking is enabled.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from selected_resources import SelectionEntity
from selection_tracker import CardSnapshot, Rect, finite


@dataclass(frozen=True)
class GeometryProposal:
    layout_id: str
    image_size: tuple
    regions: tuple
    exclusions: tuple
    source: str

    @property
    def layout_verified(self):
        return False

    def slot_at(self, x, y):
        if not finite(x) or not finite(y) or any(rect.contains(x, y) for rect in self.exclusions):
            return None
        found = [slot for slot, rect in self.regions if rect.contains(x, y)]
        return found[0] if len(found) == 1 else None

    def cards(self, entities):
        """Only confirmed entities become proposals. Unknown cards stay unclickable."""
        lookup = {str(key): value for key, value in entities.items()}
        return tuple(CardSnapshot(slot, lookup[slot], rect) for slot, rect in self.regions
                     if isinstance(lookup.get(slot), SelectionEntity) and lookup[slot].valid)

    def semantic_signature(self, entities):
        """Stable metadata, never an image buffer or a query/round revision."""
        cards = self.cards(entities)
        value = {'layout': self.layout_id,
                 'regions': [(slot, (rect.left, rect.top, rect.right, rect.bottom))
                             for slot, rect in self.regions],
                 'excluded': [(rect.left, rect.top, rect.right, rect.bottom) for rect in self.exclusions],
                 'entities': [(card.slot, card.entity.kind, card.entity.entity_id,
                               card.entity.name, card.entity.category) for card in cards]}
        return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf8')).hexdigest()


def _size(size):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or not all(finite(v) for v in size) or size[0] < 640 or size[1] < 360):
        return None
    return tuple(float(v) for v in size)


def _bounds(points):
    try:
        if len(points) != 4 or any(len(point) != 2 or not all(finite(v) for v in point) for point in points):
            return None
        xs, ys = zip(*points)
        rect = Rect(min(xs), min(ys), max(xs), max(ys))
        return rect if rect.valid else None
    except (TypeError, ValueError):
        return None


def _transform(rect, size, screen_rect):
    if screen_rect is None:
        return rect
    width, height = size
    left, top, right, bottom = screen_rect
    return Rect(left + rect.left * (right - left) / width,
                top + rect.top * (bottom - top) / height,
                left + rect.right * (right - left) / width,
                top + rect.bottom * (bottom - top) / height)


def _screen_valid(screen_rect, size):
    if screen_rect is None:
        return True
    if (not isinstance(screen_rect, (tuple, list)) or len(screen_rect) != 4
            or not all(finite(v) for v in screen_rect)):
        return False
    left, top, right, bottom = screen_rect
    width, height = size
    return (left < right and top < bottom
            and abs(((right - left) / (bottom - top)) / (width / height) - 1) < .025)


def augment_geometry(observation, image_size, *, screen_rect=None):
    """Propose three green-card interiors for the observed 16:9 MuMu layout.

    OCR title boxes anchor horizontal centers; they are never used as click boxes.
    The y range stays inside the card body and above tier/reroll controls.
    """
    size = _size(image_size)
    if (not size or not _screen_valid(screen_rect, size) or not isinstance(observation, dict)
            or observation.get('scene') != 'choice_candidates'
            or observation.get('layout_method') != 'three_refresh_controls'):
        return None
    width, height = size
    if abs(width / height / (16 / 9) - 1) > .025:
        return None
    cards = observation.get('cards')
    if not isinstance(cards, (tuple, list)) or len(cards) != 3:
        return None
    bounds = [_bounds(card.get('box')) if isinstance(card, dict) else None for card in cards]
    if any(rect is None for rect in bounds):
        return None
    slots = [str(card.get('slot')) for card in cards]
    centers = [(rect.left + rect.right) / 2 for rect in bounds]
    ys = [(rect.top + rect.bottom) / 2 for rect in bounds]
    if (slots != ['0', '1', '2'] or not (.18 < centers[0] / width < .31
            and .44 < centers[1] / width < .56 and .69 < centers[2] / width < .82)
            or any(not .30 < y / height < .45 for y in ys)
            or max(ys) - min(ys) > height * .025):
        return None
    regions = tuple((slot, Rect(center - width * .064, height * .22,
                               center + width * .064, height * .56))
                    for slot, center in zip(slots, centers))
    excluded = tuple(Rect(center - width * .045, height * .63,
                          center + width * .045, height * .73) for center in centers)
    excluded += (Rect(width * .425, height * .835, width * .575, height * .955),)
    return GeometryProposal('s18-mumu-green-augments-3-v1', tuple(image_size),
                            tuple((slot, _transform(rect, size, screen_rect)) for slot, rect in regions),
                            tuple(_transform(rect, size, screen_rect) for rect in excluded),
                            'visually reviewed 3840x2160 user frame; click acceptance not validated')


def item_geometry(boxes, image_size, *, category, screen_rect=None):
    """Propose safe card interiors and separate details controls for 3–5 items.

    Uses the actual detected full card rectangles rather than absolute positions
    from the 4:3 recording. Category is supplied by resolved catalogue identities,
    never guessed from these rectangles. A radiant screenshot can establish these
    proposed boundaries, but cannot establish live click/selection acceptance.
    """
    size = _size(image_size)
    if (not size or not _screen_valid(screen_rect, size) or category not in ('completed', 'artifact', 'radiant')
            or not isinstance(boxes, (tuple, list)) or len(boxes) not in (3, 4, 5)):
        return None
    width, height = size
    if any(not isinstance(box, (tuple, list)) or len(box) != 4
           or not all(finite(v) for v in box) for box in boxes):
        return None
    rects = [Rect(*box) for box in boxes]
    if any(not rect.valid or not 0 <= rect.left < rect.right <= width
           or not height * .55 <= rect.top < rect.bottom <= height
           or not .045 < (rect.right - rect.left) / width < .18
           or not .055 < (rect.bottom - rect.top) / height < .23 for rect in rects):
        return None
    widths = [rect.right - rect.left for rect in rects]
    heights = [rect.bottom - rect.top for rect in rects]
    group_center = (rects[0].left + rects[0].right + rects[-1].left + rects[-1].right) / 4 / width
    if (not .44 < group_center < .58
            or max(rect.top for rect in rects) - min(rect.top for rect in rects) > height * .03
            or max(widths) / min(widths) > 1.4 or max(heights) / min(heights) > 1.5
            or any(a.right >= b.left for a, b in zip(rects, rects[1:]))):
        return None
    regions = tuple((str(i), Rect(rect.left + w * .12, rect.top + h * .18,
                                 rect.right - w * .12, rect.bottom - h * .12))
                    for i, (rect, w, h) in enumerate(zip(rects, widths, heights)))
    details = tuple(Rect(rect.left + w * .08, min(height, rect.bottom + h * .035),
                         rect.right - w * .08, min(height, rect.bottom + h * .43))
                    for rect, w, h in zip(rects, widths, heights))
    details = tuple(rect for rect in details if rect.valid)
    return GeometryProposal(f's18-items-{category}-{len(rects)}-v1', tuple(image_size),
                            tuple((slot, _transform(rect, size, screen_rect)) for slot, rect in regions),
                            tuple(_transform(rect, size, screen_rect) for rect in details),
                            'detected card-body proposals; separate details buttons; no click receipt validation')
