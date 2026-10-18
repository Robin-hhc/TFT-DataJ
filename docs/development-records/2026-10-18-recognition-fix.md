# 2026-10-18：修复字形与暗标题识别并更新本机包

## 目标与范围

- 用户授权：修好「弑君突刺」字形匹配与暗色「拥抱 II」两处识别问题，补充回归，验证后重新打包，并更新当前运行的 v0.2.5。
- 起始提交：`1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；主工作树 `E:/tft-helper` 有其他未提交任务，保留所有改动。
- 隔离实现/验收：`C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper`，分支 `codex/recognition-fix-20261018`。从已提交版本只增加本轮修复及保护，不打包主工作树其他未完成的功能。
- Python：`E:/tft-helper/work/p0-runtime/Scripts/python.exe` / Python 3.12.14；原始命令输出保留在 `work/recognition-fix-20261018/`。
- 独立正确答案及原图哈希沿用[本日定位记录](2026-10-18-recognition-investigation.md)及本机 `work/recognition-investigation-20261018/independent-oracle-review.json`，不从实现输出生成预期。
- 本轮是本机重新打包与更新，未要求公开发布 GitHub Release。源码与包、安装后运行分别记录，不能互相替代。

## 复现与实现

两张真实标题裁图均先运行失败回归，再修改生产实现。`variant-red.log` / `dim-title-red.log` 均 actual exit 1，分别为真实 OCR 无法给出已独立核对的 `10196` / `10616`，没有把 mock 或测试设置错误当作原缺陷复现。

- 字形规则仅允许完整「弒君突刺」在冻结 `setId=18 / id=10196 / level=1 / DataJ hex icon` 身份下与「弑君突刺」等价。共享归一化、其他标题、罗马数字和加号不变；字面目录碰撞停用等价、重复 ID 继续歧义，冲突读数仍否决。
- 暗标题在原白色笔画证据不足时使用已有相对亮度/局部对比检测，只收紧横向背景、保留完整纵向标题范围；两次可信完整读数才确认，错误品质和初始冲突不能被覆盖。
- 包诊断增加外部哈希清单，真正 EXE 核对两张完整原图的场景、回合、三个 ID、三个 resolved 状态与槽位顺序。独立审阅发现原诊断只看非空 ID 的漏洞，补先失败的状态/槽位回归后修正。
- 新增 24 个公共方法登记到 REG-019 / REG-023，四份匿名 PNG/JSON 加入冻结 fixture 索引。确切方法见 `new-registered-test-ids.json` 和 `regressions.json`；旧 fixture 和登记方法不删、不降级。
- 使用 `tools/validate_bug_cases.py --cases-dir work/companion/bug-cases --review-baseline docs/testing/private-bug-baseline.json --register-reviewed-case <确切case-ID>` 登记独立原图 `case-2d049c…` / `case-e9518b…`。批准 34→36，原 34 条全部不变；原 134 份文件哈希全部不变。主工作树另有 14 份未批准病例，未算作通过；隔离副本只复制 36 份批准病例和必需私有测试素材，366 个复制文件逐一记录哈希。

## 实际验证

| 检查 | 实际命令/证据 | 结果与范围 |
|---|---|---|
| 合并受影响测试 | 在隔离 `outputs/companion` 执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 -m unittest test_dim_hex_title test_hex_title_variants test_portable_recognition_replay test_regression_registry -q` | 38/38 passed；`combined-targeted.log` |
| 完整公共与私有统一入口 | 在隔离根目录执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report E:/tft-helper/work/recognition-fix-20261018/full-validation.json` | actual exit 0；864/864 passed、0 failures/errors/skips；356 显示回放、25 历史主题/252 方法引用/29 冻结 fixture passed；36 批准三文件哈希全部 verified，36 精确身份/场景/回合回放 passed，source_gaps / extensions 为空；`full-validation.log` / `source-validation-summary.json` |
| 数据故障注入 | 同根目录 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report E:/tft-helper/work/recognition-fix-20261018/data-mutations.json` | actual exit 0；该固定基线 8/8 caught；保留主工作树另一个任务已有 14 项工具版本，不用它替代本包范围 |
| 新保护受控错误 | `variant-mutations.json`、`dim-title-mutation.log`、`package-replay-mutations.json` | 去掉字形支持/单票授权/去掉赛季限制/停用暗标题检测，以及忽略精确 ID/回合/哈希的错误实现均被对应新回归拒绝；不修改生产文件或预期 |
| 主工作树同步 | 先 `git apply --check`，再应用仅四个本轮生产文件的补丁；新增测试/fixture 单独复制 | 既有来源诊断、预读、外点功能 hunks 保留；24/24 新公共方法在主工作树通过（`root-scoped-tests.log`）。主工作树的全部组合功能不冒称经过本次隔离门槛 |
| 依赖/源码漂移 | `pip check`、逐项匹配 runtime/build 38 个依赖要求；`isolated-tested-source-manifest.json` 对照 | 全匹配；完整门槛后运行源码/台账/fixture 漂移 0。完整门槛受测对象是起始 SHA + 固定差异，提交前仅补文档结果 |
| 真正 EXE 隔离验收/本机更新 | 待构建后追加 | 未以源码通过代替 EXE |

