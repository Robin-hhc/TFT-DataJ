# Windows便携包

[下载v0.2.8便携测试版](https://github.com/Robin-hhc/TFT-DataJ/releases/tag/v0.2.8)。完整解压后双击 `TFT-DataJ.exe`，保留 `_internal`。无需Python、pip或OCR安装，设置与缓存保存到 `%LOCALAPPDATA%\TFT-DataJ`。

目标为Windows 10/11 x64。默认用CPU识别，DataJ统计和攻略需要联网；网络失败不会使用其他版本数据。更新时退出旧版、解压新版，用户目录中的设置保留。当前是未签名的便携测试构建，没有安装器、自动更新或Windows ARM原生包。

## 构建

下列命令与产物名对应v0.2.8；每版都应从最终提交重新构建并验证实际ZIP，源码与现场记录不替代包验证。

构建者需要Windows x64及Python 3.12，使用独立虚拟环境；使用者不需要这些步骤。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
.venv\Scripts\python.exe -X utf8 packaging\build_windows.py --version 0.2.8
```

当前开发机也可使用 `work/p0-runtime/Scripts/python.exe -X utf8 packaging/build_windows.py --version 0.2.8`。显式指定新版本，不覆盖已有 ZIP；本轮源码变化后必须完整构建，不能以 `--skip-build` 复用v0.2.7。依赖锁定不再包含开发机的 `file:///C:/Users/...` 安装路径；构建脚本在缺少模型时从RapidOCR官方模型仓库下载，并逐一验证SHA-256。运行助手不会自动下载模型。

应用图标源文件是 `outputs/companion/assets/app-icon.svg`。修改后运行 `work/p0-runtime/Scripts/python.exe -X utf8 tools/build_app_icon.py`，生成 PNG 和包含 16/24/32/48/64/128/256px 的 ICO。打包配置将 ICO 嵌入 EXE，同时供 Qt 窗口使用；图标文件也纳入构建指纹，不能以旧构建跳过新图标。

产物：

- `dist/TFT-DataJ-0.2.8-windows-x64.zip`：整体复制到其他电脑的便携包。
- 同名 `.zip.sha256`：ZIP校验值。
- 同名 `.validation.json`：从ZIP解压后实际EXE的隔离验证结果。
- `work/package-build/dist/TFT-DataJ/`：未压缩目录，含EXE、运行库、模型、说明、许可与逐文件哈希清单。

基于PyInstaller的单目录模式：它把Python和依赖一同收集，接收电脑无需安装Python。选择该模式也使Qt动态库保持独立，启动时不必每次解压全部浏览器与模型文件。实现依据：[PyInstaller分发模式](https://pyinstaller.org/en/stable/operating-mode.html)、[资源定位](https://pyinstaller.org/en/stable/runtime-information.html)、[Qt官方部署说明](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)。

## 验证

构建完成后自动把实际ZIP解压到仓库外的临时目录，目录含中文和空格；使用仅含Windows系统目录的PATH、空的用户配置目录和无效的PYTHONHOME/PYTHONPATH启动EXE。不会修改系统环境或已有用户设置，不操作游戏。

```powershell
work\p0-runtime\Scripts\python.exe -X utf8 packaging\verify_windows.py dist\TFT-DataJ-0.2.8-windows-x64.zip --online
```

检查包内每个清单文件的哈希、完整界面实例、UI资源、三份内置模型、ONNX CPU识别、WebEngine子进程和本地页面、Windows TLS。加 `--online` 时实测DataJ目录HTTPS请求和真实英雄头像。开发机有原始2-1截图时，额外复制到验证目录做真实画面识别，截图不会进入ZIP。

v0.2.8针对定阵海克斯补查、失焦完成回调及失败恢复增加专项回归。公开参考包含18.3阵容107的完整直表及精确阶段检索响应，旧冻结矩阵只迁移缺项提示，数值不变。本轮使用留存原图、正常HTTPS接口及隐藏Qt界面回放，不启动MuMu；来源、场景与测试范围见[核验记录](../docs/testing/hex-comp-statistics-20261008.md)。历史实战与装备在线验证保留在[v0.2.7发布说明](../docs/releases/v0.2.7.md)，不冒充本轮新增实战结果。

每次发布均需从本版源代码重新构建，并以上述命令验证实际ZIP；此前候选包不能代替交付包验证。门槛包含356组数据显示、真实2-1静态截图的三项ID `1023 / 1479 / 1006`、模型、WebEngine、联网DataJ与头像。保留打包后等价海克斯身份、问题图无损保存/去重/pending，以及真实4K巨人腰带 `equip/1007` 主标题诊断；新增实际EXE内的三项精确阶段补查、请求范围及缓存诊断，该项使用内嵌MockTransport，不把它称为联网实测。验证器把本机哈希锁定的私人原图复制到外部临时目录，图片不进入ZIP。实际执行项及结果保存为本版 `.validation.json`，下载校验值见 `.zip.sha256`。发布页先保持草稿，待CI通过、实际ZIP验证通过且ZIP与校验附件均上传完成后，发布为预发行测试版。

源码和已核对私有原图可通过统一入口复验：

```powershell
work\p0-runtime\Scripts\python.exe -X utf8 tools\validate_data.py --include-private --release-gate --bug-cases-dir work\live-match-20261007\reviewed-cases --report work\data-validation\v0.2.8-source-final.json
```

只有合法 `expected.json` 的问题图会运行OCR；待核对图另列 pending，不算通过。这条路径验证场景、身份、详情种类与海克斯阶段，不证明排名正确，也不会进入游戏或联网。

便携隔离验证运行在构建机上，**不等于第二台物理电脑、其他Windows版本或不同硬件实测**；真实静态截图OCR不代表新增对局现场捕获、实战延迟或FPS验收。原有装备光明正例的验收限制保持不变。

启动遇到问题时双击包内“检查运行环境.cmd”，查看 `%LOCALAPPDATA%\TFT-DataJ\portable-check.json` 和 `run-*.log`。正式启动失败会提示日志位置，避免无提示闪退。

## 本机问题图片

识别或查询失败时，助手复用已经取得的绑定游戏图在后台归档，不增加自动截图或OCR；“识别 / 设置”里的“记录问题”可手动捕获当前游戏，“记录文件夹”打开记录目录。源码位于 `work/companion/bug-cases/`，EXE 位于 `%LOCALAPPDATA%\TFT-DataJ\bug-cases\`。上限100例、500 MiB，重复问题保留首帧，满额停止新增，不覆盖旧图、不自动上传；自动归档为单任务并有15秒冷却。

打开游戏名称详情后，直接按鼠标后退侧键即可取条件并检索，无需先点击助手按钮。“记为已选”只保存本局检索快捷条目。普通4K巨人腰带已用真实原图验证；暴风之剑尚无独立原图，先前单次在线查询失败也不代表零样本或持续服务故障。

## 包内容和许可记录

不打包开发虚拟环境原目录、游戏录像、用户截图、统计缓存和账号数据。依赖及模型的第三方声明和许可文件在 `licenses/`，对应版本、模型哈希和打包文件哈希在 `manifest.json`。开发依赖的许可可能一并列入清单，不能据此认定其代码均进入运行包。

模型归属按 [RapidOCR清单](https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md) 与本地哈希核对。Qt和Chromium适用各自许可，官方依据：[Qt 6.8 WebEngine许可说明](https://doc.qt.io/qt-6.8/qtwebengine-licensing.html)。本次便携包用于用户跨电脑运行验证；正式对外发布前还需整理Qt/Chromium与实际二进制对应的完整第三方告知材料，不能将依赖元数据清单视作分发审计结论。
