"""Bottom item choices: locate repeated cards, then verify exact catalogue names.

The detector accepts three to five cards. It deliberately does not infer item
identity from a similar icon or substitute a normal item for a radiant item.
"""
from __future__ import annotations
from statistics import median
import time
import cv2
import numpy as np
from PIL import Image
from vision import TextSignature


ITEM_TYPES = frozenset(('成型装备', '神器装备', '光明武器'))


def item_boxes(image):
    """Cheap scene proposal only; brown cards alone never authorize statistics."""
    width, height = image.size
    if width < 640 or height < 360:
        return []
    scale = min(1, 960/width)
    small = image.convert('RGB').resize((round(width*scale), round(height*scale)), Image.Resampling.BILINEAR)
    pixels = np.asarray(small, dtype=np.int16)
    h, w = pixels.shape[:2]
    mask = ((pixels[:,:,0]-pixels[:,:,2] > 15) & (pixels[:,:,1]-pixels[:,:,2] > 7)
            & (pixels[:,:,0] < 140) & (pixels[:,:,1] < 130)).astype('uint8')*255
    mask[:round(h*.55)] = 0
    mask[:,:round(w*.12)] = 0
    mask[:,round(w*.9):] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
    candidates = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        if .06*w < bw < .17*w and .065*h < bh < .20*h and .55 < bw/bh < 1.6:
            candidates.append((x,y,bw,bh))
    def aligned_groups(rects):
        groups = []
        for anchor in rects:
            group = sorted([b for b in rects if abs(b[1]-anchor[1]) < .018*h
                            and abs(b[2]-anchor[2]) < .025*w and abs(b[3]-anchor[3]) < .04*h])
            if len(group) not in (3,4,5):
                continue
            gaps = [b[0]-a[0] for a,b in zip(group,group[1:])]
            if min(gaps) > median(b[2] for b in group) and max(gaps)-min(gaps) < .025*w:
                if group not in groups:groups.append(group)
        return groups
    groups = aligned_groups(candidates)
    if not groups:
        # A selection animation can tint the brown card interiors green. Recover
        # their outlines, but still require the header and exact item names below.
        edges = cv2.Canny(np.asarray(small.convert('L')),25,70)
        edges[:round(h*.55)] = 0
        edges[:,:round(w*.12)] = 0
        edges[:,round(w*.9):] = 0
        for contour in cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh = cv2.boundingRect(contour)
            if .06*w < bw < .17*w and .065*h < bh < .20*h and .55 < bw/bh < 1.6:
                candidates.append((x,y,bw,bh))
        distinct = []
        for box in sorted(candidates,key=lambda b:b[2]*b[3],reverse=True):
            if not any(abs(box[0]+box[2]/2-b[0]-b[2]/2)<min(box[2],b[2])*.35
                       and abs(box[1]+box[3]/2-b[1]-b[3]/2)<min(box[3],b[3])*.6 for b in distinct):
                distinct.append(box)
        groups = aligned_groups(distinct)
    if len(groups) != 1:
        return []
    return [(round(x/scale),round(y/scale),round((x+bw)/scale),round((y+bh)/scale))
            for x,y,bw,bh in groups[0]]


