"""Local-only OCR. Multiple pixel views preserve suffixes instead of rewriting them."""
from __future__ import annotations
import time
import re
import hashlib
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageOps, ImageStat, ImageFilter
import bootstrap
from choice_reader import read_choice, bounds, normalize_name
from ocr_baseline import build_engine
from core import resolve_name, description_terms, resolve_description
from hex_family import FamilyNameResolver
from hex_quality import read_hex_quality
from roman_glyph import roman_evidence
from scene_gate import may_be_choice


def confident_round(result):
    """Use digit confidences, excluding a decorative icon, without rewriting text."""
    if not result.txts or not getattr(result, 'word_results', None):
        return None
    text = result.txts[0]
    info = result.word_results[0]
    chars = ''.join(''.join(group) for group in info.words)
    scores = info.confs
    matches = list(re.finditer(r'(?<!\d)([1-9]-[1-9])(?!\d)', text))
    if chars != text or len(chars) != len(scores) or len(matches) != 1:
        return None
    match = matches[0]
    confidence = [float(v) for v in scores[match.start():match.end()]]
    if min(confidence) < .85:
        return None
    return {'value': match.group(), 'character_confidences': confidence}


def name_views(crop):
    crop = crop.convert('RGB')
    large = crop.resize((crop.width*2, crop.height*2), Image.Resampling.LANCZOS)
    return [crop, large, ImageOps.autocontrast(ImageOps.grayscale(large)).convert('RGB')]


def _may_have_roman_suffix(readings, catalog):
    """Route extra pixel reads; a catalog family never supplies an identity.

    The recognizer can drop a thin suffix or read it as punctuation/digits.
    Keep those observations unchanged: only new, complete exact OCR reads can
    pass resolve_name. The base must match literally, including punctuation.
    """
    titles = [normalize_name(value) for value in readings if value]
    for row in catalog:
        family = re.fullmatch(r'(.+?)(I{1,3})(\+{0,2})', normalize_name(row.get('name', '')))
        if family:
            base = family[1]
            if any(value.startswith(base) and re.fullmatch(r'[Ii1l!|+]*', value[len(base):])
                   for value in titles):
                return True
    return False


