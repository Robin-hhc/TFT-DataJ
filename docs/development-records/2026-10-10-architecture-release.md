# 2026-10-10：架构优化与 v0.2.15 交付验收

## 目标与范围

用户要求通读设计、检查并实施架构优化，已授权完成上库、CI 和新版便携交付。其他 agent 负责当前复现问题；本轮不接管几何上下文及损坏缓存修复。

起始分支 `main`，起始 SHA `0bb8c13c81b22e05cb8f8a55bdbe051dd95d55ce`，远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。Windows AMD64，Python 3.12.14，使用 `work/p0-runtime/Scripts/python.exe`；运行与构建依赖按仓库锁定版本核对。

改动包括结构化海克斯结果、任务执行前有效性检查、跨版本共享来源预算及其实际 Qt 合同回归；同步[当前架构](../design/当前架构.md)、[版本说明](../releases/v0.2.15.md)和历史索引 REG-002/003/010/017/023。目录整理、归档保护和统一开发流程的其他未提交改动保留，不混入源码交付；发布包另从固定提交的干净 checkout 构建。

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
| 固定 SHA 远端 CI | b4d0fac / CI 38059884912 success；781 public、0 failure/error/skip、356 显示、8/8 caught | 对应 artifact、私有未运行边界及哈希见追加验收 |
| 全新 ZIP / 实际 EXE | v0.2.15 全新构建；实际 EXE 离线/线上通过，3023 文件、356 显示 | 包 SHA、下载复核、独立原图预期与硬件限制见追加验收 |
| 现场游戏/物理侧键/FPS/另一台电脑 | not_run | 本轮没有对应现场证据，不能从源码或隔离 EXE 推断 |

## 审阅

不同 agent 分别审阅运行时、来源预算、结构化事实、打包与设计同步；未发现剩余源码架构阻断。打包审阅发现上述调度接口问题，已先复现再修正。最终便携 diff、暂存范围及报告另行核对。

## 上库与发布

首次交付候选为 `v0.2.14`，版本选取时本地/远端 tag、Release 和 dist/archive 均未占用；该候选因首次 CI 失败未公开。最终 `v0.2.15` 的提交、精确 SHA CI、包身份、上传、公开状态与远端下载复核已完成，逐次结果见追加验收。源验证、公共 CI、隔离 EXE 与现场游戏分别记录。

## 追加验收

后续结果追加在此；保留先前快照、失败证据和未覆盖范围。

### 首次 CI 与候选保留

源码 `494218449565f69ed7686bba5cc8a31ce394c386` 已推送 main、远端 SHA 一致。[CI 38058970801](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/38058970801)为 `failed`：780 public tests 中 779 passed、1 failure，0 error/skip；356 显示通过，数据故障注入因前序失败未执行。唯一失败为 `test_hex_result_publication.HexResultPublicationTests.test_display_projection_cannot_change_refresh_retention_or_overlay_value`，模型 4.23 已正确，但停用 timer 的测试画面超出 1.5 秒门槛，浮层保持旧 pending。原报告保留于 `work/release-0.2.14/ci-source/offline.json`。私有模块和 30 原图在 CI 中明确未执行。

受控时钟在第二次补查完成前推进 2 秒，0.710 秒稳定复现同一失败，日志 `work/data-validation/reproduce-publication-clock-red-20261010.log`。测试绘制前明确提供新鲜帧时间，保留全部数值/保留/文案断言；追加 REG-002 public 方法 `test_hex_result_publication.HexResultPublicationTests.test_stale_capture_defers_structured_publication_until_fresh_frame`。新方法同时验证旧画面禁止绘制、新鲜画面后正确投影。组合 8 项通过；受控延迟 2 项通过。独立内存注入仅移除生产 stale guard，新方法立即拒绝，证据 `work/data-validation/independent-publication-guard-review-20261010.log`。生产源码和 1.5 秒保护未改。

候选 v0.2.14 未建 tag/Release。干净 SHA 的全新构建与独立 EXE 离线、在线通过，但不足以弥补 CI 失败，未公开：ZIP 281142172 bytes，SHA-256 `9a56282d0d3fbf48c547e6d01007ca2ebb9bd3be364811e0197330793434cf47`，3023 文件哈希、356 显示；真实帧观察为 2-1、1023/1479/1006，与既有独立源码 oracle 核对一致；巨人腰带 equip/1007；联网检查仅目录/头像。原 ZIP/校验/报告逐文件 hash 核对后复制到 `dist/archive/candidates/v0.2.14/`，日志/两次报告在 `work/release-0.2.14/`。三个新增模块经实际 PYZ 检查存在。

最终候选改用未占用的 v0.2.15；原文件不覆盖、不重用。测试前置条件修正后重新执行完整含私有入口并等待新提交 CI，再从该提交重新完整构建。

### v0.2.15 最终源码复验

