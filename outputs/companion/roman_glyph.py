"""Conservative separated I/II/III stroke evidence, never character substitution.

Only continuous, near-rectangular light strokes after a clear word gap qualify.
This is optional supporting image evidence, not a general Roman numeral OCR.
"""
from __future__ import annotations
import numpy as np


def _at_threshold(gray, threshold):
    mask=gray>threshold
    ys,xs=np.where(mask)
    if len(xs)<10 or mask.mean()>.45:
        return None
    height=int(ys.max()-ys.min()+1)
    active=np.flatnonzero(mask.any(axis=0))
    groups=np.split(active,np.where(np.diff(active)>1)[0]+1)
    bars=[]
    for group in reversed(groups):
        left,right=int(group[0]),int(group[-1])+1
        part=mask[:,left:right]
        rows=np.flatnonzero(part.any(axis=1))
        top,bottom=int(rows[0]),int(rows[-1])+1
        h=bottom-top
        filled=part[top:bottom]
        if (h<max(8,.65*height) or (right-left)/h>.32
                or filled.mean()<.78 or not filled.any(axis=1).all()):
            break
        if bars and bars[-1][0]-right>.50*height:
            break
        bars.append((left,right,top,bottom))
        if len(bars)>3:return None
    if not bars or len(bars)>=len(groups):return None
    left=min(x[0] for x in bars)
    previous=groups[-len(bars)-1]
    gap=left-int(previous[-1])-1
    if gap<max(3,.18*height):return None
    if max(x[3]-x[2] for x in bars)-min(x[3]-x[2] for x in bars)>2:return None
    return {'roman':'I'*len(bars),'prefix_right':int(previous[-1])+1,'suffix_left':left}


def roman_evidence(crop):
    gray=np.asarray(crop.convert('L'))
    results=[_at_threshold(gray,t) for t in (160,190,215)]
    if any(r is None for r in results):return None
    if len({r['roman'] for r in results})!=1:return None
    if max(r['suffix_left'] for r in results)-min(r['suffix_left'] for r in results)>2:return None
    return results[1]
