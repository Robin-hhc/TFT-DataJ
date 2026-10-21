# 2026-10-12：海克斯识别与补查失败根因定位

> 最终状态（2026-10-13）：本轮海克斯源码范围修复与隔离完整验收完成；组合工作树另一个功能的失败继续单独保留，尚未发布 EXE。

## 目标与范围

- 用户目标：理解当前工具及海克斯识别实现，核查近期识别/补查失败，定位反复失效的根因、设计缺口及回归保护。
- 验收条件：用原始证据区分识别、身份、数据与发布失败；确认缺陷先复现再修复；新增保护进入统一入口；保留历史素材和未运行范围。
- 开工：`main`，`1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`，远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。
- 环境：Windows，`work/p0-runtime/Scripts/python.exe`，Python 3.12.14。源码助手进程处于运行中；不重启或修改其原始日志/缓存。
- 开工已有改动：`AGENTS.md`、根 README、文档/测试/记录索引、打包说明和 `packaging/build_windows.py`；新增开发流程、验收模板、目录说明及两份 10-10 记录。本轮保留上述改动，仅在记录索引追加本轮行。
- 本轮原始输出：`work/hex-failure-root-cause-20261012/`；私人截图保持在原始归档。

## 复现、正确答案与实现

进行中。失败观察仅用作复现输入，不能成为正确答案。新增原图必须独立核对后才能加入批准基线。

## 实际检查

| 项目 | 命令或实际操作 | 结果 | 证据与限制 |
| --- | --- | --- | --- |
| 开工身份 | `git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse HEAD`、`git remote -v`、`git status --short` | passed | 上述起始提交；工作树已有其他改动 |
| 开发解释器 | `work/p0-runtime/Scripts/python.exe --version` | passed | Python 3.12.14 |
| 近期日志、原图与实现调查 | 进行中 | pending_review | 不把既往绿色记录算为本轮通过 |
| 受影响回归/统一入口/私有回放 | 尚未执行 | not_run | 定位后按修改范围运行 |
| 打包 EXE、现场物理侧键、游戏 FPS、另一台电脑 | 本轮未执行 | not_run | 离线回放无法证明这些边界 |

## 审阅与后续复测

识别链路、补查链路及测试覆盖由独立 agent 并行检查；最终实现另行审阅，执行结果待补。

## 上库与发布状态

本轮用户未要求推送或发布版本；`not_applicable`。

## 结论、限制与交接

调查中，后续在本文件追加实际失败、修复、验证命令及结论。


## 定位及受影响验证追加

- 已读当前架构、识别/预读源码和历史台账。自动“补查”包含截图/OCR，阵容阶段补查则是已确认 ID 后的 explorer 查询；两类失败分别统计。
- 原始近期日志快照及摘要：`work/hex-failure-root-cause-20261012/pipeline*.jsonl`、`choice-flow-summary.json`。10-11/12 截面 152 个选择页观察，102/40/8/2 次分别确认 3/2/1/0 卡；重复观察不当作独立选择成功率。21 个带补查错误的发布快照也包含进度重复。日志已缺原始异常，不能追溯每个历史故障的真实网络原因。
- 新取来源：`catalog-response-original.json` / `catalog-probe-summary.json`（263 行，SHA-256 `165e9339b62b06c0359c73922e609416c17c2bebedc4bed443b3fac758f1db69`）及 `global-stats-response-original.json` / `global-stats-probe-summary.json`（18.3，226 行，SHA-256 `9fa9e0d167cf974d67cd602a3e4391dc29f86abfb9b7532cc6e06634ecca151a`）。两者没有战时补给女神之泪；致命丽花目录两个 ID 图标地址不同，不能按单项统计擅自并名。独立 exact 请求原件在 `work/hex-rootcause-supplement-20261012/`；耐心学习/阵容121/2-1 当前有73局5.00，兽性本能+/阵容113/4-2合法返回无对应阵容。
- 两名 agent 分别从原图和归档目录核对三份新增 oracle；`oracle-independent-review.json` 保留逐原件哈希及预期。两个战时补给病例分别 `[null,20224,1023]` / `[null,1479,1023]`，致命丽花病例 `[20496,1008,null]`。使用 `tools/validate_bug_cases.py --cases-dir work/companion/bug-cases --review-baseline docs/testing/private-bug-baseline.json --register-reviewed-case <确切ID>` 三次登记，批准数31→34，旧31项全部不变。
- 真像素新增两张匿名标题裁图及独立来源目录片段；注册三个新 fixture，旧25份不变。新增26个公共方法，分布为标题边界6、恢复8、实际Qt归档5、来源诊断7；全部保留旧 registry ID/scopes 与原 oracle。详细精确 ID 见 `regressions.json`。

