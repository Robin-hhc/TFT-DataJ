"""Regression on the user's video at 262 seconds; no window or network use."""
import json
from PIL import Image
from bootstrap import ROOT
from vision import Vision

catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['hex']
observation=Vision().analyze(Image.open(ROOT/'work/user-reference-BV1wXhD6ZEng/frame-0262.jpg'),catalog)
assert observation['round']=='2-1'
card=observation['cards'][2]['resolution']
assert card['status']=='resolved' and card['name']=='蔓延之根',card
print('262s: stage 2-1 and third card 蔓延之根 confirmed; other slots are not claimed')
