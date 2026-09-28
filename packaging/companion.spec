# Build on Windows x64 with packaging/build_windows.py.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata
import PySide6

root=Path(SPECPATH).parent
source=root/'outputs/companion'
datas=collect_data_files('rapidocr')+copy_metadata('rapidocr')
datas += [(str(source/'chevron-down.svg'),'.'),(str(source/'assets/refresh-glyph.png'),'assets')]
binaries=collect_dynamic_libs('onnxruntime')
# Keep the MSVC runtime beside the application; users need no developer tools.
for dll in Path(PySide6.__file__).parent.glob('*140*.dll'):
    binaries.append((str(dll),'.'))
a=Analysis([str(source/'launch.py')],
    pathex=[str(source),str(root/'outputs/mumu-p0-probe')],
    binaries=binaries,datas=datas,
    hiddenimports=['rapidocr.inference_engine.onnxruntime','onnxruntime'],
    hookspath=[],runtime_hooks=[],
    excludes=['tkinter','matplotlib','torch','paddle','tensorflow','openvino','PyQt5','PyQt6'],
    noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='TFT-DataJ',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,
    disable_windowed_traceback=False,uac_admin=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='TFT-DataJ')