class Vision:
    def __init__(self):
        self.engine = None

    def prepare(self):
        if self.engine is None:self.engine,_=build_engine()

    def read_round_crop(self,crop):
        self.prepare();values=[]
        for view in name_views(crop)[:2]:
            result=self.engine(np.asarray(view.convert('RGB'))[:,:,::-1].copy(),use_det=False,use_cls=False,return_word_box=False)
            value=result.txts[0].strip() if result.txts and result.scores[0]>=.9 else ''
            values.append(value if re.fullmatch(r'[1-9]-[1-9]',value) else None)
        return values[0] if values[0] and values[0]==values[1] else None

    def analyze_fast(self,image,catalog):
        """Verified 16:9 MuMu layout. No full-screen detector in the live path."""
        start=time.monotonic();w,h=image.size
        base={'scene':'unknown','round':None,'cards':[],'image_size':image.size}
        if abs(w/h-16/9)>.03 or w<1280:
            return {**base,'reason':'fast_layout_unsupported','elapsed_ms':0}
        if not may_be_choice(image):
            return {**base,'reason':'no_refresh_glyphs','elapsed_ms':round((time.monotonic()-start)*1000,2)}
        def rect(l,t,r,b):return (round(l*w),round(t*h),round(r*w),round(b*h))
        def box(r):
            x,y,x2,y2=r;return [[x,y],[x2,y],[x2,y2],[x,y2]]
        stage_rect=rect(.344,.008,.374,.043)
        stage=self.read_round_crop(image.crop(stage_rect))
        cards=[]
        frame_family_resolver=None
        def family_context():
            nonlocal frame_family_resolver
            if frame_family_resolver is None:
                frame_family_resolver=FamilyNameResolver(catalog)
            return frame_family_resolver
        for i,cx in enumerate((.236,.499,.761)):
            # Live titles extend below .382h; clipping their lower strokes can
            # turn 赐 into 喝 and remove a Roman quality suffix. Keep the whole
            # title above the description region, without changing OCR matching.
            area=rect(cx-.09,.34,cx+.09,.39)
            quality={'status':'unknown','level':None,'reason':'no_reviewed_family'}
            def quality_context():
                quality.update(read_hex_quality(image.crop(rect(cx-.055,.14,cx+.055,.31))))
                return quality
            result=self.read_name(image.crop(area),catalog,_quality_context=quality_context,
                                  _family_context=family_context)
            description=None
            if result['status']=='ambiguous' and any(description_terms(result['candidates'])):
                description=rect(cx-.085,.395,cx+.085,.505)
                result=self.read_description(image.crop(description),result)
            readings=[s for s in result['readings'] if s]
            raw=result.get('name') or (max(set(readings),key=readings.count) if readings else '未确认选项')
            cards.append({'slot':i,'raw_text':raw,'box':box(area),'resolution':result})
            cards[-1]['quality']=quality
            if description:cards[-1]['description_box']=box(description)
        confirmed=sum(c['resolution']['status']=='resolved' for c in cards)
        return {**base,'scene':'choice_candidates' if confirmed>=1 else 'choice_unresolved',
                'round':stage,'cards':cards,'round_box':box(stage_rect),'header_box':None,
                'layout_method':'three_refresh_controls','reason':'fast_mumu_layout',
                'elapsed_ms':round((time.monotonic()-start)*1000,2)}

    def read_description(self,crop,resolution):
        # Read only text bands, avoiding a costly full-screen detection pass.
        pixels=np.asarray(crop.convert('RGB'))
        mask=(pixels.min(axis=2)>180)&((pixels.max(axis=2)-pixels.min(axis=2))<55)
        ys=np.flatnonzero(mask.sum(axis=1)>5)
        if not len(ys):return resolution
        bands=np.split(ys,np.where(np.diff(ys)>3)[0]+1)
        readings=['','']
        for band in bands[:6]:
            if len(band)<10:continue
            line=crop.crop((0,max(0,int(band[0])-3),crop.width,min(crop.height,int(band[-1])+4)))
            for index,factor in enumerate((1,1.3)):
                view=line.resize((round(line.width*factor),line.height),Image.Resampling.BICUBIC)
                result=self.engine(np.asarray(view)[:,:,::-1].copy(),use_det=False,use_cls=False,return_word_box=False)
                if result.txts and result.scores[0]>=.95:readings[index]+=result.txts[0]
        return {**resolve_description(resolution,readings),'description_readings':readings}

    def read_name(self, crop, catalog, *, quality=None, _family_context=None, _quality_context=None):
        if self.engine is None:
            self.engine, _ = build_engine()
        seen_title_pixels=set()
        family_readings=[]
        family_resolver=None
        quality_checked=quality is not None

        def read_title(view, *, unique=False):
            pixels=np.asarray(view)[:,:,::-1].copy()
            signature=(pixels.shape,hashlib.sha256(pixels).digest())
            repeated=signature in seen_title_pixels
            if unique and signature in seen_title_pixels:
                return None
            seen_title_pixels.add(signature)
            result=self.engine(pixels,use_det=False,use_cls=False,return_word_box=False)
            if ((quality is not None or _quality_context is not None) and not repeated and result.txts
                    and result.scores[0]>=.90):
                family_readings.append(result.txts[0])
            return result

        readings = []
        def family_result():
            nonlocal family_resolver,quality,quality_checked
            if quality is None and (_quality_context is None or quality_checked):
                return None
            if family_resolver is None:
                if not FamilyNameResolver.has_family_readings(readings):
                    return None
                if not quality_checked:
                    measured=_quality_context()
                    quality_checked=True
                    quality=measured['level'] if measured['status']=='confirmed' else None
                    if quality is None:
                        return None
                family_resolver=(_family_context() if _family_context is not None
                                 else FamilyNameResolver(catalog))
            result=family_resolver.resolve(family_readings,quality,observed_readings=readings)
            return {**result,'readings':list(readings)} if result is not None else None

        for view in name_views(crop):
            result = read_title(view)
            readings.append(result.txts[0] if result.txts and result.scores[0] >= .90 else '')
        # Always acquire the initial three views before accepting a new route.
        # All complete trusted titles veto; only distinct pixels supply votes.
        family=family_result()
        if family is not None:return family
        resolution=resolve_name(readings,catalog)
        if resolution['status']=='unrecognized':
            # Tight white title strokes avoid wide background and thin punctuation.
            pixels=np.asarray(crop.convert('RGB'))
            mask=(pixels.min(axis=2)>175)&((pixels.max(axis=2)-pixels.min(axis=2))<55)
            yy,xx=np.where(mask)
            if len(xx)>=8:
                tight=crop.crop((max(0,int(xx.min())-4),max(0,int(yy.min())-4),
                                 min(crop.width,int(xx.max())+5),min(crop.height,int(yy.max())+5)))
                binary=ImageOps.grayscale(tight).point(lambda value:255 if value>200 else 0).convert('RGB')
                retries=[]
                for view in (binary,ImageOps.invert(binary)):
                    result=read_title(view)
                    retries.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                supported=resolve_name(retries,catalog)
                combined=resolve_name(readings+retries,catalog)
                readings+=retries
                family=family_result()
                if family is not None:return family
                if supported['status']=='resolved' and combined['status']=='resolved':
                    resolution={**combined,'method':'tight_binary_two_views'}
                elif combined['status'] in ('conflict','ambiguous'):
                    resolution=combined
                if resolution['status']=='unrecognized':
                    # Thin suffixes can disappear at the recognizer's fixed height.
                    # Require two direct OCR matches; never replace 1/l with I.
                    widened=[]
                    for factor in (1.3,1.6):
                        view=tight.resize((round(tight.width*factor),tight.height),Image.Resampling.BICUBIC)
                        result=read_title(view)
                        widened.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                    supported=resolve_name(widened,catalog)
                    combined=resolve_name(readings+widened,catalog)
                    readings+=widened
                    family=family_result()
                    if family is not None:return family
                    if combined['status']=='resolved':
                        # Exact agreement may span a binary and a wider color
                        # view; both are direct reads with the same confidence
                        # threshold. Requiring one retry pair to agree loses
                        # valid consensus already present across these views.
                        resolution={**combined,'method':'tight_wide_two_views'}
                    elif combined['status'] in ('conflict','ambiguous'):
                        resolution=combined
                    elif combined['status']=='unrecognized' and len(combined.get('candidates',[]))==1:
                        # One complete catalog title is evidence to try one
                        # independent color crop, not authority to assign its ID.
                        # Avoid extra reads for missing catalog names or conflicts.
                        result=read_title(tight)
                        readings.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                        family=family_result()
                        if family is not None:return family
                        confirmed=resolve_name(readings,catalog)
                        if confirmed['status']=='resolved':
                            resolution={**confirmed,'method':'tight_color_two_views'}
                        elif confirmed['status'] in ('conflict','ambiguous'):
                            resolution=confirmed
                        elif len(confirmed.get('candidates',[]))==1:
                            # Short titles can still lose confidence at native
                            # width. A different resampler supplies independent
                            # pixels, not a second vote for the first OCR output.
                            view=tight.resize((round(tight.width*1.6),tight.height),Image.Resampling.LANCZOS)
                            result=read_title(view)
                            readings.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                            family=family_result()
                            if family is not None:return family
                            confirmed=resolve_name(readings,catalog)
                            if confirmed['status']=='resolved':
                                resolution={**confirmed,'method':'tight_color_resampled_two_views'}
                            elif confirmed['status'] in ('conflict','ambiguous'):
                                resolution=confirmed
            elif resolution['status']=='unrecognized':
                # An inactive card can dim every title stroke below the white
                # threshold. Require neutral local edges before trying relative
                # contrast; flat lighting and texture supply no title evidence.
                dim_mask=_text_strokes(crop.convert('RGB'))
                _,dim_x=np.where(dim_mask)
                if len(dim_x)>=8:
                    # Keep the title band's vertical context: trimming to its
                    # stroke height can add/remove a thin Roman suffix in OCR.
                    # Horizontal context scales with the input title band.
                    context=max(4,round(crop.height*.075))
                    dim=crop.crop((max(0,int(dim_x.min())-context),0,
                                   min(crop.width,int(dim_x.max())+context+1),crop.height))
                    retries=[]
                    for view in (dim,ImageOps.autocontrast(ImageOps.grayscale(dim)).convert('RGB')):
                        result=read_title(view)
                        retries.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                    readings+=retries
                    family=family_result()
                    if family is not None:return family
                    combined=resolve_name(readings,catalog)
                    if combined['status']=='resolved':
                        resolution={**combined,'method':'dim_context_two_views'}
                    elif combined['status'] in ('conflict','ambiguous'):
                        resolution=combined
        if resolution['status']=='unrecognized' and _may_have_roman_suffix(readings,catalog):
            # A suffix needs context above/below its serifs. The old tight
            # crop can turn I into !/1; a whole-height band can make short
            # titles too small. Retain a proportional margin around ALL ink,
            # then read the complete title twice without changing characters.
            pixels=np.asarray(crop.convert('RGB'))
            mask=(pixels.min(axis=2)>175)&((pixels.max(axis=2)-pixels.min(axis=2))<55)
            yy,xx=np.where(mask)
            if len(xx)>=8:
                horizontal=max(4,round(crop.height*.075))
                vertical=max(4,round(crop.height*.11))
                context=crop.crop((max(0,int(xx.min())-horizontal),
                                   max(0,int(yy.min())-vertical),
                                   min(crop.width,int(xx.max())+horizontal+1),
                                   min(crop.height,int(yy.max())+vertical+1)))
                for view in (context,ImageOps.autocontrast(ImageOps.grayscale(context)).convert('RGB')):
                    # An unchanged crop or binary-looking title can repeat an
                    # earlier input exactly. Never count that as new evidence.
                    result=read_title(view,unique=True)
                    if result is None:
                        continue
                    readings.append(result.txts[0] if result.txts and result.scores[0]>=.90 else '')
                combined=resolve_name(readings,catalog)
                family=family_result()
                if family is not None:return family
                if combined['status']=='resolved':
                    resolution={**combined,'method':'roman_title_context_two_views'}
                elif combined['status'] in ('conflict','ambiguous'):
                    resolution=combined
        glyph=roman_evidence(crop)
        if glyph and resolution['status']=='unrecognized':
            prefix=crop.crop((0,0,glyph['prefix_right']+2,crop.height))
            suffix_readings=[]
            for view in name_views(prefix)[:2]:
                result=self.engine(np.asarray(view)[:,:,::-1].copy(),use_det=False,use_cls=False,return_word_box=False)
                suffix_readings.append(result.txts[0].strip()+' '+glyph['roman']
                                       if result.txts and result.scores[0]>=.95 else '')
            supported=resolve_name(suffix_readings,catalog)
            if supported['status']=='resolved':
                # I, lower-case l and a vertical bar can be visually identical.
                # Preserve a useful suggestion without authorizing automatic stats.
                resolution={'status':'needs_confirmation','suggested_id':supported['id'],
                            'name':supported['name'],'candidates':supported['candidates'],
                            'method':'separated_roman_strokes','glyph':glyph,
                            'prefix_readings':suffix_readings}
        if resolution['status']=='unrecognized':
            # Classify the complete evidence, including retries spread across
            # groups, without granting any identity a previous gate rejected.
            classified=resolve_name(readings,catalog)
            if classified['status']=='unrecognized':
                for key in ('reason','consensus_title','consensus_read_count'):
                    resolution.pop(key,None)
                    if key in classified:resolution[key]=classified[key]
        return {**resolution,'readings':readings}

    def analyze(self, image, catalog):
        start = time.monotonic()
        if not may_be_choice(image):
            return {'scene':'unknown','reason':'no_refresh_glyphs','round':None,'cards':[],
                    'elapsed_ms':round((time.monotonic()-start)*1000,2),'image_size':image.size}
        if self.engine is None:
            self.engine, _ = build_engine()
        start = time.monotonic()
        result = self.engine(np.asarray(image.convert('RGB'))[:,:,::-1].copy(),use_det=True,use_cls=False,return_word_box=False)
        records = []
        if result.txts:
            records = [{'text':text,'score':float(score),'box':box.tolist()}
                       for text,score,box in zip(result.txts,result.scores,result.boxes)]
        observation = read_choice(records,image.size)
        if observation['scene']!='unknown' and observation['round'] is None:
            candidates=[]
            for row in records:
                x1,y1,x2,y2=bounds(row)
                if not (.2*image.width<(x1+x2)/2<.65*image.width and y2<.09*image.height):continue
                if not re.search(r'[1-9]-[1-9]',row['text']):continue
                crop=image.crop((int(x1),int(y1),int(x2),int(y2)))
                values=[]
                for view in name_views(crop)[:2]:
                    retry=self.engine(np.asarray(view)[:,:,::-1].copy(),use_det=False,use_cls=False,return_word_box=True)
                    value=confident_round(retry)
                    if value: values.append(value)
                if len(values)==2 and values[0]['value']==values[1]['value']:
                    candidates.append((values,row['box']))
            if len(candidates)==1:
                values,box=candidates[0]
                observation['round']=values[0]['value'];observation['round_box']=box
                observation['round_method']='character_confidence_two_views'
                observation['round_evidence']=values
        for card in observation['cards']:
            x1,y1,x2,y2 = bounds(card)
            crop = image.crop((max(0,int(x1)-10),max(0,int(y1)-6),min(image.width,int(x2)+10),min(image.height,int(y2)+6)))
            card['resolution'] = self.read_name(crop,catalog)
            if card['resolution']['status']=='unrecognized':
                # On small text, six pixels of padding can include the description
                # line below the title. Retry a tighter box without altering glyphs.
                tight=image.crop((max(0,int(x1)-2),max(0,int(y1)-2),
                                  min(image.width,int(x2)+2),min(image.height,int(y2)+2)))
                retry=self.read_name(tight,catalog)
                readings=card['resolution']['readings']+retry['readings']
                combined=resolve_name(readings,catalog)
                if combined['status']=='resolved' and retry['status']=='resolved':
                    card['resolution']={**combined,'readings':readings,'method':'tight_title_retry'}
        return {**observation,'elapsed_ms':round((time.monotonic()-start)*1000,2),'image_size':image.size}


