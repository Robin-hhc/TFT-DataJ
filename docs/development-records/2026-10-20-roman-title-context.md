# 2026-10-20：罗马数字标题漏识别

## 目标与范围

- 用户反馈近期大量海克斯未识别，怀疑罗马数字后缀；核对近期原图后修复有独立证据的标题读取问题。
- 验收：最新三份“拥抱 I”和一份“嘀个痛快！I”必须正确读取完整标题、身份和阶段；保留旧等级、加号、冲突、低置信度、缺目录和动画拒识边界。统计缺项单独分类。
- 根工作树：`E:\tft-helper`，`main`，开工 SHA `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；存在大量此前未提交改动，开工快照保存在 `work/roman-suffix-20261020/initial-*`。
- 隔离开发：复用既有托管工作树 `C:\Users\Robin\.codex\worktrees\recognition-fix-20261018\tft-helper`；新分支 `codex/roman-suffix-20261020`，开工 SHA `839b20603b7e1feaacd135b502eed51d2e1c27ad`，开工干净。
- 远端：`https://github.com/Robin-hhc/TFT-DataJ.git`。本轮尚未要求远端发布。
- 环境：Windows，`E:\tft-helper\work\p0-runtime\Scripts\python.exe`，Python 3.12.14。当前实际运行根目录源码助手。
- 历史保护：REG-019、REG-020、REG-024、REG-025；既有 36 份批准原图和全部旧 fixture 不变。

## 复现与独立正确答案

- 原始证据：根目录 `work/companion/bug-cases`，10 月 19 日起新增 11 例。原始 PNG、case.json 和原始日志只读保留。
- 独立审阅：`work/roman-suffix-20261020/independent-oracle-review.json`，先看原图及原始像素裁图，再核对冻结目录；SHA-256 `2433044ff992c833413b3192a7bfa4b5f40cd050db86361f098983c3a4ff4584`。
- 10 例海克斯图的 30 张卡有明确身份；1 例装备动画缺标题，应拒识。4 例海克斯标题缺失，另 6 例三张身份已识别但统计来源缺项，不能计为 OCR 失败。
- “拥抱 I”的 I 原图完整；旧紧裁图和识别器输入比例使细后缀掉字。“嘀个痛快！I”被读成 `！！` 或 `！1`。原像素裁图的留白探测见 `context-grid.json`；不重写字符，不降低 .90 置信度。
- 探索过带横帽 I/II/III 及加号的像素判别；它仅是工作目录内的诊断原型，没有身份授权。优先使用可直接读出完整标题的两视图补读。

## 实际检查

