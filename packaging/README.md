# Windows便携包

普通使用只需完整解压 `TFT-DataJ-0.2.1-windows-x64.zip`，双击 `TFT-DataJ.exe`。无需Python、pip、OCR安装和GPU推理环境。`_internal` 必须与EXE放在同一文件夹，设置、头像缓存、统计缓存和日志另存 `%LOCALAPPDATA%\TFT-DataJ`。可以移动整个程序文件夹或创建EXE快捷方式。

目标为Windows 10/11 x64。默认用CPU识别，DataJ统计和攻略需要联网；网络失败不会使用其他版本数据。更新时退出旧版、解压新版，用户目录中的设置保留。当前是未签名的便携测试构建，没有安装器、自动更新或Windows ARM原生包。

## 构建

构建者需要Windows x64及Python 3.12，使用独立虚拟环境；使用者不需要这些步骤。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
.venv\Scripts\python.exe packaging\build_windows.py
```

当前开发机也可使用 `work/p0-runtime/Scripts/python.exe packaging/build_windows.py`。依赖锁定不再包含开发机的 `file:///C:/Users/...` 安装路径；构建脚本在缺少模型时从RapidOCR官方模型仓库下载，并逐一验证SHA-256。运行助手不会自动下载模型。

产物：

- `dist/TFT-DataJ-0.2.1-windows-x64.zip`：整体复制到其他电脑的便携包。
- 同名 `.zip.sha256`：ZIP校验值。
- 同名 `.validation.json`：从ZIP解压后实际EXE的隔离验证结果。
- `work/package-build/dist/TFT-DataJ/`：未压缩目录，含EXE、运行库、模型、说明、许可与逐文件哈希清单。

基于PyInstaller的单目录模式：它把Python和依赖一同收集，接收电脑无需安装Python。选择该模式也使Qt动态库保持独立，启动时不必每次解压全部浏览器与模型文件。实现依据：[PyInstaller分发模式](https://pyinstaller.org/en/stable/operating-mode.html)、[资源定位](https://pyinstaller.org/en/stable/runtime-information.html)、[Qt官方部署说明](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)。

## 验证

构建完成后自动把实际ZIP解压到仓库外的临时目录，目录含中文和空格；使用仅含Windows系统目录的PATH、空的用户配置目录和无效的PYTHONHOME/PYTHONPATH启动EXE。不会修改系统环境或已有用户设置，不操作游戏。

```powershell
work\p0-runtime\Scripts\python.exe packaging\verify_windows.py dist\TFT-DataJ-0.2.1-windows-x64.zip --online
```

检查包内每个清单文件的哈希、完整界面实例、UI资源、三份内置模型、ONNX CPU识别、WebEngine子进程和本地页面、Windows TLS。加 `--online` 时实测DataJ目录HTTPS请求和真实英雄头像。开发机有原始2-1截图时，额外复制到验证目录做真实画面识别，截图不会进入ZIP。

本轮59项测试通过，其中包含“黑暗仪式”检索的最小样本回归。验证脚本也将冻结检索响应交给实际EXE，检查只展示“黑暗仪式蜘蛛”和“重装女警”。隔离EXE成功识别真实2-1画面的三项ID `1023 / 1479 / 1006`；联网模式检查DataJ与头像。该验证运行在构建机上，**不等于第二台物理电脑、其他Windows版本或不同硬件实测**；原有装备光明正例、实战延迟和FPS验收限制保持不变。

启动遇到问题时双击包内“检查运行环境.cmd”，查看 `%LOCALAPPDATA%\TFT-DataJ\portable-check.json` 和 `run-*.log`。正式启动失败会提示日志位置，避免无提示闪退。

## 包内容和许可记录

不打包开发虚拟环境原目录、游戏录像、用户截图、统计缓存和账号数据。依赖及模型的第三方声明和许可文件在 `licenses/`，对应版本、模型哈希和打包文件哈希在 `manifest.json`。开发依赖的许可可能一并列入清单，不能据此认定其代码均进入运行包。

模型归属按 [RapidOCR清单](https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md) 与本地哈希核对。Qt和Chromium适用各自许可，官方依据：[Qt 6.8 WebEngine许可说明](https://doc.qt.io/qt-6.8/qtwebengine-licensing.html)。本次便携包用于用户跨电脑运行验证；正式对外发布前还需整理Qt/Chromium与实际二进制对应的完整第三方告知材料，不能将依赖元数据清单视作分发审计结论。
