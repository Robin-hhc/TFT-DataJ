# 数据验证的运行方式

在仓库根目录、已安装 `packaging/requirements-runtime.txt` 的 Python 3.12 环境中执行。开发机可将 `python` 换成 `work\p0-runtime\Scripts\python.exe`。

## 识别性能、内存与闪烁回归

`validate_data.py` 同时包含 `test_runtime_stability.py`：手动/阶段触发、过期窗口后换牌、冷却、迟到回调、前台检查、失败统计重试、并发上限，以及真实 Qt 任务完成/失败后释放截图。释放检查禁用循环 GC，用弱引用检查图片是否还被任务持有，不依赖机器内存阈值。

性能单独测量，避免把系统负载波动当成 UT 失败。需要本机真实图片和 OCR 模型：

```powershell
python -X utf8 tools/profile_runtime.py --copy-frames --report work/performance/refresh.json
python -X utf8 tools/profile_runtime.py --copy-frames --fresh --report work/performance/new-choice.json
python -X utf8 tools/profile_runtime.py --copy-frames --captures 200 --report work/performance/stress.json
```

可用 `--image 完整图片路径` 换样本。`--copy-frames` 为每次截图分配新图片，必须用于内存比较；复用同一图片不会暴露截图滞留。`--fresh` 每轮清空已确认候选，测首次识别；默认测同一组候选反复按侧键。报告包括主进程工作集、私有提交量、CPU 时间、Qt 事件间隔及阶段耗时；不含浏览器子进程和实际游戏帧率。

本轮优化前基线可用 `--baseline-ref a940d5d2637c2ea4e56933a9435b90a3c2f50d8b` 复现。只在当前测试进程中加载该提交的四个运行模块，不修改工作区；其余依赖沿用本机，后续其他模块改变后需重新评估该对照。运行性能对照时不要并行构建或跑其他高负载检查。

实测与边界见 [2026-09-29 性能修复记录](runtime-performance-20260929.md)。

## 每次修改数据代码

```powershell
python -X utf8 tools/validate_data.py --release-gate
python -X utf8 tools/check_data_mutations.py
```

第一条统一运行两个源码目录的离线测试、真实公开快照到实际 Qt 卡片/表格/浮层的回放。无需 MuMu、网络、私人截图或下载 OCR 模型。第二条在内存中注入错误，验证检查能抓住它们，结束后自动还原，不改源文件。

报告在 `work/data-validation/offline.json`、`mutations.json`。每个案例都有查询条件、状态及差异；`source_gaps`、测试跳过和未运行扩展套件单独记录。不能只看单元测试的绿色总数。

本机已有原始截图时，可以额外执行：

```powershell
python -X utf8 tools/validate_data.py --include-private --release-gate --report work/data-validation/with-private.json
```

这会包含原有 OCR/截图测试。资料缺失会失败或明确跳过，不算全部通过。Windows CI 只运行可从干净克隆复现的核心检查及故障注入，并保存报告。

## 需要刷新网站抽查时

```powershell
python -X utf8 tools/collect_display_fixtures.py --output work/capture-NEW --versions 18.2a 18.2
```

每次最多 20 个实际请求，串行且间隔至少 1 秒。再次显式执行同一命令继续下一批，复用已经保存的响应。遇到限流、超时或结构改变立即停止当前批；退出码 2 表示来源不可用，失败请求保留记录，不假装完成。之后的批次跳过已失败请求；需要重试时显式增加 `--retry-unavailable`。版本应先确认网站仍提供。

完成采集后：

```powershell
python -X utf8 tools/audit_captured_data.py --capture work/capture-NEW --output work/audit-NEW
```

产生新的参考候选和实际助手回放差异报告，**不会更新已接受的基线**。此检查证明同份接口响应在助手内按约定正确显示，不声称网站 DOM 完全一致。跨时间数据有变化时保留各次响应，不能放宽精度或自动覆盖预期。

## 本机便携包验收

```powershell
python -X utf8 packaging/build_windows.py --version 0.2.2-data.1
```

构建后自动从新 ZIP 解压到仓库外的中文临时目录，限制 Python、PATH 及模块来源，启动真正的 EXE，回放同一份四领域矩阵。报告在 ZIP 同名 `.validation.json`，详细案例在报告指向的临时用户数据目录。

已有版本 ZIP 不允许覆盖。改代码或打包资源后不能用 `--skip-build` 复用旧构建。候选包验证不会创建 GitHub Release，也不会修改 v0.2.1 标签或资产。这仍是构建电脑上的隔离验证，不等于在另一台实体电脑验收。