def capture_image(binding):
    import mss
    import win_capture as win
    before = win.describe(binding.hwnd)
    reason = win.capture_block_reason(binding,before,win.foreground_root())
    if reason:
        raise RuntimeError(reason)
    left,top,right,bottom = before.rect
    with mss.mss() as screen:
        shot = screen.grab({'left':left,'top':top,'width':right-left,'height':bottom-top})
    after = win.describe(binding.hwnd)
    if win.capture_block_reason(binding,after,win.foreground_root()) or before.rect!=after.rect or before.dpi!=after.dpi:
        raise RuntimeError('截图期间窗口变化')
    image = Image.frombytes('RGB',shot.size,shot.rgb)
    if max(ImageStat.Stat(image.resize((128,72))).stddev)<2:
        raise RuntimeError('黑屏或纯色帧')
    return image, after


def capture_stage(binding):
    """Capture only the verified MuMu round digit rectangle, never a full screen."""
    import mss
    import win_capture as win
    current=win.describe(binding.hwnd)
    if win.capture_block_reason(binding,current,win.foreground_root()):raise RuntimeError('stage_not_foreground')
    left,top,right,bottom=current.rect;w=right-left;h=bottom-top
    if abs(w/h-16/9)>.03:raise RuntimeError('stage_layout_unsupported')
    rect={'left':left+round(w*.344),'top':top+round(h*.008),
          'width':round(w*.374)-round(w*.344),'height':round(h*.043)-round(h*.008)}
    with mss.mss() as screen:shot=screen.grab(rect)
    after=win.describe(binding.hwnd)
    if win.capture_block_reason(binding,after,win.foreground_root()) or current.rect!=after.rect:raise RuntimeError('stage_window_changed')
    return Image.frombytes('RGB',shot.size,shot.rgb)