独立审阅原件：`independent-review.md`。本轮未推送或公开发布，远端 CI 未运行；本机完整入口对应固定受测源码差异，不借用旧 SHA 的 CI 结果。

## 更新与限制

新包验证后完成本机更新，现运行 v0.2.16。保留旧 v0.2.5 和用户数据备份；本轮不操作游戏输入。现场 FPS、物理侧键和其他电脑不在本轮静态识别回归结论内。

## 固定源码与实际 ZIP 验收

- 本轮源码提交 `f8400780f73c70762c47949ef184b35ded89746e`，位于本地 `codex/recognition-fix-20261018` 分支。完整门槛后仅补文档，受测源码 manifest 无漂移；显式暂存 18 个范围文件，暂存区 diff/空白检查通过。主工作树未暂存/提交其他任务。
- 干净隔离根目录执行 `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 packaging/build_windows.py --version 0.2.16`，actual exit 0，从头构建，未使用 skip-build。`build.log` 与首轮自动报告 `package-offline.json` 保留。
- ZIP：`dist/TFT-DataJ-0.2.16-windows-x64.zip`，281,160,014 字节；SHA-256 `06a8a715ac061f9e9d578e7304de0df7948eca5a343ac39e8ef4addc2186dbf1`。包清单 `base_commit=f840078…`、`working_changes=false`；3,023 个包文件哈希 verified。未发现问题原图/私人目录混入 ZIP。
- 真实 EXE 联网及精确回放命令：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 packaging/verify_windows.py dist/TFT-DataJ-0.2.16-windows-x64.zip --online --recognition-fixture E:/tft-helper/work/recognition-fix-20261018/packaged-recognition-fixture.json`，actual exit 0，嵌套 `report.status=passed`，包含 `DataJ HTTPS and real hero portrait`。原始报告 `package-online.json` / `package-online.log`，并复制到主目录 ZIP 同名 `.validation.json`。
- 两张完整原图在仓库外中文临时目录、隔离 PATH/Python 环境中由真正 EXE 运行：`3-2 / [10752,10196,10632]` 与 `2-1 / [20593,10616,20661]`，场景均为 choice_candidates，三个状态均 resolved、槽位均 `[0,1,2]`、mismatches 为空。包回放使用独立冻结的共享 S18 目录；源码 36 份批准回放仍各自使用历史归档目录。原始像素及答案未从新实现生成。
- 主目录保留 ZIP、`.sha256`、`.validation.json`，复制后 ZIP 哈希相符。没有推送、创建 tag 或公开 GitHub Release；远端 CI 未运行。后续仅补充本记录时不改变包的源码提交身份。

## 本机切换与运行核对

- 新版部署到 `C:/Users/Robin/AppData/Local/Programs/TFT-DataJ/v0.2.16/TFT-DataJ/`，部署前后按 manifest 核对全部 3,023 个文件。旧 `v0.2.5` 文件保留，原 EXE 哈希仍为 `e6d69d4575aa5ce1bd754a3ba03a56e9b9c579ebcbcd50fd2165127474502cf0`。
- 首次 `CloseMainWindow()` 返回 true，但 20 秒及追加 30 秒等待后旧进程仍在运行，保留 `deployment-first-attempt.json`，未将超时记作更新成功。核对旧包对应源码的 native 热键处理，向旧助手唯一 GUI 线程发送其既有 `WM_HOTKEY / id53 / QApplication.quit` 退出动作，旧 PID `157656` 正常结束，未强杀或注入游戏键鼠。原件 `old-application-quit.json`。
- 旧进程退出后完整备份 `%LOCALAPPDATA%/TFT-DataJ` 到 `work/recognition-fix-20261018/user-state-before-update/`（74 个文件）。`input.ini` 原有每个设置项与新版启动后完全一致；`post-install-state-check.json` 留档。
- 创建稳定入口 `%LOCALAPPDATA%/Programs/TFT-DataJ/启动助手.cmd` 和桌面 `D:/Desktop/TFT-DataJ.lnk`，均指向 v0.2.16。新进程 PID `158792` 的实际路径与新 EXE 一致，GUI Responding=true、旧 PID absent，manifest/source/version 匹配。
- 22:36 本机核对：状态 `watching_stage`、`automatic=true`、`bound=true`，已恢复 MuMu 绑定；新进程实际事件进入既有 pipeline。`running-version-check.json` / `installed-runtime-event-summary.json` / `deployment.json` 是本机证据。启动日志无异常。
- Computer Use 只读发现未返回可控制的助手窗口；此时运行状态已自动恢复绑定，因而未对游戏或助手发送 UI 输入，不把 app discovery 当视觉截图验收。实际 EXE 的静态原图回放、窗口响应和绑定状态是分别记录的证据。

## 最终结论与限制

两处识别缺陷在声明的原图/目录范围内已修复，回归、批准原图全集、冻结显示、故障注入及实际新包均通过，本机已从旧版切换到 v0.2.16。未执行新对局、物理侧键、MuMu 全屏合成、游戏 FPS 或其他实体电脑的专项验收；不以静态回放替代这些范围。主工作树其他未完成变更保留，新包仅包含本轮隔离提交。
