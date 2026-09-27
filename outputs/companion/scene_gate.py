"""Cheap permissive refresh-arrow gate; never assigns names or statistics."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

_template=None

def may_be_choice(image):
    global _template
    if _template is None:
        with Image.open(Path(__file__).parent/'assets/refresh-glyph.png') as source:
            _template=np.asarray(source.convert('L')).copy()
    width=960
    height=round(image.height*width/image.width)
    small=np.asarray(image.convert('L').resize((width,height)))
    scores=[]
    for left,right in ((.13,.37),(.40,.64),(.67,.91)):
        region=small[round(height*.6):round(height*.8),round(width*left):round(width*right)]
        if region.shape[0]<_template.shape[0] or region.shape[1]<_template.shape[1]:return False
        scores.append(float(cv2.minMaxLoc(cv2.matchTemplate(region,_template,cv2.TM_CCOEFF_NORMED))[1]))
    # Two glyphs are sufficient to run OCR; OCR must independently validate the scene.
    return sum(score>=.58 for score in scores)>=2