def scene_signature(image):
    # Broad selection region; animations can cause conservative suppression.
    width,height=image.size
    return np.asarray(image.crop((int(width*.08),0,int(width*.94),int(height*.72)))
                      .convert('L').resize((640,360)),dtype=np.int16)


@dataclass
class TextSignature:
    masks: tuple


def _expanded(mask):
    padded=np.pad(mask,1)
    return np.logical_or.reduce([padded[y:y+mask.shape[0],x:x+mask.shape[1]]
                                 for y in range(3) for x in range(3)])


def unchanged(a,b):
    if isinstance(a,TextSignature) or isinstance(b,TextSignature):
        if not isinstance(a,TextSignature) or not isinstance(b,TextSignature) or len(a.masks)!=len(b.masks):
            return False
        for previous,current in zip(a.masks,b.masks):
            if previous.shape!=current.shape or min(np.count_nonzero(previous),np.count_nonzero(current))<8:
                return False
            # Compression moves stroke edges; separated new strokes must invalidate.
            if np.count_nonzero(previous & ~_expanded(current))>2 or np.count_nonzero(current & ~_expanded(previous))>2:
                return False
        return bool(a.masks)
    if a is None or b is None or a.shape!=b.shape:
        return False
    # A global average hides a changed short title among many background pixels.
    # Local pixel changes invalidate conservatively, including animation false positives.
    difference=np.abs(a-b)
    return int(np.count_nonzero(difference>12)) < 16 and float(np.mean(difference)) < .15