| 检查 | 状态 | 证据与限制 |
|---|---|---|
| 近期原图独立核对 | passed | 独立审阅报告；不证明统计排名 |
| 修复前真实像素回归 | failed（预期） | `outputs/companion` 下执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 -m unittest test_roman_title_context -v`，2 项真实 OCR 断言失败；`new-title-red.txt`。初次路径导入设置错误另存 `new-title-setup-error.txt`，不算复现 |
| 受影响测试 | passed | `-m unittest test_roman_title_context test_roman_title_context_contract test_dim_hex_title test_title_consensus test_title_retry_views test_roman_glyph test_hex_title_variants -v` 首次 47 项通过；之后增加两项加号冲突方法，最终由完整入口覆盖 |
| 关闭补读的受控错误 | passed | `check_context_mutation.py` 将新补读路由禁用，两项真实像素回归均失败，0 测试异常；`context-disabled-mutation.json` |
| 数据故障注入 | passed | 隔离根目录执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report E:/tft-helper/work/roman-suffix-20261020/data-mutations.json`，actual exit 0，8/8 caught；不更改根目录另一个任务的 14 项工具版本 |
| 公共及私有统一入口 | passed | 隔离根目录执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 839b20603b7e1feaacd135b502eed51d2e1c27ad --report E:/tft-helper/work/roman-suffix-20261020/full-validation.json`，actual exit 0；879/879、0 failures/errors/skips；356 展示回放通过；25 历史主题/267 方法引用/33 fixture 通过；46 批准三文件校验及精确场景/阶段/身份回放全部通过。source_gaps、extensions 为空。原件 `full-validation.log` / `full-validation.json` |
| 性能对照 | passed（有限） | `compare_performance.py` 只比较两个源码版本的相同原图，预热后各 5 次、交替顺序、同一个模型实例、串行执行；`performance-comparison.json`。拥抱 I 全图中位数 273.444→314.095 ms，嘀个痛快 297.038→299.761 ms；均 15→17 次模型调用。正常标题控制组 234.205→232.417 ms、11→11 次调用。样本量小、存在调度波动，不解释为游戏 FPS 或稳定性能收益 |
| 实际 EXE、物理游戏、FPS | not_run | 本轮当前范围为源码 OCR；不从离线回放推断 |

## 审阅与交付

- 多代理独立核对原始像素、日志、目录与裁图；生产实现和回归仍在进行。
- 开工状态：未提交、未推送、未构建新 EXE；旧进程尚未重启。最终同步和重启结果见后续追加。
- 后续结果追加本记录，保留红色运行及未覆盖范围。

## 实现与保护边界

- `vision.py` 只在尚未识别、存在可信目录 Roman 家族前缀和亮色笔画时，追加原色/灰度自动对比度两个完整标题视图。仅调整全部笔画的上下文；不替换 `1/l/!`、不猜等级、不按 I 推断银色，不增加截图或 HTTP。
- 目录前缀是补读路由，身份仍由原有两次完整精确目录匹配确认；保留全部先前可信读数，等级/加号冲突及重复目录继续拒绝。
- 新增 2 项公共真实 OCR 与 13 项边界契约，覆盖 I/II/III、加号、先前冲突、低置信、数字/l/!、缺前缀、无笔画、目录重名与重复输入；绑定 4 个新匿名 PNG/JSON。原历史 fixture、方法 ID 和原图不变。
- 首次受影响运行发现旧合成 OCR mock 的有限序列被新增两视图耗尽（`affected-first-green.txt`）；只在旧合成输入的新 99×33 视图显式提供空读数，保留旧序列和所有历史断言。独立 AST 对照证明 11 项历史 test 方法完全不变，见 `review-historical-protection.json`。
- 独立审阅发现新增补读可以重复旧二值输入或让新增原色/灰度图完全相同，确定性像素引擎仅一份完整输入即被算成两票；基线对照为拒绝，新分支为错误确认。两项新增回归先失败（`duplicate-context-red.txt`），再以本次读取的尺寸+SHA-256 集合跳过相同新增输入；不跨帧缓存，不改变旧重试调用语义。最终 51 项受影响测试通过，`affected-final-green.txt`。初次和最终独立审阅均保留，最终 `recognition-audit-review-final.json` 无阻塞发现，独立 26 方法通过。
- 新私有 oracle 直接采用实现前独立审阅的 `proposed_expected`，不是回放观察；用登记命令追加 10 例至 46 例，36 条旧记录严格相同。`new-originals-registration.json` 保存命令、逐文件 SHA-256 和登记结果。同期装备动画图保持 pending，其 `unknown`/五空槽与提议空列表的格式差异不纳入本轮识别通过。

## 最终源码验证补充

- 完整门槛固定于起始 `839b206…` + `tested-tracked-diff.patch` 及新文件；`tested-scope-manifest.json` 锁定最终运行源码、测试、台账和新 fixture，`vision.py` SHA-256 `828f067138a541f8c0231f03fcca3a4b75dd38e1b95e8a6195af8884e086f007`。完整门槛后没有修改运行代码、测试、数据或资源；仅追加文档结果。
- 加入重复像素保护后重新串行测量，最终采用 `performance-final-serial.json`：同模型预热、交替顺序、各 5 次。拥抱 I 250.066→290.685 ms，嘀个痛快 247.749→292.211 ms，都是 15→17 次模型调用；正常标题控制 188.071→197.208 ms、11→11 次调用。小样本对照只说明此固定路径的开销，不证明游戏 FPS；初版测量为不同源码，仅作历史记录。`performance-final-comparison.json` 有短时测试并发，保留但不用于性能结论。
- 最终运行 `check_context_mutation.py` 再次确认禁用补读会使两项真实标题回归失败，`caught=true`。独立最终审阅绑定 8 个最终源码/fixture 哈希。
- 隔离目录只放 46 份批准病例；根归档共 61 份，其他 15 份 pending 不算通过。未执行新的对局、物理侧键、MuMu 合成、游戏 FPS、另一台电脑或新 EXE；本轮修复交付目标是正在运行的源码助手。

## 2026-10-21：根目录同步与运行生效

- `git apply --check` 后只应用本轮 `vision.py`、旧 mock 适配和文档补丁；新测试/匿名 fixture 分别复制，台账只追加本轮方法/素材，批准索引只追加 10 例。原有 36 条批准记录保留，初始 19 个无关 tracked diff 块逐字未变，见 `post-restart-check.json`。
- 首次同步脚本在完成变更后的“根目录必须与隔离 vision.py 字节相同”断言退出 1。核对发现根目录原有 8 行拒识诊断分类器，开工 diff 已包含，必须保留；它只分类拒识原因、不赋予身份、不增 OCR。`confirm_scoped_sync.py` 证实剔除这段原有逻辑后与隔离实现完全相同。根 `vision.py` SHA-256 为 `b4f41fe0ac76481fdb500e3ddb026cf8609184b063ac602fff88e9f81aa32cad`，隔离为 `828f067…`，`source-sync.json` 如实区分。
- 根 `outputs/companion` 执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 -m unittest test_roman_title_context test_roman_title_context_contract test_dim_hex_title test_title_consensus test_title_retry_views test_roman_glyph test_hex_title_variants test_regression_registry -q`，actual exit 0，65/65；`root-scoped-tests.log`。
- 根执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_bug_cases.py --cases-dir work/companion/bug-cases --run-reviewed --review-baseline docs/testing/private-bug-baseline.json --report work/roman-suffix-20261020/root-originals.json`，actual exit 0；61 例中 46 已批准精确回放全部通过、15 pending、0 failed/invalid/skipped，46 批准三文件均 verified。没有把待审样本算作通过；主工作树所有其他功能组合不冒称经过隔离的完整门槛。
- 使用已有 `WM_HOTKEY/id53 → QApplication.quit` 退出契约，定向向旧 GUI 进程 `189964` 的唯一所属 GUI 线程投递退出消息。旧应用及启动父进程 `189256` 已退出；未强杀、未发送游戏键鼠。`source-restart-quit.json` 留档。
- 2026-10-21 00:00:36 通过根源码运行环境启动，launcher `190940`、实际 GUI 子进程 `196812`；实际命令路径为根 `outputs/companion/launch.py --start-collapsed`，窗口 Responding=true，新日志无异常，pipeline 中新 PID 进入 `ready`，`automatic=true`。旧进程在 23:54:57 已记录 `game_closed`，当前 `bound=false` 符合游戏已关闭状态，不声称重启后实测游戏绑定。
- 先备份 `input.ini` 与状态。首次按整份字节不变断言退出 1：正常退出将标记最新位置从 `@Point(6 4)` 保存成 `@Point(7 2)`；核对现有 shutdown 写入契约后确认只有这项变化，主面板几何、字号、收藏等其他设置全部相同，未用旧备份覆盖新位置。最终 `post-restart-check.json` passed，固定受测源码 manifest 无漂移。
- 桌面 `D:/Desktop/金铲铲 DataJ 助手.cmd` 仍指向根源码启动入口，本轮修复已加载到当前源码进程。没有重建或覆盖 v0.2.16 EXE，没有推送或发布 Release；这两项未被本轮用户要求。

## 固定源码提交与文档收口

- 本地源码提交：`1d0d3af1e930f249bcc38fde9933a98258f5124d`，分支 `codex/roman-suffix-20261020`，14 个范围文件；显式暂存、暂存区 diff/空白检查通过，原件 `staged-scope.patch`。工作目录报告保留在根 `work/roman-suffix-20261020/`，私有原图未加入提交。
- 提交与 `tested-scope-manifest.json` 的最终源码/测试/目录/fixture 完全一致。后续补充只更新本文及当前批准样本数量说明，不改变运行代码或验收素材，不重复运行重负载测试。
- 没有推送或远端 CI。本轮结果来自上述固定源码的本机隔离完整门槛、主目录专项复验和实际源码进程启动；不能引用旧发布包的 CI/EXE 结果。