def analyze_items(image, vision, catalogue):
    start = time.monotonic()
    boxes = item_boxes(image)
    result = {'scene':'unknown','cards':[], 'image_size':image.size,'reason':'no_item_cards'}
    if not boxes:
        return result
    heights = [b[3]-b[1] for b in boxes]
    top = median(b[1] for b in boxes)
    card_height = median(heights)
    # The common header sits directly above the cards, regardless of their count.
    header = image.crop((round(image.width*.4),round(top-card_height*.48),
                         round(image.width*.6),round(top-card_height*.08)))
    header_result = vision.read_name(header, [{'id':'1','name':'选择一件'}])
    if header_result['status'] != 'resolved':
        return {**result,'reason':'item_header_unconfirmed'}
    cards = []
    for slot, (left,upper,right,bottom) in enumerate(boxes):
        height = bottom-upper
        text_box = (left,round(upper+height*.44),right,round(upper+height*.68))
        resolution = vision.read_name(image.crop(text_box), catalogue)
        supported = (resolution['status']=='resolved'
                     and resolution['candidates'][0].get('type') in ITEM_TYPES)
        if resolution['status']=='resolved' and not supported:
            resolution = {**resolution,'status':'excluded','excluded_id':resolution['id']}
            resolution.pop('id',None)
        cards.append({'slot':slot,'box':[[left,upper],[right,upper],[right,bottom],[left,bottom]],
                      'text_rect':text_box,'resolution':resolution})
    confirmed = sum(c['resolution']['status']=='resolved' for c in cards)
    excluded = sum(c['resolution']['status']=='excluded' for c in cards)
    # A non-item selection, or a mixture including a confirmed excluded entity,
    # must not be treated as a standard item anvil.
    scene = 'item_candidates' if confirmed>=2 and excluded==0 else 'unknown'
    return {**result,'scene':scene,'cards':cards,'reason':'item_titles' if scene!='unknown' else 'excluded_or_unconfirmed',
            'elapsed_ms':round((time.monotonic()-start)*1000,2)}


def item_signature(image, boxes):
    """Stable title/header strokes, excluding card glow and our overlay region."""
    if not boxes:return TextSignature(())
    top=median(b[1] for b in boxes);height=median(b[3]-b[1] for b in boxes)
    regions=[(image.width*.4,top-height*.48,image.width*.6,top-height*.08)]
    regions.extend((l,t+(b-t)*.44,r,t+(b-t)*.68) for l,t,r,b in boxes)
    masks=[]
    for region in regions:
        crop=image.crop(tuple(round(v) for v in region)).convert('RGB')
        crop=crop.resize((180,max(8,round(crop.height*180/crop.width))),Image.Resampling.BILINEAR)
        rgb=np.asarray(crop,dtype=np.int16)
        masks.append((rgb.min(axis=2)>180)&(rgb.max(axis=2)-rgb.min(axis=2)<70))
    return TextSignature(tuple(masks))


def same_item_text(current, previous):
    """Allow sparse compression noise, while invalidating a changed single slot.

    On consecutive original 720P frames, up to four isolated bright pixels can
    appear/disappear without a title changing. A one-pixel stroke expansion and
    five-pixel noise budget apply to each title separately, never the full frame.
    """
    if not current or not previous or len(current.masks)!=len(previous.masks):return False
    kernel=np.ones((3,3),np.uint8)
    for a,b in zip(current.masks,previous.masks):
        if a.shape!=b.shape or min(np.count_nonzero(a),np.count_nonzero(b))<8:return False
        expanded_a=cv2.dilate(a.astype('uint8'),kernel).astype(bool)
        expanded_b=cv2.dilate(b.astype('uint8'),kernel).astype(bool)
        if np.count_nonzero(a & ~expanded_b)>5 or np.count_nonzero(b & ~expanded_a)>5:return False
    return bool(current.masks)


def capture_item_region(binding):
    """Read only the lower game region; pad coordinates without desktop capture."""
    import mss
    import win_capture as win
    current=win.describe(binding.hwnd)
    if win.capture_block_reason(binding,current,win.foreground_root()):
        raise RuntimeError('item_not_foreground')
    left,top,right,bottom=current.rect
    width,height=right-left,bottom-top
    offset=round(height*.55)
    with mss.mss() as screen:
        shot=screen.grab({'left':left,'top':top+offset,'width':width,'height':height-offset})
    after=win.describe(binding.hwnd)
    if (win.capture_block_reason(binding,after,win.foreground_root())
        or current.rect!=after.rect or current.dpi!=after.dpi):
        raise RuntimeError('item_window_changed')
    image=Image.new('RGB',(width,height))
    image.paste(Image.frombytes('RGB',shot.size,shot.rgb),(0,offset))
    return image,after
