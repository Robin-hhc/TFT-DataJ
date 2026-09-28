"""Preserve installed dependency notices and explicit Qt/model upstream notices."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import httpx


SOURCES={
    'Qt/LGPL-3.0-only.txt':'https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/LGPL-3.0-only.txt',
    'Qt/GPL-3.0-only.txt':'https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/GPL-3.0-only.txt',
    'Qt/Qt-WebEngine-Licensing.html':'https://doc.qt.io/qt-6.8/qtwebengine-licensing.html',
    'RapidOCR/MODEL_LICENSES.md':'https://raw.githubusercontent.com/RapidAI/RapidOCR/main/python/MODEL_LICENSES.md',
    'RapidOCR/LICENSE':'https://raw.githubusercontent.com/RapidAI/RapidOCR/main/LICENSE',
    'PaddleOCR/LICENSE':'https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE',
}


def collect(destination):
    folder=destination/'licenses';folder.mkdir(exist_ok=True)
    packages=[]
    for dist in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
        name=dist.metadata['Name'];files=[]
        for relative in dist.files or []:
            basename=Path(relative).name.lower()
            if not any(token in basename for token in ('license','licence','copying','notice')):continue
            source=Path(dist.locate_file(relative)).resolve()
            if not source.is_file() or source.suffix.lower() in ('.py','.pyc','.pyd','.dll','.exe'):continue
            # Drop leading site-packages/../ segments, never write outside licenses.
            target=folder/name/Path(*[part for part in relative.parts if part not in ('.','..')])
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            files.append(str(target.relative_to(folder)))
        packages.append({'package':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),'files':files})
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    shutil.copy2(python_license,folder/'Python-LICENSE.txt')
    fetched=[]
    with httpx.Client(timeout=30,follow_redirects=True) as client:
        for name,url in SOURCES.items():
            response=client.get(url);response.raise_for_status()
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(response.content)
            fetched.append({'file':name,'url':url,'sha256':hashlib.sha256(response.content).hexdigest()})
    # ONNX Runtime ships notices outside its dist-info license directory.
    import onnxruntime
    for name in ('LICENSE','ThirdPartyNotices.txt'):
        target=folder/'onnxruntime'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(onnxruntime.__file__).parent/name,target)
    (folder/'inventory.json').write_text(json.dumps({'packages':packages,'upstream_notices':fetched},ensure_ascii=False,indent=2),encoding='utf-8')