| 缺陷 | 修复前实际 RED 原件 | 最终修正 |
| --- | --- | --- |
| 目录缺项与 OCR 不足混为同一原因 | `work/hex-failure-recognition-20261012/taxonomy-red.log`，6方法11个断言失败 | additive reason，不变更身份门槛；重算跨重试视图的 lookup 分类 |
| 一次网络错误永久停止预读 | `work/hex-rootcause-supplement-20261012/red.log` | 至少60秒并遵守共享冷却的单个可取消 Timer，保留未完成队列 |
| 非法200主表缓存阻断恢复 | `work/hex-rootcause-supplement-20261012/schema-cache-red.log` | 域校验拒绝后按同键同获取时间失效，保护较新并发替换 |
| 部分补查错误没有实际归档 | `work/hex-diagnostics-audit-20261012/partial-timeout-behavior-red.log` | 实际终态事件/归档；其他成功统计保留 |
| 并发冷却期间把结构错误误标为冷却 | `work/hex-diagnostics-audit-20261012/source-classification-behavior-red.log` | SourceError明确原因标记，不从共享截止时间或错误文字猜分类 |
| 预读 canonical 名称与保存请求不同 | `work/hex-diagnostics-audit-20261012/prewarm-request-body-red.log` | DataJ.explore实际请求 seam 捕获精确 body |
| 冷却丢失源头及发布竞态 | `work/hex-diagnostics-audit-20261012/cooldown-origin-red.log` / `cooldown-origin-atomic-red.log` | 安全来源失败快照与冷却一起发布，读取锁内复制 |

- 受影响运行：在 `outputs/companion` 执行 `../../work/p0-runtime/Scripts/python.exe -X utf8 -m unittest test_source_failure_details test_hex_failure_diagnostics test_title_catalog_boundary test_hex_prewarm_recovery -q`，26方法全部通过、0失败/错误/跳过，3.333秒；原件 `affected-new-final.log`。识别旧37方法和预读/Qt/预算旧31方法分别通过，agent 原始日志保留，不与新方法累加为独立总覆盖。
- 新统一故障注入：`work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/hex-failure-root-cause-20261012/mutations-second.json`，14/14 caught；旧8语义不变、新6分别拒绝预读不恢复、坏缓存不失效、漏部分错误归档、隐藏目录原因、丢冷却源头、记录候选别名而非真实请求。首轮两个 escaped 因测试导入绑定未被 patch，原件保留；改在实际 consumer 的导入绑定施加同一 faulty API，未放宽断言。独立审阅确认新故障均触发语义断言而非 harness errors。
- 失败/工具限制留档：最初诊断 harness 缺 card box 是 fixture 错误，不作为行为 RED；一次临时缺 `panel_dismissal` 依赖来自同期其他任务，原件保留；一次批量替换冷却站点预期6实际7导致脚本 assert、修正后4来源测试通过；一次文档 formatter 命令用错 workdir 未执行，后续正确根目录命令已修正新 fixture 格式为 `utf8-lf`，14 registry方法通过。以上不称生产故障。
- 并行工作树：另一个“设计点击空白处自动收起”任务修改同一 `app.py` / 鼠标模块、增加 panel_dismissal 及其测试/台账。其 hunks 未修改或回退；完整验证绑定实际组合工作树。公共阶段中当前仅台账新增引用发生漂移，生产输入不变；后续完整私有入口会读取最终台账。临时归档测试补隔离 `bug_reporting.record`，真实 Reporter/Store 仍运行，测试事件不再追加到活动日志。
- 独立审阅：另一 agent 核对原 scope/fixtures/31批准哈希及14故障证据；生产代码交叉审阅定位并修正错误分类、请求名称及原子发布问题。预读调度采用受控时钟/Timer+真实DataJ/MockTransport；未等待现场真实一分钟，也未验证游戏性能。
- 文档链接及保护检查：`document-integrity-check.json`，missing_links为空；旧方法引用、scope、25 fixtures、31批准条目全部保留。当前架构、预读规范和回归积累入口已同步。

## 完整统一验证（进行中）

公共命令：`work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report work/hex-failure-root-cause-20261012/public.json`。日志 `public.log`。最终报告及私有完整回放待追加；当前不称完整验收通过。


## 组合工作树公共结果与隔离（2026-10-12）

