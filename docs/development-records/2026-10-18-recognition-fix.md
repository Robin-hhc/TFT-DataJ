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

仅在新包验证通过后退出旧助手，备份现有设置/数据，在新版本目录部署并启动。保留旧 v0.2.5 以便恢复；不操作游戏输入。现场 FPS、物理侧键和其他电脑不在本轮静态识别回归结论内。
