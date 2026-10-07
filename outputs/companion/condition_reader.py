"""Read one open game's primary title using the already prepared OCR engine.

This module neither captures the screen nor scans in the background. Supported
proposals are the S18 dark floating title panel, right-side hero detail, and
gold-bordered left inventory detail. Proposals only limit OCR: they never
establish a selected resource.
"""
from collections import Counter
import math
from statistics import median
import time
import unicodedata

import cv2
import numpy as np

from item_vision import item_boxes
from scene_gate import may_be_choice


SUPPORTED_KINDS = ('hero', 'equip', 'hex')
SUPPORTED_EQUIPMENT = frozenset(('基础装备', '成型装备', '神器装备', '光明武器', '转职纹章'))


def _name(value):
    return ''.join(unicodedata.normalize('NFKC', value).split()).casefold() if isinstance(value, str) else ''


def _left_inventory_panels(pixels):
    """Propose the verified S18 inventory panel from its four gold borders.

    The tall recipe list can cross the shop band. Its primary title remains
    above the list, beside the large inventory icon. Require two long aligned
    vertical borders and complete top/bottom borders; never search its body.
    """
    h, w = pixels.shape[:2]
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    gold = ((red >= 70) & (green >= 55) & (blue < 115)
            & (red-green >= 8) & (green-blue >= 15)).astype('uint8')*255
    gold[:, :round(w*.05)] = 0
    gold[:, round(w*.34):] = 0
    vertical = cv2.morphologyEx(gold, cv2.MORPH_OPEN,
                               np.ones((max(3, round(h*.16)) | 1, 1), np.uint8))
    lines = []
    for contour in cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        if 1 < y < h*.045 and h*.16 < bh < h*.95 and bw < w*.02 and y+bh < h*.95:
            lines.append((x, y, x+bw, y+bh))
    proposals = []
    tolerance = max(3, round(h*.01))
    for left in lines:
        if not w*.05 < left[0] < w*.11:
            continue
        for right in lines:
            if not w*.24 < right[0] < w*.34:
                continue
            x1, y1, x2, y2 = left[0], max(left[1], right[1]), right[2], min(left[3], right[3])
            if not w*.20 < x2-x1 < w*.27:
                continue
            if abs(left[1]-right[1]) > tolerance or abs(left[3]-right[3]) > tolerance:
                continue
            if (np.mean(gold[y1, x1:x2] > 0) < .85
                    or np.mean(gold[y2-1, x1:x2] > 0) < .85):
                continue
            proposals.append((x1, y1, x2, y2))
    return proposals


def detail_boxes(image):
    """Bounded dark-panel proposals on the board, below the stage and above shop.

    At most 640 pixels are inspected, independent of a 4K capture. Opening
    disconnects small health bars and avatars from a flat dark panel. No OCR or
    catalogue matching occurs during this proposal step.
    """
    width, height = image.size
    scale = min(1, 640 / width)
    small = image.convert('RGB').resize((round(width*scale), round(height*scale)))
    pixels = np.asarray(small, dtype=np.int16)
    h, w = pixels.shape[:2]
    mask = ((pixels.max(2) < 70) & (pixels.max(2)-pixels.min(2) < 40)).astype('uint8')*255
    close_size = max(3, round(5*w/640)) | 1
    open_size = max(7, round(13*w/640)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_size, close_size), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((open_size, open_size), np.uint8))
    top_limit, bottom_limit = round(h*.07), round(h*.72)
    mask[:top_limit] = 0
    mask[bottom_limit:] = 0
    mask[:, :round(w*.1)] = 0
    boxes = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        left, top, bw, bh = cv2.boundingRect(contour)
        if not (.17*w < bw < .26*w and .15*h < bh < .68*h):
            continue
        if cv2.contourArea(contour)/(bw*bh) < .76:
            continue
        right_hero = left >= .75*w and left+bw >= .98*w
        # Floating panels whose top/body extends outside the inspected board
        # band have no verified title position. Right-side hero panels have a
        # separately verified fixed title band and may meet that crop boundary.
        if not right_hero and (top <= top_limit or top+bh >= bottom_limit):
            continue
        boxes.append(tuple(round(value/scale) for value in (left, top, left+bw, top+bh)))
    boxes.extend(tuple(round(value/scale) for value in rect) for rect in _left_inventory_panels(pixels))
    return sorted(set(boxes))


