"""Hidden packaged-app diagnostic. No game input and no network by default."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true')
    parser.add_argument('--online',action='store_true')
    parser.add_argument('--image',type=Path)
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--explorer-fixture',type=Path)
    parser.add_argument('--data-fixture',type=Path)
    parser.add_argument('--forbid-path',type=Path)
    args=parser.parse_args()
    from bootstrap import FROZEN,RESOURCE_DIR,STATE_DIR
    report={'frozen':FROZEN,'resource_dir':str(RESOURCE_DIR),'state_dir':str(STATE_DIR),'checks':[]}
    qt=panel=None
    errors=[]
    def unhandled(kind,value,tb):
        errors.append(str(value));sys.__excepthook__(kind,value,tb)
    sys.excepthook=unhandled
    try:
        from app import QApplication,Companion
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtNetwork import QSslSocket
        from PIL import Image,ImageDraw,ImageFont
        from ocr_baseline import build_engine
        qt=QApplication([]);qt.setQuitOnLastWindowClosed(False)
        panel=Companion(offline=True,offline_catalog={'hex':[],'hero':[],'equip':[],'trait':[]})
        panel.timer.stop();panel.hide()
        assert panel.grab().save(str(STATE_DIR/'portable-ui.png'))
        assert (RESOURCE_DIR/'assets/refresh-glyph.png').is_file()
        assert (RESOURCE_DIR/'chevron-down.svg').is_file()
        report['checks'].append('application widgets and bundled UI assets')
        if args.explorer_fixture:
            fixture=json.loads(args.explorer_fixture.read_text(encoding='utf-8'))
            browser=panel.browser
            # Feed captured data through the packaged UI without issuing a query.
            browser.blockSignals(True)
            browser.set_catalog({'hex':[fixture['entity']]})
            browser.set_filter('hex',fixture['entity'])
            browser.blockSignals(False)
            browser.set_result(fixture['comps'],fixture['version'])
            actual=[card.comp_id for card in browser.cards]
            assert actual==['120','100'],f'Explorer minimum sample regression: {actual}'
            report['explorer']={'entity':fixture['entity']['name'],'comp_ids':actual}
            panel.tabs.setCurrentIndex(1)
            assert panel.grab().save(str(STATE_DIR/'portable-explorer.png'))
            report['checks'].append('dark ritual explorer excludes samples below 50')
        if args.data_fixture:
            from display_audit import run
            result=run(args.data_fixture)
            (STATE_DIR/'display-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            report['data_display']={k:result[k] for k in ['passed','failed','gaps']}
            assert result['failed']==0 and result['not_verified']==0 and not result['gaps'],report['data_display']
            assert {r['domain'] for r in result['cases'] if r['status']=='pass'}=={'explorer','hero','hex','items'},'Missing display domain'
            report['checks'].append('packaged explorer, hex, item overlays and hero equipment replay')
        panel.vision.engine,report['models']=build_engine()
        test_image=Image.new('RGB',(200,64),'black')
        font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arialbd.ttf'),42)
        ImageDraw.Draw(test_image).text((20,2),'2-1',font=font,fill='white')
        stage=panel.vision.read_round_crop(test_image)
        assert stage=='2-1',f'Bundled OCR stage: {stage}'
        report['checks'].append('bundled OCR models and ONNX CPU inference')
        page=QWebEngineView();loaded=[];page.loadFinished.connect(loaded.append)
        page.setHtml('<html><body>Companion browser diagnostic</body></html>',QUrl('about:blank'))
        end=time.monotonic()+15
        while not loaded and time.monotonic()<end:qt.processEvents();time.sleep(.01)
        assert loaded==[True],f'WebEngine load failed: {loaded}'
        report['checks'].append('WebEngine helper and local page')
        assert QSslSocket.activeBackend()=='schannel',QSslSocket.availableBackends()
        report['checks'].append('Windows native TLS backend')
        if args.online:
            from dataj import DataJ
            from comp_browser import Portraits
            catalog=DataJ().catalog()['data']
            assert catalog.get('hex') and catalog.get('equip')
            store=Portraits(qt)
            url='https://img.dataj.cc/images/s18/hero/s18_head_sivir.png'
            store.request(url);end=time.monotonic()+12
            while store.pending and time.monotonic()<end:qt.processEvents();time.sleep(.01)
            assert url in store.images,'Portrait HTTPS failed'
            report['checks'].append('DataJ HTTPS and real hero portrait')
        if args.image:
            if not args.catalog:parser.error('--image requires --catalog')
            catalog=json.loads(args.catalog.read_text(encoding='utf-8'))['data']
            with Image.open(args.image) as frame:
                result=panel.vision.analyze_fast(frame.convert('RGB'),catalog['hex'])
            report['real_frame']={'stage':result['round'],'ids':[c['resolution'].get('id') for c in result['cards']]}
            assert result['scene']=='choice_candidates' and all(report['real_frame']['ids']),report['real_frame']
            report['checks'].append('external real game frame recognition')
        if args.forbid_path:
            forbidden=args.forbid_path.resolve()
            dependencies=[Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None)]
            assert not any(p.is_relative_to(forbidden) for p in dependencies),'Source workspace imported'
            assert not any(Path(p).resolve().is_relative_to(forbidden) for p in sys.path),'Source workspace on search path'
            report['checks'].append('no source workspace modules or search paths')
        assert not errors,errors
        page.close();page.deleteLater();qt.processEvents()
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
        traceback.print_exc()
    finally:
        if panel:panel.shutdown()
        if qt:qt.processEvents()
        (STATE_DIR/'portable-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1
