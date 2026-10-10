# 2026-10-11：匹配模式与截图取条件现场复验

截至 02:34，普通自动截图 / OCR 请求补修已完成独立审阅及新的完整验证：公共 816 / 私有 839、31 批准原图、8 数据故障注入全部通过，313 文件零漂移。准备推送并启动新进程进行第四局实测；以下保留各阶段的原始结论，第三局现场证据仍只绑定旧源码 56369c8。

## 目标与范围

- 用户授权：控制已打开的 MuMu，在匹配模式检查、修复问题并上库，修复后再实测；重点核对截图自动识别检索条件。
- 验收：真实原图独立核对主体，再检查自动读取、最终检索请求与实际 Qt 展示；故障先有失败回归，修复后统一验证、确切 SHA 的 CI，并回游戏复验。
- 开工分支 `main`，起始提交 `c2f1b2b18373c7a0077181abff4b0503a5582d8c`；远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。
- 本机 Python 3.12.14，`work/p0-runtime/Scripts/python.exe`；游戏窗口 MuMuNxDevice / MuMuPlayer-15.0-0，3840×2160，DPI 192。
- 开工存在其他人的未提交流程、目录整理文档和 `packaging/build_windows.py` 改动。本轮保留这些文件，只暂存本轮明确范围；记录索引按新增行单独暂存。
- 设计与历史：详情取条件、REG-010/014/015/019/022/024，按统一流程与回归积累执行。
- 原始日志、请求、响应与私人画面保留 `work/live-match-20261011-r1/`，不上传玩家原图。

## 初次复现、正确答案与实现（01:15 前）

- 现场识别预期由主标题、主体图标/布局和冻结来源目录独立核对，不能从 OCR 输出推导。第一局商店英雄与羁绊并排的原图，独立主体为卡蜜尔 / hero 1505；它不属于当前支持的详情布局，不能把空条件直接定为 OCR 错字。
- 确认的生产缺陷：后台装备/阶段探测占用捕获时，`ConditionController.trigger()` 和侧键入口直接返回，首次明确的取条件请求没有捕获、读取或提示。现场调用留下探测忙碌和没有条件读出的观察；公共回归通过真实隐藏 Qt、Companion 工作池和阻塞探测，独立复现请求丢失。
- 先保留 `trigger-red.log` 的 1 个失败，再补装备、阶段、配置侧键和上下文检查。`trigger-red-stage-mouse.log` 有 2 个失败；上下文的干净失败是 `trigger-red-frozen-context-v2.log`。首次同名无 v2 运行含异步夹具清理错误，保留日志但不算有效复现。
- 修复将一个有效请求排队，最多等待 2 秒；探测完成后优先取得新的整帧。重复有效请求合并且不延长期限；换过滤条件、窗口、版本、几何或会话边界取消旧意图并提示；真正手动捕获/OCR 忙碌仍不重复排队。失败探测也释放请求，关闭时停止等待计时器。
- 独立审阅发现 P2：旧等待请求因上下文变化或期限已过而取消时，同次新显式请求也被吞掉。`trigger-red-new-intent.log` 先得到 1 failure / 0 errors，再修复为取消旧等待后继续处理当前新意图；最终独立复审无阻塞问题。
- 最终新增 16 个具体公开测试方法，登记 REG-014；REG-010 关联生命周期与限时保护。历史 ID、批准基线和未覆盖范围保留，两个主题仍是 partial。主设计的详情入口与实施状态同步此次规则。
- `Computer Use` 对 MuMu 返回 `FrameArrived timed out: timed out waiting on channel`，刷新绑定重试仍有 `window capture timed out: timed out waiting on channel`；普通记事本对照也截图超时。没有盲点游戏坐标。
- 项目自身 MSS 截图成功：`work/p0-runs/20261011-000112-213019/game.png`、同目录 `capture.json`，前台 MuMu 客户区 3840×2160，capture 184.53 ms，非黑帧。实际画面为“自然之力·标准匹配”房间。
- 当前 VM 配置 `D:/Program Files/Netease/MuMu/vms/MuMuPlayer-15.0-0/configs/vm_config.json` 的 ADB host_port=16384；当前 MuMu 进程监听该端口。使用现有 `nx_main/adb.exe` 连接 127.0.0.1:16384，通过 Android 原生输入/原图采样操作游戏。这不证明 Windows 物理侧键或 Windows 控制工具截图正常。
- 初始“从游戏取条件”按钮隐藏怀疑经实际 CompBrowser Qt 检查排除：按钮已移至搜索行，空条件仍可见且发送一次 readRequested。保留这一纠正，不作为生产缺陷。
- 第二局 2-1 的三卡原图 SHA-256 `ef69a4e0bd125068968201b61ddb36397100c876ec6c5aa31d353d308481e210`，独立主标题是“电火花 I / 进攻宣告 / 白银命运”。当前 run `d7eb27bf1e34eefb3c4881e17b5b31c6` 的完整已加载目录由只读 IPC 保存为 `responses/b072e6cc98e74cbabf162eb46242d94a.json`，SHA-256 `79fa1da2561e8c4c5459dda3b446951982d2ce8c0762103bfe76f2aaf95d0a78`，统计 patch 18.3 / set 18。预期前两项 10708 / 10004，第三项基础版不在该目录，只有 + / ++ 且金币描述不同，不能借用这些 ID。
- 另以 SQLite `mode=ro` 取当前 `/gamedata` 缓存原始未投影 payload（263 hex；GET 参数只有 setId=18，目录不是按统计 patch 请求）：基础白银命运同样不存在，排除 259 投影丢条目。缓存 fetched 为 `2026-10-10T16:08:46.418395Z`；原 body UTF-8 SHA-256 `e5c2d7b74ebb0c1754fd922863f4538f5cbcd654702f3b8540905aa16c781d7d`，证据 `raw-gamedata-cache-20261010T170537Z-e91e5db6.json` 与同 stem metadata。没有修改 DB、新请求或把缓存字节称为本轮 HTTP wire bytes。
- 三卡属于强化选择页，预期互斥走 `augment_stats`，不得生成单个详情过滤、改已有 scope 或自动记本局已选。上述是实测前独立预期，不代表 reader / 统计展示已通过。原生 Android 图有右上黑矩形；来源及 Windows 实际生产截图是否同样遮挡需另核，不把它直接归因于助手。
- 私有清点相对上一轮的 35 总 / 30 批准 / 5 待核，新增 `case-bebf06ef248d400cd4e76cccadbd932500b118a6d414bbfa963abf2fce1d9224`（`created_at=2026-10-10T16:16:44.998+00:00`，bound_game / full_game / hex_unresolved）。本轮没有改它的 expected 或批准状态；安全元数据差异存于 `validation/pending-inventory-delta.json`，仍是 pending_review，不把诊断采样当验证成功。

