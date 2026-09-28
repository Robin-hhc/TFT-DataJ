"""Build a self-contained Windows x64 folder and ZIP from a configured Python 3.12."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
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
    parser.add_argument('--version',default='0.2.2-data.1',help='New candidate version; existing ZIPs are never overwritten')
    args=parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?',args.version):parser.error('Invalid version')
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/f'TFT-DataJ-{args.version}-windows-x64.zip'
    if archive.exists():parser.error('Archive already exists; choose a new candidate version')
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
    sources=[*sorted((ROOT/'outputs/companion').glob('*.py')),*sorted((ROOT/'outputs/mumu-p0-probe').glob('*.py')),
             ROOT/'outputs/companion/chevron-down.svg',ROOT/'outputs/companion/assets/refresh-glyph.png',
             ROOT/'packaging/companion.spec',ROOT/'packaging/requirements-runtime.txt']
    fingerprint={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    provenance=work/'build-provenance.json'
    if args.skip_build:
        assert provenance.exists() and json.loads(provenance.read_text(encoding='utf8'))==fingerprint,'Source changed; rebuild before packaging'
    if not args.skip_build:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(work/'dist'),
                        '--workpath',str(work/'build'),str(ROOT/'packaging/companion.spec')],cwd=ROOT,check=True)
        provenance.write_text(json.dumps(fingerprint,sort_keys=True),encoding='utf8')
    bundle=work/'dist/TFT-DataJ'
    assert (bundle/'TFT-DataJ.exe').is_file()
    for filename in ('使用说明.txt','检查运行环境.cmd','THIRD-PARTY-NOTICES.txt'):
        shutil.copy2(ROOT/'packaging'/filename,bundle/filename)
    collect(bundle)
    version=args.version
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    manifest={'version':version,'target':'windows-x64','python':platform.python_version(),
              'base_commit':revision,'working_changes':dirty,'source_hashes':fingerprint,'models':{n:d for n,(_,d) in MODELS.items()},
              'files':{str(p.relative_to(bundle)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='manifest.json'}}
    (bundle/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():z.write(p,Path('TFT-DataJ')/p.relative_to(bundle))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest},indent=2))
    from verify_windows import verify
    verify(archive,ROOT)


if __name__=='__main__':main()