`work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 0bb8c13c81b22e05cb8f8a55bdbe051dd95d55ce --report work/data-validation/architecture-release-v15-final-20261010.json` 退出 0，804 tests，0 failure/error/skip，256.521 秒；356 显示通过，25 历史主题、181 方法引用、25 冻结 fixture 通过；30 approved 哈希和身份回放通过，5 pending 不算通过。受测版本为 `4942184` 加仅测试前置条件、新 stale→fresh 回归与台账的 diff，生产模块与该提交完全一致。报告 SHA-256 `faa029e350b15d473e3997cbfac9e9916633a417e43fe2d0ac4634992d0ffecf`。

`work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/data-validation/architecture-release-v15-mutations-20261010.json` 8/8 caught，退出 0。性能测量时的生产模块未改变，前述性能结果不重复解释成新版本速度提升。

### v0.2.15 上库、包与公开交付完成

源码提交 `b4d0fac8ff0491139d5e8a3464f78459692bef3a` 已推送 main；[CI 38059884912](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/38059884912) 的 `headSha`、完成状态和成功结论逐项核对一致。下载并检查原始 artifact：781 项公共测试、356 显示、25 主题/181 方法引用/25 fixture，0 failure/error/skip，8/8 数据故障捕获。CI 没有运行 7 个私有模块和 30 份批准原图。原始报告保存在 `work/release-0.2.15/ci-source/`：offline SHA-256 `6967860ee69ab8dcc2aca1b5871a159904792fb7e1c70fd335d6d96f7c26a94d`，mutations SHA-256 `610abb365693b18a60411bc351c2acb80c7128fc0f44aae33d9db0deceb5e203`。

本机 804 项最终报告的基准仍是 `4942184` 加已测 diff；两份暂存快照中的 22 个源码/测试/工具/台账文件逐一核对受测字节及新提交内容，与 `b4d0fac8ff0491139d5e8a3464f78459692bef3a` 绑定一致，不能把 dirty 报告伪称干净 CI。

从 `b4d0fac8ff0491139d5e8a3464f78459692bef3a` 的干净 checkout 安装锁定构建依赖后执行完整 `packaging/build_windows.py --version 0.2.15`，退出 0，未使用 `--skip-build`；manifest `base_commit` 相同、`working_changes=false`。独立审阅逐一重算 ZIP 内 3023 份 manifest 文件哈希，无缺失或额外内容；直接查看实际 EXE PYZ，三个新增模块 `background_jobs`、`hex_results`、`source_budget` 均存在且 EXE 字节与 ZIP 一致；3 份私有输入原始哈希未进入包。

实际 EXE 在仓库外中文目录、空用户数据、限制 PATH 与源码搜索路径的隔离环境通过：自动离线 47.31 秒，随后 `packaging/verify_windows.py dist/TFT-DataJ-0.2.15-windows-x64.zip --online` 联网 46.62 秒，均 `exit_code=0`、`report.status=passed`、`frozen=true`、3023 文件及 356 显示通过。内置 OCR/ONNX、WebEngine 和 Windows TLS 通过；真实留存原图观察阶段 2-1、IDs 1023/1479/1006，与既有独立 oracle 核对一致；条件为 equip/1007 巨人腰带。联网项仅目录 HTTPS 与真实英雄头像，不证明实时统计排名。两份报告、构建/依赖/联网日志、manifest、PYZ 检查在 `work/release-0.2.15/`，本机私人路径和原始画面未上传。

注解 tag `v0.2.15` 的远端剥离 SHA 为 `b4d0fac8ff0491139d5e8a3464f78459692bef3a`。[公开预发行版](https://github.com/Robin-hhc/TFT-DataJ/releases/tag/v0.2.15) 的公开时间 `2026-10-10T14:50:57Z`，`draft=false`、`prerelease=true`。先建草稿并上传明确三份附件，逐一核对 `state=uploaded`、大小及 GitHub SHA-256 后公开；随后重新读取状态并通过 `gh release download v0.2.15` 下载 ZIP、校验文件及公开摘要，三份字节哈希与本机一致。ZIP 为 281143481 bytes，SHA-256 `a7950a32e8269e7ae4763bbec46f6de599fadb629d4e361dc979c80562715d92`。下载副本和校验记录在 `work/release-0.2.15/download-verified/`、`download-verification.json`，草稿与公开 API 记录分别保留。公开摘要仅使用字段白名单，原始 validation/private 报告没有上传。

这次补充仅更新交付文档，包与 tag 继续绑定已通过 CI 的源码提交 `b4d0fac8ff0491139d5e8a3464f78459692bef3a`。文档补充会另行提交推送并检查对应 CI，不改变包身份。其他任务的工作树字节保持不变；两份临时构建 checkout 在 ZIP/校验/报告/日志/manifest 留存后通过可恢复 Git 快照归档。v0.2.14 仍为未公开候选，原 ZIP 与失败证据保留。

现场游戏、物理侧键、MuMu 合成器、游戏 FPS 和第二台实体电脑未运行，不能从本机隔离 EXE 推断通过。5 个 pending 样本继续保留、不计通过；几何上下文和坏缓存问题仍由其他任务独立验收。