def _valid_rect(rect, size):
    if not isinstance(rect, (tuple, list)) or len(rect) != 4:
        return None
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in rect):
        return None
    left, top, right, bottom = map(round, rect)
    width, height = size
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        return None
    if right-left > width*.38 or bottom-top > height*.15 or min(right-left, bottom-top) < 8:
        return None
    return left, top, right, bottom


def _title_is_bounded(crop):
    pixels = np.asarray(crop.convert('RGB'), dtype=np.int16)
    ink = (pixels.min(2) > 175) & (pixels.max(2)-pixels.min(2) < 65)
    if np.count_nonzero(ink) < 8:
        return False, 'no_primary_title_strokes'
    # A one-pixel boundary is enough to reject a partially clipped name. False
    # negatives are safer than silently assigning the unclipped prefix's ID.
    if (np.count_nonzero(ink[:, 0]) >= 2 or np.count_nonzero(ink[:, -1]) >= 2
            or np.count_nonzero(ink[0]) >= 3 or np.count_nonzero(ink[-1]) >= 3):
        return False, 'title_touches_boundary'
    return True, ''


def _header_icon_visible(crop):
    pixels = np.asarray(crop.convert('RGB'), dtype=np.int16)
    if min(crop.size) < 6:
        return False
    visible = pixels.max(2) > 150
    return (float(pixels.std()) >= 20 and np.count_nonzero(visible) >= 20
            and np.count_nonzero(visible.sum(1) >= 2) >= crop.height*.5)


def _spaced_item_choices(boxes):
    # The low-level card proposal also catches contiguous shop slots on some
    # video frames. Verified anvil cards have space between their card bodies.
    if len(boxes) not in (3, 4, 5):
        return False
    ordered = sorted(boxes)
    body_width = median(right-left for left, _, right, _ in ordered)
    return min(b[0]-a[0] for a, b in zip(ordered, ordered[1:])) > body_width*1.20