## 实际检查

下表保留 OCR 追加修复前的阶段结果；最终联合验证、上库和修复后现场结论另在文末追加，不以本表替代最终源码验证。

| 项目 | 命令/操作 | 结果与证据 | 限制 |
|---|---|---|---|
| Windows 原图 | `work/p0-runtime/Scripts/python.exe -X utf8 outputs/mumu-p0-probe/probe.py --capture-foreground --wait-seconds 20` | passed；原图及窗口/DPI 元数据如上 | 单帧，不证明条件身份、物理侧键或 FPS |
| Android 连接 | 现有 adb `devices -l`、`connect 127.0.0.1:16384`、再次 `devices -l` | passed；当前 VM 返回 device / A2925 | 不证明生产 Windows 捕获 |
| 原图识别与最终请求 | 第一局商店卡蜜尔详情及 Qt 入口；第二局采样进行中 | 第一局原图 SHA-256 `c70487ae3b79319e6338f98fd768f813130b2af3724121d61093316fe6bbdb72`，独立 hero 1505；该入口被后台探测忙碌挡住，没有 reader 输出 | 商店英雄与羁绊并排布局不在支持范围；不作为已批准 OCR 正例 |
| 真实无详情负例 | 第二局的 `take_condition` / Windows MSS 原图 `21eaf38567fa39c0035b3eff1c414f20.png`，先独立核图再看 reader / Qt / 请求观察 | passed：17:08:20 UTC 原图 SHA-256 `d84e9376357a000bcc3ef2c4e823cf8a0a339ce9feaa93ba6c2285935d5df017` 实为 3-7 普通棋盘，没有展开详情；reader `no_verified_detail_panel`、route none；scope/本局已选/原浏览结果全保留；晚于入口的快照 jobs=0，期间无新详情请求 | 这是拒绝乱填的负例，不是英雄成功率或新 HTTP 成功证明；同场 Android 黑区在真实 Windows MSS 中是阵容推荐面板，未出现纯黑遮挡 |
| 受影响回归 | `QT_QPA_PLATFORM=windows`、`PYTHONPATH=E:/tft-helper/outputs/companion`；Python `-X utf8 -m unittest -v test_condition_trigger_priority test_condition_controller test_condition_controller_extra test_condition_manual_geometry_review test_mouse_shortcut test_choice_exit_confirmation test_runtime_stability test_input_spec_review test_item_overlay_stability test_item_proposal_recovery` | passed：118 tests，40.574 s，exit 0，无 errors/skips；`trigger-green-affected-new-intent.log` | 捕获/OCR 为受控替身，不证明实际原图识别、物理侧键或游戏 FPS |
| 请求保护的错误注入 | `work/p0-runtime/Scripts/python.exe -X utf8 work/live-match-20261011-r1/check_trigger_baseline_mutation.py`；实际 Qt 平台与受影响测试相同 | passed：旧版静默丢请求 3/3、延长等待期限 1/1、取消旧等待后丢弃新意图 2/2 均被拒绝；harness exit 0；`trigger-mutations-new-intent.log` | 六个变体只证明本次新增保护，不替代数据故障注入 |
| 公共统一入口 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation/public.json` | passed：797 tests，0 errors/failures/skips；356 显示（explorer 116 / hero 144 / hex 72 / items 24），`source_gaps=[]`；25 历史主题、201 方法引用、25 夹具保护通过；454.812 s / exit 0 | 7 个私有扩展按公共范围 not_run；30 批准原图索引 schema 通过，但公共运行不执行原图；离线矩阵无缺口不代表所有现场词条均有来源 |
| 私有统一入口 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation/with-private.json` | passed：820 tests，0 errors/failures/skips；30 批准原图哈希与身份回放全 passed；25 主题 registered 检查全执行；7 私有扩展已执行；356 显示无来源缺口；467.515 s / exit 0 | 清点的全部归档是 36 份，其中 6 份 pending_review，均不计通过；不能沿用开工时的 5 份口径 |
| 数据故障注入 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/live-match-20261011-r1/validation/mutations.json` | passed：8 个故障逐项 caught，0 escaped；3.272 s / exit 0 | 不用六个调度变体替代数据错误注入 |
| 最终源码漂移 | 比较 `validation/tested-source-before.json` 与本轮全部检查后的文件哈希；详见 `validation/verification-summary.json` | passed：170 项代码/工具/测试/历史保护文件零漂移；16 新方法两轮都是 16/16 passed | 更新本轮验收记录单列为文档修改，不混入生产漂移检查 |
| 推送与确切 SHA CI | 待完成验证 | not_run | 本轮尚未上库 |
| 修复后再次实测 | 待完成修复 | not_run | 不称为全部修好 |
| 发布 | 本轮仅要求修复上库 | not_applicable | 不覆盖 v0.2.15 资产 |

## 结论、限制与交接

进行中。最终代码与测试的 SHA-256 已冻结于 `work/live-match-20261011-r1/trigger-final-manifest.json`，受测三份生产文件的 diff 为 `trigger-final.diff`；16 方法清单为 `trigger-test-ids.json`。这里的起始 SHA + 文件哈希与已测 diff 绑定本轮工作树，不把尚未提交的工作树称为干净构建。

生产取条件仍需真实支持布局的原图、实际 reader、条件字段、请求/响应与 Qt 展示连续证据。物理侧键、真实游戏 FPS、另一台电脑及 Windows Computer Use 截图恢复均尚未验收。`last_elapsed_ms` 从实际捕获开始，排队等待不在该值内；不据此宣称端到端 P95 达标。

## 追加修订：2026-10-11 01:15，现场漏识别继续修复

- 以上 797 / 820 / 30 原图与 170 文件冻结结果只覆盖条件请求等待修复，均保留原报告，不用于证明随后 OCR 改动通过。第二局正式 Windows 原图的三次采集均没有展开详情：第一帧是 3-7 普通棋盘，后两帧是第四名结算。第一帧完整负例链已独立核对，不能把其他命名为 detail 的图片直接算作正例。
- 对新增 pending 原图独立复核确认：它实际是有效 3-2 三选一，主标题“装备百宝袋 I / 拥抱 I / 假人化”，该 case 自身冻结目录对应 1006 / 10615 / 10236。原图 SHA-256 `f566d6642ad3de466107090d2a8cc8cec8d22346d4ba604b44f79e1b18d8ec5d`。此前没有把该待核图计入 30 批准通过，正是本轮继续诊断的输入。
- 实际 `Vision.analyze_fast` 检出支持布局和 3-2，左右 ID 正确，中卡 `unrecognized`，只出现一次有效完整“拥抱 I”读取。没有错误已知 ID，但统计漏了一项。原始输出保留 `validation/diagnostic-original-replays.json`；不得把 expected 改成未知来收绿。
- 先保留真实原图失败 `ocr/original-red.json` 与日志，再实验标题像素视图。2 倍紧裁原色和部分宽度调整仍低于 0.90，保留这些失败；现有 1.6 倍宽 BICUBIC 读取置信约 0.934，独立像素的 1.6 倍宽 LANCZOS 约 0.923，均完整读取同一标题，见 `ocr/title-view-probes-wide.json`。准备保留双读一致与冲突拒绝规则，加入有依据的受限像素补读。
- 排队修复的受控性能对照已完成，`validation/performance-comparison-pre-ocr-fix.json`：后台阻塞的首次与六次重复场景，旧源各 0/8 执行，等待延迟为 null；队列修复各 8/8 执行且重复仅一捕获/读取，按钮至 OCR 结束中位数约 400–405 ms，空闲约 158 ms。这是固定原图/真实 Qt 工作池的受控对照，非游戏 FPS。Mock 调用历史保留图像副本污染了内存采样，不能据此作生产内存判断；本批报告明确是 OCR 新修复前的版本。
- 继续审核并追加上述原图的独立身份基线，运行干净 RED 后最小修复；重新执行受影响、公共、私有及数据故障注入，按最终源码上库/确切 SHA CI，然后第三局真实详情到请求/Qt 的正例验收。当前没有宣布整体完成。

## 追加修订：2026-10-11 01:23，OCR 修复与批准原图

- 以上 pending 状态是当时的清点结果。现在独立核图者依据该 case 自身冻结目录及主标题，新建 reviewed expected，再执行 `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_bug_cases.py --cases-dir work/companion/bug-cases --review-baseline docs/testing/private-bug-baseline.json --register-reviewed-case case-bebf06ef248d400cd4e76cccadbd932500b118a6d414bbfa963abf2fce1d9224`，exit 0。旧 30 条等于新索引前 30 条，全部 93 个批准文件哈希逐项一致；`private-hug-I-registration-integrity.json` 保存核对。现为 31 approved / 5 pending，待核项不计通过。
- 新原图 / case / expected SHA-256 分别为 `f566d6642ad3de466107090d2a8cc8cec8d22346d4ba604b44f79e1b18d8ec5d` / `c4c12740bbaeeb5fc084219421b5570fa94a969700b744606d4d0db6cae859a4` / `4148fadf0281d1dd58c1064c12a070541dd1d86ee5abb5ffe7c99a4601da4181`，批准索引 SHA-256 `ee0a8eeb72dff2bd21ef0c12bd649fe3ad32a01a25988eac5f9e774e9fa77ba7`。原批准索引字节备份保留本地。
- 正式 31 原图回放先以内存载入起始提交的旧 Vision：`ocr/private-original-31-red.json`，30 pass / 1 fail，唯一失败为新增原图中卡 10615；31 approved verified，0 drift / invalid，pending 5。未修改当前源码或任何 oracle。修复后的同一官方回放 `ocr/private-current-31-green.json` 为 31 pass / 0 fail / invalid / skip。
- `Vision.read_name` 只在原有尝试未识别且只剩一个完整目录候选时，最多追加一次 1.6 倍宽 LANCZOS 紧裁原色视图；仍要求至少两次完整标题高置信一致、0.90 门槛及不同已知品质冲突拒绝，不改数字/罗马后缀、不强填 ID。正常已确认、冲突或没有完整候选均不补读。
- 新增 8 个公开受控像素测试，先保存 `ocr/public-red.log`，后与受影响标题、布局、详情套件共 80 tests 全 passed / 0 skip；旧测试只补额外视图的空引擎输出，原方法 ID 和断言均保留。5 个内存错误变体全部 rejected / 0 errors，`ocr/title-mutations.json`；它们不替代统一数据故障注入。
- 首次合跑 19 个标题方法时，额外读取暴露旧受控引擎流未提供下一项，出现 5 个 mock 输出耗尽错误；日志 `ocr/title-targeted-first.log` 保留。随后为这些历史负例追加一次空 OCR 输出，未改变旧断言或正确答案。这批夹具错误不计为真实故障 RED，也不借它证明识别修复；行为 RED 使用上述原图及有效公开断言失败。
- 同原图、同 warmed engine 串行 5 对轻量对照：旧 16 / 新 17 次 OCR 调用，中位数 271.779 / 283.600 ms，约增加 11.821 ms，`ocr/retry-latency.json`。这只度量本原图的受限补读，不推断游戏 FPS、物理输入、EXE 或总体 P95。
- 最终 OCR 生产哈希 `vision.py=dcb998b48b6dd44d5fb31c95987d23dd0ca4db2d239a557f044230331fee6a0a`，两测试哈希分别 `296a222390298a477faf030d7c23db5f88e1e559f786058bc870953e115f1dc3` / `4294b85136777df61ad8be5a084823cd443dc8b36711187d0ca928ca32b3867b`。两处修复合并后的最终统一检查使用新的 `validation-final/`，不覆盖之前报告。
- 第二局结算已正常退出，17:20:07 UTC 回到标准匹配房间；第三局未开始。旧源码 QA run `d7eb27bf1e34eefb3c4881e17b5b31c6` 于 17:23:06 UTC 通过正常 quit 槽关闭；推送后重新启动最终源码再实测，避免旧进程冒充新修复。
- 最终独立审阅分 Standards / Spec 两轴，各自无阻塞发现；`review-standards-final.json` 与 `review-spec-final.json` 绑定同一 9 文件哈希、起始 SHA 和 scoped tracked diff SHA-256 `1cb1d397a19ec2d246e1293c7aba7123aa31cb73e8c0ca71208c407024fe0bee`。审阅不替代运行检查。REG-019 精确追加 8 方法后索引 SHA-256 `c73899dd71c8e95ad04c43f2b0a6f636970228d50b0ec322adb2bd402fb02bc8`；主设计同步两处已采用的实现边界。

## 前一版联合验证（2026-10-11 01:33 起追加）

- 起始 SHA 仍固定为 `c2f1b2b18373c7a0077181abff4b0503a5582d8c`。最终源码、工具、全部公开/私有测试、历史保护及批准原图共 313 文件冻结于 `validation-final/tested-source-before.json`，对应已测 tracked diff 和两个新增测试原文另存本地。独立新增方法是 24 个；相比开工 registry 新增 28 条登记引用，含 REG-010 对 4 个方法的交叉关联。最终为 25 主题 / 209 方法引用 / 25 夹具；旧方法、scope、fixtures 及批准文件均保留。
- 公共命令：`work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation-final/public.json`。exit 0，440.335 s，805 个实际方法全 passed，errors / failures 为 0，skipped 为空；24 新增方法全实际执行。356 显示检查（116 / 144 / 72 / 24）全 pass，`source_gaps=[]`，历史保护 passed。
- 公共 report SHA-256 `594042c70b3822b79558634471bab0edf5c68ff364ef3b09ea55294374af1a86`；该项前后 313 文件零漂移。公共模式的 7 个私有扩展明确 not_run，31 批准原图仅 schema 检查、31 not_run，不能把它计为真实原图通过。私有统一入口及数据故障注入仍在此公共检查之后串行执行。
- 私有命令：`work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation-final/with-private.json`。exit 0，457.207 s，828 实际方法全 passed，errors / failures 为 0，skipped 为空；新增 24 方法全部执行，7 私有扩展实际执行；356 显示检查全通过、无来源缺口，25 / 209 / 25 历史保护通过。
- 私有 report SHA-256 `a6ef5428c36710aac10d29f498639fdab1a5c9c61e78f9a55f62e683367c5549`。31 批准原图全部 verified、31 身份回放全部 passed；总清点 36 / approved 31 / pending 5 / invalid 0 / failed 0 / skipped 0。5 待核仍不计通过，313 文件再次零漂移。
- 数据故障注入命令：`work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/live-match-20261011-r1/validation-final/mutations.json`。exit 0，3.078 s，8 项逐项 caught / 0 escaped；三项验证严格串行，测试期间没有游戏操作、实机捕获或其他本地重负载作业并行。完整命令、原始日志、逐方法结果与报告哈希存于 `validation-final/`。

## 上库与修复后进程（2026-10-11 01:43 起）

- 最终统一摘要 `validation-final/final-summary.json` SHA-256 `f831129c76b4989fd8ab78aebf026f8c30881d5056416725bcf3aa5b2268d835`，13 项断言全 true；mutations report SHA-256 `b25db0a17de94b7dfb35450df55b250d697716c478c105847e4775dd6339361b`。正式提交前 `git diff --check`、`git diff --cached --check` 均 exit 0，12 个明确文件暂存；记录索引只暂存新增一行，其他工作树改动保留。`staged-scoped-audit.json` 证明 staged 内容与独立审阅/最终受测文件一致，scoped diff SHA-256 `f6244cdce01378c256b073978f11fbb47f29906ad61821a7cf4631c008afb5e5`。
- 源码提交 `56369c847f025b9726f48ca441ea52293947e120`（`fix: preserve condition requests and recover short augment titles`），普通推送 `git push origin 56369c847f025b9726f48ca441ea52293947e120:refs/heads/main` exit 0；`git ls-remote origin refs/heads/main` 核对同一 SHA。确切源码 [CI 38072823119](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/38072823119) 已开始，最终状态及 artifact 核对待追加；不引用 c2f1b2b 的旧 CI。
- 17:42:36 UTC 用 `work/p0-runtime/Scripts/python.exe -X utf8 work/live-match-20261011-r1/qa_runner.py --start-collapsed` 启动新的普通在线 app.main（局部只读观察与正常 Qt 槽），`DATAJ_QA_SOURCE_ROOT` 未设置。新 PID 107276 / run `62cb5b238692ece8676c8a70eb414173`，166 运行时 Python 文件字节与最终统一验证冻结哈希一致，本轮 scoped 源码无未提交差异。`post-push-runtime-identity.json` 将源码提交、远端、启动命令、driver 哈希与新进程关联；这不是打包 EXE 或物理侧键验证。
- 新进程只读启动快照 `responses/eb8b7e1c011948659c7407960248cfb0.json`：统计 patch 18.3 / set 18，目录 259 hex / 157 equip / 86 hero / 90 trait；绑定 MuMu HWND 459956 / PID 110104，3840×2160 / DPI 192；活动 paused，scope null，已选空，样本门槛 50、均排排序、搜索空，0 jobs。第三局从新的当前画面进入标准匹配，与远端 CI 并行，本地重验证全部结束。真实详情正例及后续请求/实际 Qt 结果仍待独立核图与连续证据，不将启动成功直接算功能通过。

## 源码 CI 收口（2026-10-11 01:49）

- 上述源码 [CI 38072823119](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/38072823119) 已 completed / success，`headSha` 精确等于 `56369c847f025b9726f48ca441ea52293947e120`。运行元数据与下载产物保存在新目录 `work/live-match-20261011-r1/ci-source-56369c8/`，没有覆盖本机报告。
- 独立审计 `ci-audit.json` 20 项断言全 true：报告源码同 SHA、clean；805 实际方法和 24 新增方法全 passed、0 errors / failures / skips；REG 25 / 209 / 25 全通过，历史比较 base 为开工 c2f1b2b，旧 ID、scope、fixtures、批准哈希无删变；356 离线显示检查全通过，离线矩阵无来源缺口；8 数据故障注入全 caught。
- CI 的 7 私有扩展明确 not_run，31 批准原图仅 schema-only / 31 not_run，不能替代本机私有 828 方法及 31 原图复验，更不能证明真实游戏、物理侧键、EXE 或 FPS。`ci-audit.json` / `offline.json` / `mutations.json` SHA-256 分别为 `18cf702a0ec01383d9fd68a4b8fbf3bf945941112aacd15e0d0a19c9de00f12d` / `8c756afb8e86e84c49e50d59070c336be588d23a9ee47949bf4d03f8a4599e6f` / `610abb365693b18a60411bc351c2acb80c7128fc0f44aae33d9db0deceb5e203`。

## 继续发现：普通自动整帧截图仍会吞首次条件请求（2026-10-11 01:52）

- 对 56369c8 的另一路后台所有权检查，实际 `Companion.tick → request_capture → capture_pool` 延迟整帧截图期间，点击真正 Qt 读取按钮产生一次 `readRequested`。此时 `capture_pending=true`、`rank_capture_started` 有值、`items.probing=false`、`stage_probe_pending=false`、`conditions.active=false`、`ocr_busy=false`、`once_active=false`。原 `background_probe_busy()` 只接纳 item / stage，因此没有 pending，自动任务结束后手动 capture / read 均为 0、输入未变。
- `work/live-match-20261011-r1/trigger-auto-review/repro.py`、`repro.log`、`repro.json` 保存初次 RED：1 个明确断言失败、0 errors / skips，0.498 s，实际 Qt 工作池与回调；5 份源码前后零漂移。该复现控制像素、延迟、窗口身份及 HTTP，不冒称物理侧键或现场时序。已经开始扩展有限等待的后台路径，保留现有手动处理中重复请求不排队的断言、2 s 总期限及上下文保护。
- 上述 805 / 828 / 8 与源码 CI 只证明此前 56369c8，不证明随后修订。新的最终受测 diff、统一检查、上库 SHA / CI 和重启后的游戏实测会单独追加，不覆盖先前结果。

## 普通自动路径补修及第三局真实链路（2026-10-11 02:13）

- 新增 11 个永久方法先 RED：9 方法 failed、2 个排除对照 passed；含 subtests 共 12 failures，0 errors / skips，`trigger-auto-review/red.json`。真实 `tick → request_capture → captured → analyze_fast` 工作线程阻塞时，自动 live OCR 同样没有接纳明确条件请求。随后才修改后台所有权判断及完成 / 失败 / 主循环的恢复优先级，不能把 11 方法表述为全部 RED 失败。
- 补修只改变普通自动截图 / 自动 live OCR 的接纳与调度；条件读取已 active、旧版手动 once、非自动或文件 OCR 均不接纳等待。截图检查完成后有效 pending 先于自动分析启动；等待时 tick 不排下一轮自动任务。仍保持 2 秒、合并不延期、冻结输入 / 版本 / 会话 / 窗口 / 几何 / 前台以及 fresh manual 原图互斥路由。普通浮层 invalidate 只改变 Session.revision，保留 session_id，不单独取消有效条件请求；新局等真实边界仍取消。
- GREEN 为旧 16 + 新 11 = 27 实际方法全 passed，0 errors / failures / skips，实际 native exit 0，6.898 s，旧 16 方法 AST 全保留。首次绿色运行曾有 offscreen Qt 收尾异常、进程 exit 1，原日志保留；仅在本地 runner 消费正常 DeferredDelete 后重跑同组断言得到真实 exit 0，未修改生产或断言来收绿。两个内存坏变体恢复旧 admission、旧 completion / tick priority，各 2 方法全失败、0 errors、实际 exit 1。
- `trigger-auto-review/extension-summary.json` SHA-256 `012280b0950e9f6e88d0d9f8ecdec8ea0aabb5cb5e90063a3eb762edf2c675b5` 保存确切命令、11 IDs、原日志和哈希。生产 `app.py` / `condition_controller.py` / 测试 SHA-256 分别 `3db081e694217ce60aaad96bd6b7a72a58d16f6bca77e661ebaf21adcea1eee7` / `2043f5d2e7085b7b3b704cc36644d7562f429848a903a0f0d0455c3a8beb720b` / `f44a75e6f529f161e17d15da8b62aae771dd3bbb1f49acb0b9bdec52b8d90f60`。
- REG-014 追加全部 11 个 public 方法，REG-010 交叉关联 6 个调度 / 合并 / 期限方法；总计 25 主题 / 226 引用 / 25 fixtures。相对开工新增 35 个独立方法、45 条登记引用；保留旧 ID / scopes / 原图、31 批准索引和 partial 覆盖。`trigger-auto-review/registry-append-audit.json` 保存追加核对，registry SHA-256 `ae56ceed25ae5a7f681c550b8fc39f72801d265622705871bda390bd45fa39ab`。
- 新扩展独立 Spec 和 Standards 均无阻断发现：`trigger-auto-review/review-spec.json`、`post-push-independent/post-push-standards-review.json`，后者 SHA-256 `a8ae58296db533d37a30576613b1c3668bec484f477067cab83e1ee452f93655`，5 文件 scoped diff SHA-256 `15f1cf32e7491f2a358eca77131fbaf446a18a0673f07768b7eab06d753194b4`。两个审查核对旧断言和基线、固定文件哈希，无源漂移；审查不替代统一执行。
- 第三局现场进程仍加载已推送 56369c8（PID 107276 / run 62cb5b238692ece8676c8a70eb414173），不能作为新补修的现场通过证明。三张生产 MSS 普通棋盘 / 选秀负例 560903 / 047562 / 34c918，先独立核图再检查 actual reader / Qt / settled 与请求，均 unknown / none、scope 和已选不变、无新详情查询；`post-push-independent/three-no-detail-negatives-joined-audit.json` SHA-256 `0afdacdeb1db1fa44c7d5e407626f70e674607f1c9da97ddd824eb88066d5798`。
- 17:58:21 UTC 正常点开左装备栏，取得真正暴风之剑单详情；17:58:41.141 生产原图 e9d64884eea188b102cc66a95c528231，SHA-256 `6ecd1d73747ba318f177ec56990a01a37dfc7317cea3cf788b076204f2aa1959`。独立原图主标题 + 预先冻结目录得到 equip / 1001（基础装备），随后真实 reader 为 condition_detail / detail / resolved，单条件请求与独立预期精确一致：18.3 / set18、type equip、targetId 1001、targetName 暴风之剑、空附加过滤，不记本局已选。
- 首次新 HTTP 请求 ReadTimeout（约 15.56 s），没有 response 字节或可用排名。实际 Qt 清旧卡、保留正确条件，显示读取失败与重试；`e9d64884eea188b102cc66a95c528231-joined-audit.json` SHA-256 `261beb905cb4acefdbd655d2f1c0f3fa21f92bccabf5b33485d42aff8ff1d623`，不称首次统计成功。
- 18:05:34.723 正常同条件重新提交，query 75ef2f0914d3ac63242fbf47131fd774 得到新 HTTP 201 / JSON code200、success true，非缓存；原 response 176258 bytes。独立投影先从 38 行按样本 >=50 保留 21、排除 17，再均排升序，首 8 ID 为 120 / 87 / 104 / 113 / 116 / 99 / 114 / 100，均排 3.89 / 3.96 / 3.98 / 4.24 / 4.25 / 4.26 / 4.27 / 4.41，两位出场率不乘 100。18:07:26 实际 Qt 快照 8a14a23a026c441caf5d97a343a08f7f，8 个真实 card 字段、顺序和统计文字全部一致，条件 1001、已选空、jobs0。实际 viewport 仅首两卡完整和第三标题可见；不冒称同一 viewport 已显示全部八卡。`75ef2f0914d3ac63242fbf47131fd774-success-joined-audit.json` SHA-256 `226ae02b22cb26389e0a245e6dcd439fb1fc6721ec36328cf4df603311ad2ee8`。
- 点备战英雄曾实际展开阿兹尔右详情，但取条件时已切回合、详情关闭；后一次在淘汰结算，均不能算英雄识别正例。第三局第八名，18:11:42 通过正常 quit 槽关闭自己 QA，确认 PID 消失，保留退出记录；游戏通过正常结果页返回大厅。新的受影响检查、普通自动路径性能对照及公共 / 私有 / mutations 在 `validation-automatic-final/` 串行执行，期间停止游戏操作与实机捕获。

## 补修受影响检查与性能对照（2026-10-11 02:19）

- 受影响 10 套件共 129 个实际方法全部 passed，errors / failures / skips 为 0，实际 native exit 0；unittest 47.749 s，进程 48.985 s。`validation-automatic-final/affected.run.json` 和原日志绑定 313 文件冻结，前后零漂移；run report SHA-256 `b534fd052379eb2d1d71d24e4123bea125d26fea207cb478ea1b7d2c51acafbd`。
- 普通自动路径串行对照使用 `trigger-auto-review/benchmark_ordinary_auto_capture.py`，旧 56369c8 内存加载与当前工作树各 8 次空闲 / 自动截图忙单次 / 自动截图忙六连点。两版本空闲各 8/8；旧版两个忙场景各 0/8 执行，新版各 8/8，且每次一份 fresh manual capture / 一次真实 ConditionReader，巨人腰带 1007 与预先批准 oracle 一致，已选资源均为 0。
- 两版本实际 native exit 0，进程 21.552 / 11.966 s；250 ms 受控阻塞后，新版按钮到捕获中位数 250.972 / 250.001 ms、到 reader 结束 411.077 / 420.606 ms，P95 437.508 / 435.942 ms，GUI 心跳间隔 P95 约 11.7 ms。旧版没有执行的请求不能比较读取耗时；固定原图 / 控制窗口和 HTTP、排除引擎预热，不能推断现场截图 / 网络耗时、游戏 FPS 或物理按键。
- 对照 Mock 调用历史保留图片副本，工作集阶梯增长不能作为生产泄漏证据。baseline / final 原报告 SHA-256 为 `7ea11426507511f6b7e158ba1848876b6ecb3ba271ce7ee4be05bfa157af50fe` / `d94136674923c63435f04c41648a28236a789d201f8c494628532905333a39b1`。后续公共 / 私有 / mutations 仍在严格串行执行，尚不计最终统一通过。
## 补修公共验证（2026-10-11 02:25 起追加）

- 公共命令 `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation-automatic-final/public.json`，实际 native exit 0，471.062 s。816 实际方法全部 passed，35 新增方法逐项执行；errors / failures / skips 为 0，313 文件零漂移，旧 16 调度方法 AST 保留。REG 25 / 226 / 25、356 显示检查和历史保护全通过，source_gaps 为空。
- public report / log SHA-256 分别为 `6879cf2dafedcde157f3c454396021f237a0b79be1a6fcb3fa6cf4948a491304` / `351554cdae7b130ecdacf5d722320e1041c131b445fb38c2d031ea08e02e64cd`。7 私有扩展明确 not_run；31 批准图仅 schema 检查 / 31 not_run，不能计为原图回放。私有统一入口及 mutations 紧接其后串行执行。
- 纯说明 `docs/testing/regression-accumulation.md` 同步当前 31 批准数量、第 31 拥抱 I 记录及第三局 BF1001 真正现场证据链接；明确 BF 尚未单列自动回放基线，保留硬件限制。独立核对全部 4 个本地链接存在、旧 30 entries 完整相同、e9 失败与 75ef 重试审计支持文义，`git diff --check` exit 0。文档 SHA-256 `6a54d0bac3ce9c57796f00e81f180409dd9ced59b32ecd273b1461d7777f6070`，不属于运行冻结范围，不因此重跑或改变原图/源码。
## 补修最终统一验证（2026-10-11 02:34）

- 私有命令 `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref c2f1b2b18373c7a0077181abff4b0503a5582d8c --report work/live-match-20261011-r1/validation-automatic-final/with-private.json`，actual native exit 0，486.138 s；839 实际方法全部 passed、35 新增方法全部执行，errors / failures / skips 均 0。7 私有套件 23 方法实际 passed；31 批准文件 verified、31 身份回放 passed，total36 / pending5，待核项不计通过。
- 私有报告 / 日志 SHA-256 `ed19ceaae71db7b348b35428f94008b3b296c582fa69dd1b8964ddfaff0e608a` / `372e2d7fba39b0d725c9acf80e02d779aac21d743aea9c61a71edcdf925dab02`。REG 25 / 226 / 25、356 显示检查全部通过，source_gaps 为空，313 文件再次零漂移。
- 故障注入命令 `work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report work/live-match-20261011-r1/validation-automatic-final/mutations.json`，actual native exit 0，3.279 s；8 项逐项 caught、0 escaped，报告 SHA-256 `b25db0a17de94b7dfb35450df55b250d697716c478c105847e4775dd6339361b`。
- `validation-automatic-final/final-summary.json` SHA-256 `3508f0d8b00f28360637200bf368cc2afa438cfd0290da19b22a1db3203f9d2c`，19 项断言全 true：受影响 / 两份对照 / 公共 / 私有 / mutations 六阶段严格串行，源冻结313项零漂移、新35方法全部实际执行、旧16 AST不变、旧25主题181引用25夹具及30原图哈希完整保留。受测 tracked diff SHA-256 `ea4c9b0bc4377794fd63dff046996abf2472cbc16a5b18472bf40769647133a1`；报告 head563加已测dirty diff，起始比较仍是c2f，尚不冒称干净clone或第四局证明。
- 本轮补修上库仅7明确文件：app / condition_controller / test_condition_trigger_priority、regressions、主设计、regression-accumulation说明、此验收记录；不暂存其他人的流程 / 打包 / 索引改动。新的源码SHA、远端CI与重启游戏证据将在后续追加。