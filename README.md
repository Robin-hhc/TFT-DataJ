# 金铲铲 DataJ Companion

## Windows 便携版

其他电脑请下载 [v0.2.3 Windows便携版](https://github.com/Robin-hhc/TFT-DataJ/releases/tag/v0.2.3) 中的 `TFT-DataJ-0.2.3-windows-x64.zip`：先退出旧助手，完整解压后双击 **TFT-DataJ.exe**，不需要安装Python或OCR环境。保留旁边的 `_internal` 文件夹；可以为EXE创建快捷方式。目标系统为Windows 10/11 x64，最新统计与攻略仍需联网。

[本版改动与升级](docs/releases/v0.2.3.md) · [安装、快捷键与已知限制](docs/releases/v0.2.1.md) · [更新记录](CHANGELOG.md) · [问题反馈](https://github.com/Robin-hhc/TFT-DataJ/issues)

本机产物在 [dist目录](dist/)，构建与验证说明见 [Windows便携包](packaging/README.md)。设置与缓存保存在 `%LOCALAPPDATA%\TFT-DataJ`；包中不包含本机游戏截图、录像及旧缓存。已在本机的隔离目录和清理过的环境中运行EXE验证，尚未在第二台物理电脑实测。

## 源码运行

项目工作目录：`E:\tft-helper`。

双击根目录的 **启动助手.cmd**。首页展示多套阵容，上方检索器选择一个装备、转职、海克斯、英雄或羁绊条件。点击卡片即固定阵容，顶部复制主阵容码，左侧查看攻略或点英雄查出装。

默认自动阶段识别：收起面板并回到 MuMu 后，自动连接唯一的游戏窗口，每 3 秒仅检查顶部回合，在 2-1、3-2、4-2 开启海克斯识别。启动时预热识别模型，统计在后台加载。

手动触发始终作为保底：按 **鼠标后退侧键**、**Ctrl+Alt+F10** 或“立即补查一次”，不会关闭自动识别。暂停自动识别后，手动补查仍可使用；MuMu 关闭后等待重新连接。左上角“阵容助手 · 展开”按钮打开面板；Ctrl+Alt+F9 切换，Ctrl+Alt+F12 退出。

详见 [手动触发与阶段浮窗](outputs/手动触发与阶段浮窗.md)。当前改动通过离线截图与隐藏界面验证，游戏帧率、实际全屏点击穿透仍待实测。

## 文件位置

- `outputs/companion/`：桌面程序源码与使用说明。
- `outputs/mumu-p0-probe/`：共用的窗口、截图和 OCR 模块。
- `outputs/`：调研、设计、任务表和验证报告。
- `work/p0-runtime/`：本机 Python 环境与 OCR 模型。
- `work/companion/`：缓存、日志、回放结果。
- `work/s18-video-next/`：S18 录像样本与人工标注。

[详细使用说明](outputs/companion/README.md) · [任务进度](outputs/执行任务.md) · [实战回放验证](outputs/S18实战回放验证.md) · [新版界面预览](outputs/UI设计与验证.md)

2026-09-26 从原 Codex 任务目录复制到此处，保留原目录以免中断已启动的助手。现已按用户最新指定路径迁至 `E:\tft-helper`，此后开发以本目录为准。历史报告内的旧绝对路径为原始记录；当前应用按所在目录定位数据。

源码启动仍依赖本机Python基础安装和 `work/p0-runtime`。跨电脑使用请复制完整便携ZIP，而不是复制开发虚拟环境。游戏功能仍未完成独立多局验收。

### 鼠标侧键查询（2026-09-27）

默认按鼠标的后退侧键查均排（通常为靠近手腕的侧键）。首页可改成前进侧键或关闭，设置会保存；Ctrl+Alt+F10 仍可备用。只在目标 MuMu 游戏处于前台时触发，松开按键查询一次，忙碌和短时间连按不重复排队。侧键原有操作不会被拦截；如果鼠标驱动把侧键改成了键盘宏，需要恢复为标准后退/前进侧键。

此次通过输入过滤、前台校验、去重和原有流程的离线测试，未用真实鼠标及游戏验收。助手未自动启动。

## Git 仓库范围

本仓库保存程序源码、调研设计和验证记录。`work/`（本机 Python 环境、OCR 模型、统计缓存、日志、游戏截图及回放样本）不上传，生成的界面截图也保留在本机。部分历史报告的本地图片链接和依赖样本的回归脚本，需要原机器上的 `work/` 数据才能运行。

克隆源码仓库不会自动获得二进制发行包；`dist/` 不纳入Git。源码启动脚本仍需要 `work/p0-runtime/Scripts/pythonw.exe`。从新环境构建使用 `packaging/requirements-build.txt`；构建脚本准备并校验三份模型，程序运行时不自动下载模型。历史环境快照 `outputs/companion/environment-lock.txt` 包含原安装来源，不作为新电脑的安装入口。
