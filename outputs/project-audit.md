# 金铲铲 DataJ Companion：开源助手源码审计

核查日期：2026-09-25。仅静态阅读仓库元数据、许可证、依赖和源码；未运行候选，未测准确率或延迟，未调用统计接口。

## 结论与候选

建议独立建立 Companion，复用专用基础库。JinChanChanTool 的窗口定位、OCR 队列和穿透浮层值得研究，但其当前数据源是 MetaTFT 代理，并非 DataJ。未发现可以少量改造就交付本 MVP 的现成底座。

| 项目 | 核实能力与维护 | 许可及复用判断 |
|---|---|---|
| [JinChanChanTool](https://github.com/XJYdemons/JinChanChanTool) | C#、.NET 8、WinForms、PaddleOCR、OpenCvSharp；HEAD 62108d3，2026-09-25 | GPL-3.0；研究窗口/OCR实现，当前统计不是DataJ |
| [jcc-assistant](https://github.com/haoooowa/jcc-assistant) | Python、mss、PaddleOCR、PyQt5；仅一个提交，HEAD d8dd8c5，2026-06-08 | 完整树未发现LICENSE，README限制商业使用；不能作为可直接复制的开源底座 |
| [TFT-OCR-BOT](https://github.com/jfd02/TFT-OCR-BOT) | Python、tesserocr、OpenCV、Pillow；HEAD c3c8a7e，2024-04-12；2026-04-09归档 | GPL-3.0；仅参考ROI/回合识别；README限制英文客户端和1920×1080无边框主屏 |
| [TFT-Overlay](https://github.com/Just2good/TFT-Overlay) | C# WPF、.NET Framework 4.6.1；2019声明停更；HEAD dbbaf66，2021-04-07 | GPL-3.0；仅参考交互，README记录独占全屏置顶问题 |

提交证据：[JinChanChanTool](https://github.com/XJYdemons/JinChanChanTool/commit/62108d38dd01f38fd10516cf8c932e4b9fbe4753)、[jcc-assistant](https://github.com/haoooowa/jcc-assistant/commit/d8dd8c5d1dcb658b14bf49cc08ac04f460b1f9a5)、[TFT-OCR-BOT](https://github.com/jfd02/TFT-OCR-BOT/commit/c3c8a7e3c483b79ad38f59f9b0ef0a70b68a0e35)、[TFT-Overlay](https://github.com/Just2good/TFT-Overlay/commit/dbbaf66e505232cb181371adba4d6cdc858ec47d)。有提交不等于发布包可靠。

## JinChanChanTool 关键源码

**README技术栈过时。** [csproj第5–13行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/JinChanChanTool.csproj#L5-L13) 是net8.0-windows10.0.17763.0、WinForms、x64，不是README声称的.NET Framework；[依赖第2808–2816行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/JinChanChanTool.csproj#L2808-L2816) 包含Sdcb.PaddleOCR 3.0.1、OpenCvSharp 4.11.0.20250507。

**不是DataJ适配。** [LineupCrawlingService第38–47行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/LineupCrawling/LineupCrawlingService.cs#L38-L47) 使用api.xiaoyumetatft.xyz请求comps_data、comps_stats、comp_details，参数含queue=1100、patch=current、days=1、段位、comp、cluster_id；注释保留MetaTFT原站。这不能作为DataJ接口、金铲铲统计口径或数据授权的证据。

**装备统计被加工。** [CrawlingService第94–97行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/RecommendedEquipment/CrawlingService.cs#L94-L97) 请求同一代理的unit_detail；[第187–214行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/RecommendedEquipment/CrawlingService.cs#L187-L214) 排除Artifact/Radiant，按排名计数求均排，后续还有样本门槛和择优启发式。不宜移植为奥恩/光明装备原始统计比较。

**窗口定位可参考。** [第192–313行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/AutomaticSetCoordinates/WindowInteractionService.cs#L192-L313) 枚举顶层和子窗口；[第441–454行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/AutomaticSetCoordinates/WindowInteractionService.cs#L441-L454) 使用GetClientRect、ClientToScreen获取客户区。应区分模拟器外框和实际画面，未证明任意模拟器/DPI兼容。

**OCR/浮层可参考。** [QueuedOCRService第75–147行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Services/QueuedOCRService.cs#L75-L147) 有CPU/GPU初始化、队列、Bitmap输入；[高亮窗口第390–400行](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/SourceCode/JinChanChanTool/Forms/DisplayUIForm/CardHighlightOverlayForm.cs#L390-L400) 设置WS_EX_LAYERED、WS_EX_TRANSPARENT。这不是海克斯准确率或性能实测。

## 其他直接源码证据

- jcc-assistant：[依赖](https://github.com/haoooowa/jcc-assistant/blob/d8dd8c5d1dcb658b14bf49cc08ac04f460b1f9a5/requirements.txt)、[不抢焦点标志](https://github.com/haoooowa/jcc-assistant/blob/d8dd8c5d1dcb658b14bf49cc08ac04f460b1f9a5/overlay/window.py#L106-L113)、[九游/3DM策略来源](https://github.com/haoooowa/jcc-assistant/blob/d8dd8c5d1dcb658b14bf49cc08ac04f460b1f9a5/scraper/strategy_sites.py#L21-L26)。
- TFT-OCR-BOT：[局部截图、阈值化、数字白名单](https://github.com/jfd02/TFT-OCR-BOT/blob/c3c8a7e3c483b79ad38f59f9b0ef0a70b68a0e35/ocr.py#L5-L52)、[英文和分辨率要求](https://github.com/jfd02/TFT-OCR-BOT/blob/c3c8a7e3c483b79ad38f59f9b0ef0a70b68a0e35/README.md)。
- TFT-Overlay：[目标框架](https://github.com/Just2good/TFT-Overlay/blob/dbbaf66e505232cb181371adba4d6cdc858ec47d/TFT%20Overlay.csproj#L12)、[停更与全屏限制](https://github.com/Just2good/TFT-Overlay/blob/dbbaf66e505232cb181371adba4d6cdc858ec47d/README.md)。

## 许可证判断

GPL不禁止商业使用；派生作品分发须满足相应源码、通知和许可义务。参见[JinChanChanTool LICENSE第5、6节](https://github.com/XJYdemons/JinChanChanTool/blob/62108d38dd01f38fd10516cf8c932e4b9fbe4753/LICENSE#L196-L343)、[TFT-OCR-BOT LICENSE](https://github.com/jfd02/TFT-OCR-BOT/blob/c3c8a7e3c483b79ad38f59f9b0ef0a70b68a0e35/LICENSE)、[TFT-Overlay LICENSE](https://github.com/Just2good/TFT-Overlay/blob/dbbaf66e505232cb181371adba4d6cdc858ec47d/LICENSE)。当前JinChanChanTool根LICENSE未见非商业附加条款，不能据此保证模型和游戏资产无问题。

没有LICENSE不能默认为MIT或任意复制授权；[GitHub官方说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository#choosing-the-right-license) 区分查看/fork与复制、修改、分发授权。

[Riverbank FAQ](https://riverbankcomputing.com/commercial/license-faq) 说明分发许可与GPL不兼容时需要商业PyQt许可。换成PySide6不会自动消除已经复制的第三方应用源码的义务。

工程建议：根据公开Windows、Qt、OCR API独立实现，逐项记录基础库、模型权重和随包资产许可；若未来决定按GPL发布，再评估特定模块移植。本审计未覆盖整仓所有文件的授权。
