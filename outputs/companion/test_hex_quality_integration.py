"""Quality/prefix decisions at Vision's frame and OCR public seams."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageOps, ImageDraw

from vision import Vision
from hex_quality import read_hex_quality
from scene_gate import may_be_choice

FIXTURES=Path(__file__).parent/'fixtures'


def reviewed_inputs(glyph='silver-hug-i'):
    evidence=json.loads((FIXTURES/'hex-hug-i-title-context-20261020.json').read_text('utf-8'))
    with Image.open(FIXTURES/'hex-hug-i-title-context-20261020.png') as source:
        title=source.convert('RGB')
    path=FIXTURES/('hex-quality-'+glyph+'-20261021.png')
    meta=json.loads(path.with_suffix('.json').read_text('utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['crop_sha256']:
        raise AssertionError('Original glyph changed')
    with Image.open(path) as source: icon=source.convert('RGB')
    return title,icon,evidence['catalog']


def selection_frame(glyph='silver-hug-i', *, absent_icon=False):
    title,icon,catalog=reviewed_inputs(glyph)
    w,h=3840,2160
    image=Image.new('RGB',(w,h),(20,45,30))
    with Image.open(Path(__file__).parent/'assets/refresh-glyph.png') as source:
        refresh=source.convert('RGB').resize((source.width*4,source.height*4))
    for cx in (.236,.499,.761):
        left,top,right,bottom=map(round,((cx-.09)*w,.34*h,(cx+.09)*w,.39*h))
        image.paste(title.resize((right-left,bottom-top)),(left,top))
        if not absent_icon:
            bounds=tuple(map(round,((cx-.055)*w,.14*h,(cx+.055)*w,.31*h)))
            image.paste(icon.resize((bounds[2]-bounds[0],bounds[3]-bounds[1])),bounds[:2])
        image.paste(refresh,(round(cx*w)-refresh.width//2,round(.68*h)))
    return image,catalog


class HexQualityIntegrationTests(unittest.TestCase):
    def test_non_family_frame_keeps_quality_pixels_unread(self):
        image,catalog=selection_frame()
        catalog=catalog+[{'id':'ordinary','name':'普通选项'}]
        vision=Vision()
        vision.engine=lambda array,**kwargs:SimpleNamespace(txts=['普通选项'],scores=[.99])
        with patch('vision.read_hex_quality',side_effect=AssertionError('Unneeded icon processing')):
            result=vision.analyze_fast(image,catalog)
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],['ordinary']*3,result)

    def test_frame_recovers_missing_suffix_from_reviewed_icon_and_literal_prefix(self):
        image,catalog=selection_frame()
        self.assertTrue(may_be_choice(image),'Synthetic layout uses the real refresh glyph seam')
        vision=Vision()
        calls=[]
        def engine(array,**kwargs):
            calls.append(array.shape)
            return SimpleNamespace(txts=['拥抱'],scores=[.99])
        vision.engine=engine
        result=vision.analyze_fast(image,catalog)
        self.assertEqual(result['cards'][0]['resolution']['status'],'resolved',result)
        self.assertEqual([c['resolution']['id'] for c in result['cards']],['10615']*3)
        self.assertTrue(all(c['resolution']['method']=='reviewed_family_base_and_quality' for c in result['cards']))
        # Two round reads and the existing initial three title views per card.
        self.assertEqual(len(calls),11)

    def title_read(self,texts,quality=1,*,image=None,catalog=None):
        crop,_,rows=reviewed_inputs()
        vision=Vision()
        texts=iter(texts)
        calls=[]
        def engine(array,**kwargs):
            calls.append((array.shape,hashlib.sha256(array.tobytes()).hexdigest()))
            value=next(texts,('',0))
            text,score=value if isinstance(value,tuple) else (value,.99)
            return SimpleNamespace(txts=[text],scores=[score])
        vision.engine=engine
        result=vision.read_name(crop if image is None else image,rows if catalog is None else catalog,quality=quality)
        return result,calls

    def test_third_initial_view_legal_tier_vetoes_two_prefix_votes(self):
        result,calls=self.title_read(['拥抱','拥抱1','拥抱 II'])
        self.assertEqual(result['status'],'conflict',result)
        self.assertNotIn('id',result)
        self.assertEqual(len(calls),3)

    def test_trusted_complete_title_cannot_override_contradictory_icon(self):
        result,_=self.title_read(['拥抱 I']*3,quality=2)
        self.assertEqual(result['status'],'conflict',result)
        self.assertNotIn('id',result)

    def test_single_confident_prefix_and_low_confidence_views_do_not_resolve(self):
        result,_=self.title_read(['拥抱',('拥抱1',.899),('',0)])
        self.assertNotEqual(result['status'],'resolved',result)
        self.assertNotIn('id',result)

    def test_exact_catalog_duplicates_still_reject_quality_completion(self):
        _,_,catalog=reviewed_inputs()
        result,_=self.title_read(['拥抱1']*3,catalog=catalog+[dict(catalog[0])])
        self.assertNotEqual(result['status'],'resolved',result)
        self.assertNotIn('id',result)

    def test_unknown_quality_preserves_default_title_reads_and_call_sequence(self):
        crop,_,catalog=reviewed_inputs()
        def run(explicit):
            vision=Vision();calls=[]
            def engine(array,**kwargs):
                calls.append((array.shape,hashlib.sha256(array.tobytes()).hexdigest()))
                return SimpleNamespace(txts=['拥抱'],scores=[.99])
            vision.engine=engine
            result=vision.read_name(crop,catalog,quality=None) if explicit else vision.read_name(crop,catalog)
            return result,calls
        self.assertEqual(run(True),run(False))

    def test_repeated_identical_pixels_cannot_supply_two_prefix_votes(self):
        crop,_,catalog=reviewed_inputs()
        crop=ImageOps.grayscale(crop).point(lambda p:255 if p>200 else 0).convert('RGB')
        for point in ((0,0),(crop.width-1,0),(0,crop.height-1),(crop.width-1,crop.height-1)):
            crop.putpixel(point,(255,255,255))
        native=np.asarray(crop)[:,:,::-1].copy()
        signature=(native.shape,hashlib.sha256(native.tobytes()).hexdigest())
        calls=[];vision=Vision()
        def engine(array,**kwargs):
            key=(array.shape,hashlib.sha256(array.tobytes()).hexdigest());calls.append(key)
            return SimpleNamespace(txts=['拥抱' if key==signature else ''],scores=[.99])
        vision.engine=engine
        result=vision.read_name(crop,catalog,quality=1)
        self.assertGreaterEqual(calls.count(signature),2,'Exercise the actual duplicate-pixel retry')
        self.assertNotEqual(result['status'],'resolved',result)
        self.assertNotIn('id',result)

    def test_absent_icon_keeps_missing_suffix_unconfirmed(self):
        image,catalog=selection_frame(absent_icon=True)
        vision=Vision()
        vision.engine=lambda array,**kwargs:SimpleNamespace(txts=['拥抱'],scores=[.99])
        with patch('vision.read_hex_quality',wraps=read_hex_quality) as quality_reader:
            result=vision.analyze_fast(image,catalog)
        self.assertEqual(quality_reader.call_count,3,'Unknown quality is read once per relevant card')
        self.assertTrue(all(c['quality']['status']=='unknown' for c in result['cards']))
        self.assertTrue(all(c['resolution']['status']!='resolved' for c in result['cards']))

    def test_non_choice_frame_does_not_initialize_ocr(self):
        vision=Vision()
        result=vision.analyze_fast(Image.new('RGB',(3840,2160),(20,45,30)),[])
        self.assertEqual(result['scene'],'unknown')
        self.assertIsNone(vision.engine)

    def test_actual_ocr_uses_reviewed_prefix_and_icon_without_suffix_rewriting(self):
        image,catalog=selection_frame()
        result=Vision().analyze_fast(image,catalog)
        self.assertEqual([c['resolution'].get('id') for c in result['cards']],['10615']*3,result)
        self.assertTrue(all(c['quality']['level']==1 for c in result['cards']))
        self.assertTrue(any(c['resolution'].get('method')=='reviewed_family_base_and_quality' for c in result['cards']),result)

    def test_one_frame_uses_one_catalog_snapshot_and_next_frame_rechecks(self):
        image,catalog=selection_frame()
        original=list(catalog)
        vision=Vision();calls=[]
        def engine(array,**kwargs):
            calls.append(array.shape)
            if len(calls)==6:catalog.clear()
            return SimpleNamespace(txts=['拥抱'],scores=[.99])
        vision.engine=engine
        first=vision.analyze_fast(image,catalog)
        self.assertEqual([c['resolution'].get('id') for c in first['cards']],['10615']*3,first)
        self.assertTrue(original)
        second=vision.analyze_fast(image,catalog)
        self.assertTrue(all(c['resolution'].get('id') is None for c in second['cards']),second)


if __name__=='__main__':unittest.main()
