"""Extract the shipped ZIP outside the checkout and exercise its actual EXE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import zipfile


def verify(archive,root,online=False):
    sandbox=Path(tempfile.mkdtemp(prefix='TFT DataJ 便携验证 ')).resolve()
    assert sandbox.is_relative_to(Path(tempfile.gettempdir()).resolve())
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            assert (sandbox/name).resolve().is_relative_to(sandbox),'Unsafe archive path'
        zipped.extractall(sandbox)
    bundle=sandbox/'TFT-DataJ';manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((bundle/name).read_bytes()).hexdigest()==digest,name
    state=sandbox/'用户数据';state.mkdir()
    env=os.environ.copy()
    for key in list(env):
        if key.startswith(('PYTHON','QT_','QML')) or key=='VIRTUAL_ENV':env.pop(key)
    env['PATH']=env['SYSTEMROOT']+'\\System32;'+env['SYSTEMROOT']
    env['LOCALAPPDATA']=str(state)
    env['PYTHONHOME']=str(sandbox/'未安装Python');env['PYTHONPATH']=str(sandbox/'无源码')
    command=[str(bundle/'TFT-DataJ.exe'),'--diagnose','--forbid-path',str(root)]
    data_fixture=root/'outputs/companion/fixtures/data_display/matrix.json.gz'
    assert data_fixture.is_file(),'Required display regression fixture missing'
    shutil.copy2(data_fixture,sandbox/'数据显示.json.gz')
    command+=['--data-fixture',str(sandbox/'数据显示.json.gz')]
    if online:command.append('--online')
    explorer_fixture=root/'outputs/companion/fixtures/explorer-dark-ritual.json'
    if explorer_fixture.is_file():
        shutil.copy2(explorer_fixture,sandbox/'检索回归.json')
        command+=['--explorer-fixture',str(sandbox/'检索回归.json')]
    # Optional private verification inputs stay outside the deliverable archive.
    real_frame=root/'work/companion/live-validation/choice-2-1.png'
    catalog=root/'work/s18-refresh-20260926/catalog.json'
    if real_frame.is_file() and catalog.is_file():
        shutil.copy2(real_frame,sandbox/'选择画面.png');shutil.copy2(catalog,sandbox/'目录.json')
        command+=['--image',str(sandbox/'选择画面.png'),'--catalog',str(sandbox/'目录.json')]
    start=time.monotonic()
    result=subprocess.run(command,cwd=sandbox,env=env,timeout=300,capture_output=True)
    report_path=state/'TFT-DataJ/portable-check.json'
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'status':'failed','error':'No diagnostic report'}
    output={'archive':str(archive),'sandbox':str(sandbox),'exit_code':result.returncode,
            'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'version':manifest['version'],
            'elapsed_seconds':round(time.monotonic()-start,2),'manifest_files_verified':len(manifest['files']),
            'report':report,'scope':'isolated paths and environment on build PC, not a separate physical PC'}
    archive.with_suffix('.validation.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result.returncode==0 and report['status']=='passed',output
    print(json.dumps(output,ensure_ascii=False,indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--online',action='store_true')
    args=parser.parse_args();verify(args.archive.resolve(),Path(__file__).resolve().parents[1],args.online)
