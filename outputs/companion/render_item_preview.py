"""Render actual item widgets over a recorded S18 frame; this is not a live test."""
import json
import time
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QWidget,QLabel
from bootstrap import ROOT
from vision import Vision
from item_vision import analyze_items
from item_stats import item_stat,fallback_stat,best_holders
from item_overlay import ItemOverlay, HEADER_CLEARANCE
from comp_browser import Portraits
from dataj import DataJ


def main():
    app=QApplication([])
    folder=ROOT/'work/item-choice-samples'
    adapter=DataJ(db=folder/'preview-cache.sqlite')
    catalog=adapter.catalog()['data'];detail=adapter.comp('112')['data']
    global_result=adapter.item_stats();comp_result=adapter.item_stats('112')
    vision=Vision();vision.prepare()
    summaries=[]
    store=Portraits(app)
    for filename in ('user-p2-720p-0753s.png','user-p3-720p-2232s.png','user-p1-720p-0288s.png'):
        image=Image.open(folder/filename).convert('RGB')
        observation=analyze_items(image,vision,catalog['equip'])
        assert observation['scene']=='item_candidates'
        canvas=QWidget();canvas.resize(*image.size)
        background=QLabel(canvas);background.setPixmap(QPixmap(str(folder/filename)));background.resize(*image.size)
        overlays=[];rows=[]
        centers=[(c['box'][0][0]+c['box'][1][0])/2 for c in observation['cards']]
        gap=min(b-a for a,b in zip(centers,centers[1:]))
        for card in observation['cards']:
            entity=card['resolution'];eid=entity['id']
            row={'id':eid,'name':entity['name'],'global':item_stat(global_result,eid),
                 'comp':item_stat(comp_result,eid,'112'),'holders':[],'holder_status':'missing'}
            if row['comp']['status']=='missing':row['comp']=fallback_stat(adapter.explore('equip',entity['candidates'][0]),'112')
            holders=adapter.item_holders(eid,'112')
            row['holders']=best_holders(holders,{str(h['heroId']) for h in detail['heroes']})
            row['holder_status']='ok' if row['holders'] else 'missing'
            rows.append(row)
            widget=ItemOverlay(store);widget.setParent(canvas);widget.setWindowFlags(Qt.WindowType.Widget)
            widget.update_row(row,catalog)
            widget.setFixedWidth(round(gap*.92))
            b=card['box'];height=b[2][1]-b[0][1]
            widget.move(round((b[0][0]+b[1][0])/2-widget.width()/2),round(b[0][1]-HEADER_CLEARANCE*height-widget.height()))
            widget.show();overlays.append(widget)
        deadline=time.monotonic()+20
        while store.pending and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        app.processEvents()
        # A preview is only complete when every displayed hero has a real image.
        for widget,row in zip(overlays,rows):
            for i,hero in enumerate(row['holders']):
                assert widget.urls[i] in store.images, f'Portrait missing: {hero["name"]}'
                assert not widget.holder_lines[i][0].pixmap().isNull(), hero['name']
        output=folder/(filename.removesuffix('.png')+'-ranks.png')
        assert canvas.grab().save(str(output))
        summaries.append({'source_frame':filename,'output':str(output),'patch':adapter.patch,
                          'comp':detail['name'],'rows':rows,'portraits_loaded':len(store.images),
                          'mode':'recording widget render, not live capture'})
        canvas.close()
    (folder/'preview-stats.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'file':s['output'],'items':len(s['rows'])} for s in summaries],ensure_ascii=False))


if __name__=='__main__':main()
