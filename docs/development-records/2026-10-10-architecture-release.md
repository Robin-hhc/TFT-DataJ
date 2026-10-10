# 2026-10-10：架构优化与 v0.2.14 交付验收

## 目标与范围

用户要求通读设计、检查并实施架构优化，已授权完成上库、CI 和新版便携交付。其他 agent 负责当前复现问题；本轮不接管几何上下文及损坏缓存修复。

起始分支 `main`，起始 SHA `0bb8c13c81b22e05cb8f8a55bdbe051dd95d55ce`，远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。Windows AMD64，Python 3.12.14，使用 `work/p0-runtime/Scripts/python.exe`；运行与构建依赖按仓库锁定版本核对。

改动包括结构化海克斯结果、任务执行前有效性检查、跨版本共享来源预算及其实际 Qt 合同回归；同步[当前架构](../design/当前架构.md)、[版本说明](../releases/v0.2.14.md)和历史索引 REG-002/003/010/017/023。目录整理、归档保护和统一开发流程的其他未提交改动保留，不混入源码交付；发布包另从固定提交的干净 checkout 构建。

## 实现与独立证据

- `HexResults` 保存身份、作用域、数值、样本、来源与进度。刷新保留和 UI 着色直接读取事实，显示字符串只用于投影。冻结来源 fixture 与实际 Companion/Qt 发布测试独立检查数值和保留范围。
- `Job` 执行前检查有效性；过期的目录、列表、详情和英雄出装任务不再访问来源。已经开始的 HTTP 仍需回调范围保护。真实队列测试检查最新请求执行、迟到请求不执行及引用释放。
- `SourceBudget` 统一限制应用内总 HTTP 并发 3、后台并发 1、请求间隔与失败冷却。完整请求身份继续隔离版本缓存和在途结果，独立 adapter 默认使用各自预算。
- 发包检查发现便携诊断的两个调度 double 不接受新增参数。修改前两个真实 Qt 诊断测试分别出现 `TypeError(is_current)` 和请求未产生断言失败；保留原诊断断言，修正为执行前取消、成功发布及异常直接上报。日志保存在 `work/portable-query-lifecycle-20261010-68857abc/`。

新增方法 ID 与 public 范围均追加至 [regressions.json](../testing/regressions.json)。原有测试、25 份冻结素材、30 份批准私有病例及其 oracle/hash 保留；5 份 pending 不计为通过。

## 实际检查

本轮先前源码快照为起始 SHA 加未提交 diff，20 文件哈希保存在 `work/data-validation/architecture-optimization-source-snapshot-20261010.json`。

| 检查 | 实际命令与结果 | 原始证据及范围 |
|---|---|---|
| 首轮含私有统一验证 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --report work/data-validation/architecture-optimization-20261010.json`；799 tests，0 failure/error/skip，356 显示回放；30 approved 哈希与身份回放通过，5 pending 单列 | 报告 SHA-256 `c277231932d80dbc91c56e0b2d97cfacf7a18986d9dc39f76b7694146766a557`；这是便携诊断修正前的快照，不能代替最终检查 |
| 数据故障注入 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/data-validation/architecture-optimization-mutations-20261010.json`；8/8 caught | 保留阶段、全局/阵容、版本、样本、排序和实际显示保护 |
| 架构合同错误注入 | 基线 7 项通过；忽略任务 guard、丢弃共享 budget、忽略结构化保留三个故障分别使 4/2/1 项失败 | `work/data-validation/architecture-contract-mutations-20261010.json`；证明合同拒绝具体错误，无原始用户故障的项目不声称 red-green 修复 |
| 便携诊断真实 Qt 回归 | 修改前 2 项失败；修正后 4 项通过，组合原测试共 20 项通过，无跳过；忽略 guard 的错误被捕获 | `work/portable-query-lifecycle-20261010-68857abc/`；同一面板连续诊断通过并留存 5 张生成截图；源码诊断不等于 EXE |
| 最终源码验收 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 0bb8c13c81b22e05cb8f8a55bdbe051dd95d55ce --report work/data-validation/architecture-release-final-20261010.json`；803 tests，0 failure/error/skip，243.417 秒；356 显示通过 | 25 主题、180 方法引用、25 冻结素材；30 approved 原图哈希与身份回放通过，5 pending；报告 SHA-256 `f1b5ad66d1db0e3eccb225b77451e2509ff13b9a91369ddd5897b1dabee05135` |
| 最终数据故障注入 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/data-validation/architecture-release-final-mutations-20261010.json`；8/8 caught，退出 0 | 原始 JSON 和同名前缀 log 保留本机 |
| 固定帧触发性能对照 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/profile_runtime.py --image work/companion/live-validation/choice-2-1.png --copy-frames --repeat 4 --captures 20 --report work/data-validation/architecture-release-performance-current-20261010.json`；baseline 使用相同参数加 `--baseline-ref 0bb8c13c81b22e05cb8f8a55bdbe051dd95d55ce` 与 baseline 报告名；均退出 0 | 帧 hash `9181da560fbf2c3d24acb6876a9c05b4620f18d8af940fd65048825f61fac767`；刷新中位数 34.66→42.96ms，GUI 最大间隔 11.58→9.57ms，峰值主进程工作集 386.57→383.38MiB；invalidate 后均不保留全帧。仅 4 次且基线只替换工具定义的 4 个模块，不声称速度提升或完整旧版本对照；不含网络、真实截图、WebEngine 子进程或游戏 FPS |
| 固定 SHA 远端 CI | pending | 不引用旧 SHA 的绿色结果 |
| 全新 ZIP / 实际 EXE | pending | 独立解压离线及线上诊断，分别留报告 |
| 现场游戏/物理侧键/FPS/另一台电脑 | not_run | 本轮没有对应现场证据，不能从源码或隔离 EXE 推断 |

## 审阅

不同 agent 分别审阅运行时、来源预算、结构化事实、打包与设计同步；未发现剩余源码架构阻断。打包审阅发现上述调度接口问题，已先复现再修正。最终便携 diff、暂存范围及报告另行核对。

## 上库与发布

交付候选版本 `v0.2.14`；版本选取时本地/远端 tag、Release 和 dist/archive 均未使用该版本。提交、精确 SHA CI、包身份、资产上传与公开状态尚需实际执行。源验证、公共 CI、隔离 EXE 与现场游戏分别记录。

## 追加验收

后续结果追加在此；保留先前快照、失败证据和未覆盖范围。
