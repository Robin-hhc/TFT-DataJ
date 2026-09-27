"""Real screenshot regression: recover narrow Roman suffix without name substitution.

Requires local user screenshots; images stay outside the repository.
"""
import json
from pathlib import Path
from PIL import Image
from vision import Vision
from bootstrap import ROOT

catalog=json.loads((ROOT/'work/s18-refresh-20260926/catalog.json').read_text(encoding='utf-8'))['data']['hex']
vision=Vision();vision.prepare()
cases=[
    (Path('D:/Documents/MuMu共享文件夹/Screenshots/MuMu-20260926-112533-073.png'),
     '2-1',['黑铁资产','应急护甲 I','进攻宣告']),
    (ROOT/'work/companion/live-validation/choice-3-2-overlay.png',
     '3-2',['后期专家','强化之能量','治疗法球 I']),
    (ROOT/'work/companion/live-validation/real-3-2-2155.png',
     '3-2',['兽性本能','玻璃大炮 II','双城赢家']),
]
for path,stage,names in cases:
    observation=vision.analyze_fast(Image.open(path).convert('RGB'),catalog)
    actual=[c['resolution'].get('name') for c in observation['cards']]
    assert observation['round']==stage
    assert actual==names,(path.name,actual)
    assert all(c['resolution']['status']=='resolved' for c in observation['cards'])
    if path.name=='real-3-2-2155.png':
        assert observation['cards'][0]['resolution']['id']=='20764'
    print(path.name,actual,observation['elapsed_ms'],'ms')
