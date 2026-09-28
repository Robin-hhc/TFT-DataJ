"""Build a self-contained Windows x64 folder and ZIP from a configured Python 3.12."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
import httpx
from collect_notices import collect

ROOT=Path(__file__).resolve().parents[1]
MODELS={
    'PP-OCRv6_det_small.onnx':('PP-OCRv6/det','090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'),
    'PP-OCRv6_rec_small.onnx':('PP-OCRv6/rec','6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884'),
    'ch_ppocr_mobile_v2.0_cls_mobile.onnx':('PP-OCRv4/cls','e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c'),
}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-build',action='store_true')
    args=parser.parse_args()
    assert sys.platform=='win32' and platform.machine().upper() in ('AMD64','X86_64')
    import rapidocr
    models=Path(rapidocr.__file__).parent/'models';models.mkdir(exist_ok=True)
    for name,(kind,digest) in MODELS.items():
        path=models/name
        if not path.exists():
            url=f'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/{kind}/{name}'
            response=httpx.get(url,timeout=120,follow_redirects=True);response.raise_for_status()
            assert hashlib.sha256(response.content).hexdigest()==digest,name
            path.write_bytes(response.content)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
    work=(ROOT/'work/package-build').resolve()
    assert work.is_relative_to(ROOT.resolve()) and work!=ROOT.resolve()
    if not args.skip_build:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(work/'dist'),
                        '--workpath',str(work/'build'),str(ROOT/'packaging/companion.spec')],cwd=ROOT,check=True)
    bundle=work/'dist/TFT-DataJ'
    assert (bundle/'TFT-DataJ.exe').is_file()
    for filename in ('使用说明.txt','检查运行环境.cmd','THIRD-PARTY-NOTICES.txt'):
        shutil.copy2(ROOT/'packaging'/filename,bundle/filename)
    collect(bundle)
    version='0.2.1'
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    manifest={'version':version,'target':'windows-x64','python':platform.python_version(),
              'base_commit':revision,'working_changes':dirty,'models':{n:d for n,(_,d) in MODELS.items()},
              'files':{str(p.relative_to(bundle)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='manifest.json'}}
    (bundle/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/f'TFT-DataJ-{version}-windows-x64.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():z.write(p,Path('TFT-DataJ')/p.relative_to(bundle))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest},indent=2))
    from verify_windows import verify
    verify(archive,ROOT)


if __name__=='__main__':main()