def _text_strokes(region):
    """Neutral foreground with both regional and local contrast evidence."""
    gray=region.convert('L')
    brightness=np.asarray(gray,dtype=np.int16)
    rgb=np.asarray(region,dtype=np.int16)
    background=float(np.median(brightness))
    peak=float(np.percentile(brightness,99))
    contrast=peak-background
    # Beige live titles can peak below 200 after downsampling. A relative
    # threshold recovers their strokes; insufficient contrast stays empty.
    if contrast<max(40,.8*background):return np.zeros(brightness.shape,dtype=bool)
    low=np.asarray(gray.filter(ImageFilter.MinFilter(3)),dtype=np.int16)
    high=np.asarray(gray.filter(ImageFilter.MaxFilter(3)),dtype=np.int16)
    mask=((brightness>=background+.6*contrast)&(high-low>=max(24,.35*contrast))
          &((rgb.max(axis=2)-rgb.min(axis=2))<80))
    # Smooth lighting has no local edges; dense texture is not title evidence.
    if np.count_nonzero(mask)>.35*mask.size:return np.zeros(mask.shape,dtype=bool)
    return mask


def tracked_signature(image,observation):
    """Development guard: supported text strokes, excluding animated borders."""
    width,height=image.size
    header=observation.get('header_box')
    regions=[(min(p[0] for p in header)-1,min(p[1] for p in header)-1,
              max(p[0] for p in header)+1,max(p[1] for p in header)+1)] if header else [(width*.22,height*.04,width*.78,height*.14)]
    if not header and observation.get('layout_method')=='three_refresh_controls':
        regions=[]  # This layout has no header; do not track animated card icons.
    if observation.get('round_box'):
        points=observation['round_box']
        regions.append((min(p[0] for p in points)-6,min(p[1] for p in points)-4,
                        max(p[0] for p in points)+6,max(p[1] for p in points)+4))
    for card in observation.get('cards',[]):
        if card.get('description_box'):
            points=card['description_box']
            regions.append((min(p[0] for p in points),min(p[1] for p in points),
                            max(p[0] for p in points),max(p[1] for p in points)))
        x1,y1,x2,y2=bounds(card)
        center=(x1+x2)/2
        half=max(width*.09,(x2-x1)/2+2)
        regions.append((center-half,y1-1,center+half,y2+1))
    scale=640/width
    normalized_height=round(height*scale)
    source=image if image.mode=='RGB' else image.convert('RGB')
    vectors=[]
    for left,top,right,bottom in regions:
        # Preserve the original 640-wide sampling grid, but resample only the
        # small text regions. PIL's box keeps the Lanczos support at ROI edges.
        l,t=max(0,round(left*scale)),max(0,round(top*scale))
        r,b=min(640,round(right*scale)),min(normalized_height,round(bottom*scale))
        if r<=l or b<=t:return TextSignature(())
        region=source.resize((r-l,b-t),Image.Resampling.LANCZOS,
                             box=(l*width/640,t*height/normalized_height,r*width/640,b*height/normalized_height))
        vectors.append(_text_strokes(region))
    return TextSignature(tuple(vectors))
