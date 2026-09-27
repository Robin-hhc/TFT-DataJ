# MuMu 全屏验证工具（P0）

这是可丢弃的本地验证程序，用于决定截图、浮层和离线识别方案；尚不是 DataJ Companion 成品。不读取游戏内存、不点击游戏、不发送游戏按键。运行时本地处理，公开样本和依赖的下载另行完成；不显示虚构的均排。

## 运行与退出

在 MuMu 全屏显示游戏时运行 `start-probe.cmd`。若启动时 MuMu 游戏窗口处于前台，则绑定该窗口；否则从面板选择实际游戏窗口，点击“绑定并收起”。不能把 MuMu 启动器当作游戏窗口。

- **Ctrl+Alt+F9**：展开或收起验证面板。
- **Ctrl+Alt+F10**：仅在绑定的 MuMu 处于前台时保存一张截图。
- **Ctrl+Alt+F12**：立即退出。
- 默认 5 分钟后自动退出；面板的“结束测试”也可退出。

点面板关闭按钮会收起并请求返回游戏；Windows 若拒绝恢复焦点，手动切回 MuMu。快捷键被占用会显示提示，不会强行覆盖其他程序的注册。

## 需要实际验证的行为

1. 游戏左上区域能看到“MuMu 浮层测试”，游戏画面继续正常显示。
2. 浮层出现时游戏保持焦点。用鼠标正常操作游戏，确认浮层没有截走点击。位置命中检查只提供辅助证据，不能代替实际点击体验。
3. 切到其他应用，浮层消失；切回全屏游戏，浮层恢复。
4. 用 F9 组合键打开面板并收起，确认能继续操作游戏。
5. 用 F10 组合键保存一帧；检查是否为游戏画面、是否黑屏、是否含测试浮层。程序请求系统将自己的浮层排除在截图外；若系统拒绝，会先隐藏浮层再截图。
6. 全屏切换、窗口尺寸变化后浮层位置正常；缩放和多屏覆盖需要分别测试。

截图只在显式请求时保存，没有连续录屏。窗口在截图前后切换、尺寸变化或最小化时，本帧会被丢弃。其他软件临时覆盖游戏的通知仍可能进入桌面区域截图，此工具不声称能识别所有遮挡。

## 记录位置与复现

每次运行创建工作区 `work/p0-runs/<时间>/`，记录 `events.jsonl` 和显式采集的 PNG。保留窗口 PID/句柄、客户区、DPI、前台状态、热点注册、截图耗时与是否疑似黑屏。日志仅存在本机。

依赖环境是工作区内 `work/p0-runtime`，使用 Python 3.12 x64。依赖版本见 `requirements.txt`，不修改系统 Python。直接启动：

```text
work\p0-runtime\Scripts\python.exe -X utf8 outputs\mumu-p0-probe\probe.py
```

验证工具另有 `--capture-foreground`（等待前台 MuMu 后保存单帧）、`--self-test`（窗口构造与标志检查后退出）、`--seconds 120`（调整本次自动退出时长）。单元测试用 `python -m unittest discover -s outputs/mumu-p0-probe -p "test_*.py"`。

截图耗时是该次调用结果，不能代替多帧 p95 性能或 OCR 准确率。全屏几何匹配只是客户区覆盖显示器，不能据此断言独占全屏。

## 实现依据

- [Qt WindowType 与窗口属性](https://doc.qt.io/qtforpython-6/PySide6/QtCore/Qt.html)：透明输入、不接受焦点、置顶窗口。
- [Microsoft RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)：全局快捷键及冲突检测。
- [Microsoft SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)：请求排除本程序浮层；是否有效以实际截图为准。
- [mss 项目](https://github.com/BoboTiG/python-mss)：桌面区域截图；不提供被遮挡游戏的独立画面保证。

Qt/PySide 与其他依赖继续适用各自许可；本工具尚未制作可外部分发的安装包，项目开源方式未决定。

## 公开图片离线验证

见 [公开截图 OCR 报告](../公开截图OCR验证.md)。`public-samples.json` 记录 4 张原图 URL、页面来源和人工标注；图片在工作区 `work/ocr-public-samples/`，未打包在此目录中。

- `ocr_baseline.py`：输入本地图片，输出原始文本、框、分数、耗时及模型哈希。不读取标注。
- `choice_reader.py`：根据选择页标题和三列卡名位置提取候选；找不到或有歧义则拒绝。
- `evaluate_public.py`：回放局部识别，最后对照人工标注；用既有 DataJ 历史快照做显式演示，不把旧图当当前对局。
- `snapshot_stats.py`：按明确阶段查表，缺失不回退到整体均排。

在工作区根目录执行：

```text
work\p0-runtime\Scripts\python.exe -X utf8 outputs\mumu-p0-probe\evaluate_public.py
```

回放会验证图片哈希、模型哈希、依赖版本及引擎参数；不一致则要求重跑全图基线。

此命令依赖当前工作区已保存的 baseline、negative-baseline、DataJ JSON 和图片。完整环境版本在 `environment-lock.txt`，基础窗口依赖在 `requirements.txt`。这是本地可复现实验，尚未打包成自动下载/部署工具。

## S18 批量验证

`validate_s18_batch.py` 使用已冻结的 S18 目录和统计，核对每个 ID 的三阶段查询；再用本机字体生成两组名称裁剪图并运行 OCR。合成图只用于暴露错误，不计实战准确率。结果与真实视频素材分开，详见 [S18 批量报告](../S18批量验证.md)。