class ConditionReader:
    def __init__(self, vision, resolver):
        self.vision = vision
        self.resolver = resolver
        self.catalogue = [row for kind in SUPPORTED_KINDS for row in resolver.entries(kind)]
        self.names = {_name(row['name']) for row in self.catalogue}

    def read(self, image, trigger_point=None, *, title_rect=None, kind=None, scene_hint=None):
        """Return route/status/entity/candidates/evidence for one frozen frame.

        trigger_point is relative to the captured game canvas, not desktop
        coordinates. title_rect is an explicitly selected primary-title box;
        it is never inferred from a description or remembered mouse position.
        Existing confirmed choice scenes take precedence over detail input.
        """
        started = time.monotonic()
        base = {'scene': 'unknown', 'route': 'none', 'status': 'unknown', 'entity': None,
                'candidates': [], 'evidence': {}, 'records_selected': False,
                'image_size': image.size}

        def result(reason, **values):
            return {**base, 'reason': reason, **values,
                    'elapsed_ms': round((time.monotonic()-started)*1000, 2)}

        width, height = image.size
        if width < 480 or height < 270 or abs(width/height-16/9) > .03:
            return result('detail_layout_unsupported')
        if scene_hint in ('choice_candidates', 'choice_unresolved', 'augment_choice') or may_be_choice(image):
            return result('augment_choice_has_priority', scene='augment_choice', route='augment_stats')
        if scene_hint in ('item_candidates', 'equipment_choice'):
            return result('equipment_choice_has_priority', scene='equipment_choice', route='equipment_stats')
        boxes = item_boxes(image)
        if _spaced_item_choices(boxes):
            top = median(box[1] for box in boxes)
            card_height = median(box[3]-box[1] for box in boxes)
            header_rect = tuple(round(value) for value in (width*.4, top-card_height*.48, width*.6, top-card_height*.08))
            readings = self.vision.read_name(image.crop(header_rect), [{'id': '1', 'name': '选择一件'}]).get('readings', [])
            if sum(_name(value) == '选择一件' for value in readings) >= 2:
                return result('equipment_choice_has_priority', scene='equipment_choice', route='equipment_stats')
            # A possible choice layout with an unreadable header cannot fall
            # through to a detail query. The existing item analyser will decide
            # whether it can display ranks; this route does not authorise IDs.
            return result('equipment_choice_header_unconfirmed', scene='equipment_choice', route='equipment_stats')
        if kind is not None and kind not in SUPPORTED_KINDS:
            return result('detail_kind_unsupported')
        popup_rect = None
        headers = []
        if title_rect is not None:
            area = _valid_rect(title_rect, image.size)
            if not area:
                return result('invalid_primary_title_rectangle')
            layout = 'explicit_primary_title'
        else:
            panels = detail_boxes(image)
            if len(panels) > 1:
                if (isinstance(trigger_point, (tuple, list)) and len(trigger_point) == 2
                        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in trigger_point)):
                    x, y = trigger_point
                    panels = [rect for rect in panels if rect[0] < x < rect[2] and rect[1] < y < rect[3]]
                if len(panels) != 1:
                    return result('multiple_detail_panels')
            if not panels:
                return result('no_verified_detail_panel')
            popup_rect = panels[0]
            left, top, right, bottom = popup_rect
            if left >= width*.75 and right >= width*.98:
                # Fixed hero detail title, excluding its star tab, item/skill
                # names below, sale price and range/role labels on the right.
                panel_width = right-left
                area = tuple(round(value) for value in (width*.834, top+panel_width*.105,
                                                       width*.929, top+panel_width*.225))
                kind, layout = 'hero', 's18_right_hero_detail'
                icon_rect = tuple(round(value) for value in (width*.796, area[1], width*.834,
                                                            area[1]+panel_width*.20))
                headers.append((layout, area, icon_rect))
            else:
                bw = right-left
                area = tuple(round(value) for value in (left+bw*.28, top+bw*.025, right-bw*.025, top+bw*.24))
                layout = 's18_floating_icon_title'
                if left < width*.11 and top < height*.045 and right < width*.34:
                    kind, layout = 'equip', 's18_left_inventory_detail'
                icon_rect = tuple(round(value) for value in (left+bw*.035, top+bw*.035,
                                                            left+bw*.255, top+bw*.27))
                headers.append((layout, area, icon_rect))
                if layout == 's18_floating_icon_title':
                    # Native MuMu equipment popups have a larger header icon.
                    # The older video layout clips its right edge into the
                    # title and misses part of the icon. Keep both bounded
                    # header layouts; never search stats or the wearer below.
                    title = tuple(round(value) for value in (left+bw*.35, top+bw*.07,
                                                            left+bw*.97, top+bw*.18))
                    icon = tuple(round(value) for value in (left+bw*.07, top+bw*.07,
                                                           left+bw*.32, top+bw*.32))
                    headers.append(('s18_floating_large_icon_title', title, icon))
            valid = []
            for header_layout, title, icon in headers:
                if not _header_icon_visible(image.crop(icon)):
                    reason = 'detail_header_icon_unconfirmed'
                else:
                    bounded, reason = _title_is_bounded(image.crop(title))
                    if bounded:
                        valid.append((header_layout, title, icon))
                evidence = {'layout': header_layout, 'popup_rect': popup_rect,
                            'icon_rect': icon, 'title_rect': title, 'readings': []}
            if not valid:
                return result(reason, evidence=evidence)
            # Preserve the previously verified crop when both layouts fit.
            layout, area, icon_rect = valid[0]
        bounded, reason = _title_is_bounded(image.crop(area))
        evidence = {'layout': layout, 'title_rect': area, 'popup_rect': popup_rect, 'readings': []}
        if not bounded:
            return result(reason, evidence=evidence)
        catalogue = self.resolver.entries(kind) if kind else self.catalogue
        observed = self.vision.read_name(image.crop(area), catalogue)
        readings = observed.get('readings', [])
        evidence['readings'] = readings
        counts = Counter(_name(value) for value in readings if _name(value) in self.names)
        if len(counts) != 1 or next(iter(counts.values()), 0) < 2:
            return result('primary_title_unconfirmed', evidence=evidence)
        title = next(value for value in readings if _name(value) == next(iter(counts)))
        resolution = self.resolver.resolve(kind, title) if kind else self.resolver.resolve_any(title)
        if resolution.kind not in SUPPORTED_KINDS and resolution.status != 'ambiguous':
            return result('detail_kind_unsupported', evidence=evidence)
        if resolution.confirmed and resolution.kind == 'equip' and resolution.entity.get('type') not in SUPPORTED_EQUIPMENT:
            return result('equipment_category_unsupported', evidence=evidence)
        return result(resolution.reason or 'primary_title', scene='condition_detail', route='detail',
                      status=resolution.status, entity=resolution.entity,
                      candidates=list(resolution.candidates), evidence=evidence)


def analyze_condition(image, vision, catalogue, trigger_point=None, **options):
    from entity_identity import EntityResolver
    return ConditionReader(vision, EntityResolver(catalogue)).read(image, trigger_point, **options)