- 上述公共命令 actual exit1，883方法，882passed / 1failure / 0errors / 0skips，unittest426.400秒；356显示全部通过、source_gaps为空，25历史主题/273引用/28fixtures检查通过；34批准原图在公共阶段为schema-only/not_run。唯一失败为同期另一个任务新增 `test_outside_click_collapse.OutsideClickCollapseTests.test_passive_collapse_preserves_plan_query_and_local_guide_scroll`，实际断言 `loaded.count()==0` / Local guide did not load。此失败已保留 `public.json` / `public.log`，没有删除、跳过或放宽测试；本轮26个新方法全部passed。
- 与开跑339输入快照相比，仅台账加入同期40个外点方法引用、本轮临时归档测试补日志隔离发生变化，生产/fixture/原始批准图未变，见 `public-final-drift.json`。组合结果不能称整个当前工作树绿色。
- 创建本任务附属管理 worktree：`C:/Users/Robin/.codex/worktrees/hex-rootcause-20261012/tft-helper`，确切起始HEAD仍1ae完整SHA。复制本轮19个范围文件；app从基线重建仅本轮4hunks；台账保留旧25ID/228refs，增加本轮26方法/45refs→273，旧25fixtures加3→28，旧31批准加3→34。未提交的外点功能/40方法属于另一任务，其源码、台账及失败原件仍保留共享工作树；隔离验收不冒称该功能也通过。
- 独立隔离审阅 `work/hex-diagnostics-audit-20261012/isolated-static-review.json` passed：manifest19hash相符，仅app/registry按范围不同，旧保护无损失，app正好4hexhunks；日志隔离不替换Reporter/Store。`isolated-source-manifest.json` / `isolated-runtime.diff` 固定受测范围。隔离registry14方法通过，missing evidence为空。
- 私有原图复制只读输入到隔离副本、逐文件hash一致；当前43档案/34批准/9pending，新增未审核档案不算通过，原件不修改。复制索引 `isolated-case-copy-hashes.json`；整屏身份回放继续按独立oracle，排名不是该回放的验收对象。


## 最终隔离范围验收与交接（2026-10-13）

- 在上述固定 worktree 执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report E:/tft-helper/work/hex-failure-root-cause-20261012/isolated-full.json`，actual exit0，866方法全部passed / 0failures / 0errors / 0skips，unittest289.099秒。其中843公共、23私有扩展（7模块）；本轮26方法均实际passed。此一次完整入口包含公共与私有范围，未将公共组合失败改写为成功。
- REG25 / 273references / 28fixtures、356冻结显示通过，source_gaps为空只对冻结显示矩阵成立。批准原图34三文件hash全部verified，34身份回放passed；当前43total / 34reviewed / 9pending，0invalid / failed / skipped。九份pending不算通过；三份新增图的未知身份仍安全拒绝。
- `isolated-validation-summary.json` 检查manifest19个源码/fixture/registry文件无漂移、159个原始及隔离私有输入无漂移；真正受测对象为起始SHA+`isolated-source-manifest.json`+`isolated-runtime.diff`，source_tree_dirty=true，不称已提交或clean clone。完整报告SHA-256 `5615c52c52da67e13b987034b424e727d02b9730d41fa435dab59c78b588f7e6`，原日志SHA-256 `c4505426f4f1718c2c26061ff00c2a6322e8434034dd847add22fe0a7e92d6d0`。
- 随后在相同固定副本执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report E:/tft-helper/work/hex-failure-root-cause-20261012/isolated-mutations.json`，actual exit0，14/14caught / 0escaped。原始日志同名 `.log`；JSON SHA-256 `c3ce9e3dfae017fb10867a580fecf1caa6adfc277b1956524bbde48e0ab4760b`。此最终故障检查采用隔离日志后的测试，保留首轮错误patch和共享树14通过原件。
- 完整结果与静态独立审阅共同满足本轮明确的源码范围：目录 lookup 原因可区分、真实错误恢复和坏主表缓存失效、逐项失败保留成功统计且可追溯、取消/晚回调/源头原子发布、原保护完整、新保护进入统一入口。现有源码助手未重启，运行实例没有自动加载新代码；没有构建/发布EXE、推送、现场游戏、物理侧键/FPS或另一台电脑验收。
- 共享工作树的同期外点功能仍属于另一任务；本轮公开报告的1项local guide加载失败原件保留，最终隔离通过不能证明全部组合源码绿色。隔离副本供复查，主工作树本轮变更与其他人改动均保留；没有删除/跳过已登记旧测试，也没有抹去原失败报告。
- 来源女神之泪缺项和致命丽花无法独立证明唯一ID仍未补齐；本轮把它们明确归类和守护安全边界，不按同名/统计大小猜答案。以后取得独立实体证据后再新增映射和成功oracle；旧原图/拒绝oracle保持冻结。
