# 2026-10-21：中文前缀与图标品质识别实施

## 目标与范围

- 用户授权按已核对思路实施，做好设计、回归和验证，避免其他模块故障及额外时延；本机运行版本验证后更新。设计为[前缀与品质规格](../specs/hex-family-quality-recognition.md)。
- 开工根 `E:\tft-helper`、分支 main、HEAD `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。已有多轮其他未提交修改，未重置或批量暂存。
- `work/suffix-recognition-20261021/initial-source.json` 及 `baseline-source/` 保存 361 份开工源码/文档；初始 diff、status、运行设置另存。原图及独立批准答案不改写。
- Python `work/p0-runtime/Scripts/python.exe` 3.12.14。范围为图标品质新模块、审核家族规则、Vision 的显式可选通道、相应测试/fixture/回归登记/文档。其他运行模块只做回归验证。
- 本轮相关 REG-019、REG-024、REG-025；先实施 19 个纯罗马家族，未证实阶段的 plus 家族不猜 ID。

## 设计、正确答案与红绿证据

- 独立来源为当前目录四源一致的 19 家族/34 成员及 46 份批准原图。使用上轮原像素手工颜色检查及冻结目录品质，不能用新分类输出生成答案。
- 库存代理 `family-agent/red-01.txt`：新接口空实现对“完整拥抱前缀＋银色”的行为断言失败，非 import/setup 失败；后逐个扩展能力与负例。
- 图标模块、Vision 集成的真实失败、方法 ID、fixture SHA 及修后结果在完成后追加；未发生的检查不记通过。

## 实际检查与状态

| 项目 | 命令/实际操作 | 当前结果 | 证据与边界 |
|---|---|---|---|
| 开工快照 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-recognition-20261021/snapshot.py` | passed：361 文件复制和哈希 | `initial-source.json`、`initial-diff.patch`、`initial-status.txt` |
| 隔离基线首次预检 | 冻结 baseline-source 运行私有统一入口 | failed：私有病例路径为 junction，被保护逻辑拒绝；测试尚未执行 | `baseline-validation.log`；保留失败，不放宽保护逻辑，改用真实文件副本 |
| 身份规则 TDD | 精确命令和逐阶段 red/green 保留于 `family-agent/` | passed：22 项 | 新接口行为先失败后实现；不改旧 core 合同 |
| 图标、集成及旧标题回归 | 下列针对性命令 | passed：115 项，其中新增 50 项 | `lazy-quality-green-full.log`；旧标题 31 个方法所在文件逐字节未改 |
| 根目录公共及私有门槛 | 下列 `validate_data.py` 命令 | passed：995 项，0 失败/错误/跳过 | 356 项展示、25 主题/402 方法引用/46 fixture；46 份批准原图均通过 |
| 最终识别故障注入、数据故障注入 | 下列两种工具 | passed：9/9、14/14 被捕获 | 不写生产源码，不改正确答案；基线新 50 项先通过 |
| 串行性能与独立审阅 | `review-agent/profile_compare.py` 第四轮 | passed：固定 10 场景，原预算 0 异常 | 每版 5 次预热/50 次正式；无新增 OCR，全部 P50/P95 达标 |
| 干净源码 | 固定 `c83e7259fd6f0554c198a90d50e16ea4f584728e` 跑自身统一入口与故障注入 | passed：929 项/0 失败错误跳过，8/8 注入被捕获 | 356 展示、46/46 批准原图，新 50 方法均实跑；未混入 root 其他 pending 功能 |
| 新包实际 EXE | 全新构建、仓库外独立解压，离线和 online+9 原图验收 | passed：两次 exit0/nested passed | 3023 文件核验；9/9 完整图的场景、回合、三 ID、状态及槽位一致；HTTPS/头像通过 |
| 本机更新 | 安装 v0.2.17、切换 EXE 快捷方式、按已有退出合同重启源码助手 | passed：新进程 ready/automatic=true、配置字节不变 | 旧 v0.2.16 留存；未实测现场游戏或另一实体电脑 |
| 远端 CI/公开 Release | 本轮要求重新打包并更新本机，没有要求远端上库或公开发布 | not_applicable | 本地提交与包 SHA 留档；没有推送/tag/公开 Release |

## 追加执行记录

实现、复测、审阅、性能和交付结果随后按实际顺序追加；保留失败及限制，不改写历史答案。

### 基线与实现验证

- 原冻结目录的私有素材 junction 预检失败后，保留该目录，改在 `baseline-run/` 使用真实病例文件副本；没有放宽受保护路径检查。基线报告 `baseline-validation.json`：945 项测试，无失败、错误或跳过，46 份批准原图通过。
- 新图标模块 16 项、家族规则 22 项、Vision 集成 11 项；最后一轮针对性检查共 80 项通过（含原有 31 项标题回归）。快照隔离、同帧目录一致及下一帧重查均有先失败后通过的行为证据。
- 已核对私有图标的自动检查为 105 个已知身份中 101 个正确确认、4 个拒识、0 个误确认；这是固定样本验证，不能当作新数据上的总体准确率。透明、动画和不确定图标仍拒识。

### 性能失败与优化记录

- 第一轮 `profile-comparison-initial.json`：10 个场景均未增加 OCR 调用，但目录缺行、重复两项的中位开销超出 5ms 预算，未通过；随后增加局部目录快照和索引复用。
- 第二轮 `profile-comparison-final.json`（文件名不表示通过）：仍有 5 项中位数或 P95 预算异常，未通过；保留全部原数据和预算。随后改成命中字面前缀后才建立目录快照，同帧复用、下一帧重查。
- 第三轮 `profile-comparison-optimized.json` 使用同一组 10 场景、每版预热 5 次、正式 50 对交替运行，并分别记录 OCR 内部耗时和外围处理；本条写入时尚在运行，不能提前记通过。测量期间不并行测试或打包。

- 第三轮完成后：9/10 场景达到原预算，所有 OCR 次数及 P95 合格；暗色拥抱 II 的中位数增量 5.210ms，超过目标 0.210ms，仍记录为未达预算。组件探针显示首尾两张非审核家族卡的图标处理合计约 1.91ms；该探针只定位成本，不能豁免整帧异常。
- 随后新增“不属于审核家族时不处理品质像素”的公开帧接口回归，旧实现先失败（`lazy-quality-red.log`），改为延后、每卡最多一次品质读取后通过。未知品质仍保留旧路径并验证不重复读取。`lazy-quality-green-full.log`：115 项相关测试通过；其中本轮新方法为 50 项。
- 第四轮 `profile-comparison-lazy-quality.json` 继续使用原 10 场景、5 次预热和 50 对交替运行，原预算不变；本条写入时尚在运行。前三轮数据和未达标结论均保留。

### 最终源码结果（08:55 后追加）

第四轮完成，报告 `review-agent/profile-budget-lazy-quality.json`，原始报告 SHA-256 `6bddaa74dae7c6c91849be1f5a22162a5f1658d1c0013f5d00d42cd3c03c72a1`。普通图整帧 P50 增量 0.736ms；暗 II 为 -1.835ms；嘀 I 为 -62.630ms、OCR 17→13 次。其余场景 OCR 次数不增加，目录缺失控制的最大正 P50 增量为 2.969ms；每场 P95 均在原先 max(5%,10ms) 增量预算内。这里只验证同机、同 engine、固定素材的 warm `analyze_fast`，不包含捕获、HTTP、Qt 发布、首次模型加载或现场游戏 FPS。重复 50 次不计作 50 张独立图片。

最终代码绑定（根目录）：

- `vision.py`：`816c2d93110907324e5f4164a7d50e9cb8e2ec012b8e92895c11fbf8b836b867`
- `hex_family.py`：`91121bb2eec67ebd38d08516b8775c2bd66887c5efb740d44899537adf0c5573`
- `hex_quality.py`：`90e0746930bda4534476ec7b505d226957f2bac743f6aac4ecacaec05dd1e416`

独立审阅 `review-agent/final-review-rebind.json` 与标准轴检查没有未解决生产阻断。`scope-preservation.json` 核对开工 361 文件，357 份字节未改，4 份已有文件仅为本轮允许范围（Vision、动画规格、记录索引、回归登记）。新模块、测试、图标和记录单独新增；已有私有原图、答案、批准哈希均保留。

实际执行命令（Python 3.12.14）：

```powershell
# 以下针对性命令在 outputs/companion 执行。
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 -m unittest test_hex_quality test_hex_family test_hex_quality_integration test_title_consensus test_roman_title_context test_roman_title_context_contract test_dim_hex_title test_hex_title_variants test_title_retry_views test_title_catalog_boundary test_fast_title_regression test_vision_guard test_roman_glyph
# 以下在根目录执行。
& work/p0-runtime/Scripts/python.exe -u -X utf8 work/suffix-recognition-20261021/check_final_mutations.py
& work/p0-runtime/Scripts/python.exe -u -X utf8 work/suffix-recognition-20261021/register_protection.py
& work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report work/suffix-recognition-20261021/final-validation.json
& work/p0-runtime/Scripts/python.exe -u -X utf8 tools/check_data_mutations.py --report work/suffix-recognition-20261021/data-mutations.json
```

统一入口实际退出 0，995 项运行 302.874 秒。`final-validation.json` 明确无失败/错误/跳过；`bug_cases` 为 46 份批准通过、15 份未审核、0 无效/失败/跳过。未审核项继续 pending，不计通过。项目批准基线 required=46、verified=46；新增 50 方法/10 fixture 已进入 REG-019 及统一报告。`final-recognition-mutations.json` 对单票、丢弃完整标题否决、过滤未知竞争者、忽略品质、暴露可变目录、重复像素计票、少读第三视图、无用颜色处理、重复读取未知颜色九种错误，均由行为断言失败拒绝，0 setup error；生产源码前后哈希相同。数据故障注入 14 种均 caught。

### 干净交付源码

复用已附加的干净工作树 `C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper`，开工 `41761604a22255240d73e19009126767d76c2dd1`、分支 `codex/roman-suffix-20261020`。本地实现提交 `4544000d601b63eb85284cd72f33f95a14483822`，动画规格补充提交 `c83e7259fd6f0554c198a90d50e16ea4f584728e`。仅 24 个明确路径；相对根目录保留旧有 8 行诊断块的差异，没有混入其他未提交运行模块。旧登记和 fixtures 全保留，旧测试文件未覆盖。详细窄 diff、哈希与显式暂存审阅保留于 `package-agent/`。包源码需另跑完整私有门槛及真实 EXE 检查后才记通过。

### 干净门槛及 v0.2.17 包验收（09:07 后追加）

以下均在上述干净工作树、同一 Python 3.12.14 执行，高负载串行：

```powershell
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 41761604a22255240d73e19009126767d76c2dd1 --report work/suffix-recognition-20261021/clean-validation.json
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/check_data_mutations.py --report work/suffix-recognition-20261021/clean-data-mutations.json
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 packaging/build_windows.py --version 0.2.17
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 packaging/verify_windows.py dist/TFT-DataJ-0.2.17-windows-x64.zip --online --recognition-fixture E:/tft-helper/work/suffix-recognition-20261021/package-agent/exe-recognition-v0.2.17.json
```

全部命令退出 0。干净门槛 929 项、0 failure/error/skip，356 展示、25 回归/317 方法引用/43 fixture；新 50 个方法均 passed。46 份批准原图及两份批准基线完整性核验均 46/46。干净 checkout 自身数据注入为 8/8 caught，不能把 root 的 14 项数目移作此处结果；两处差异来自刻意隔离的其他旧 pending 功能。报告原件与命令归档于本轮 `package-agent/clean-validation.json`、`clean-data-mutations.json`、`package-delivery-v0.2.17.json`。

构建从源码重新执行 PyInstaller Analysis/PYZ/EXE/COLLECT，没有 `--skip-build`，依赖版本已核对、没有 pip 升级。构建后的自动离线真实 EXE 验收为 exit0/report.status=passed，37.56 秒，已先另存 `package-agent/offline-v0.2.17.validation.json`；后续 online 为 exit0/passed，43.81 秒，另存 `online-v0.2.17.validation.json`。两次均核对 3023 个文件。online 实际执行 `DataJ HTTPS and real hero portrait`，外部 9 份批准完整三槽原图均 passed，另 3 份相关但含 null 槽的原图没有强填 ID 或混入此接口；它们仍由完整私有统一入口保护。

包身份：

- 版本 `0.2.17`；`base_commit=c83e7259fd6f0554c198a90d50e16ea4f584728e`、`working_changes=false`。
- ZIP `dist/TFT-DataJ-0.2.17-windows-x64.zip`，281175859 字节；SHA-256 `5755e186143287fccf6f8746aba617a608c34f724737a4743270020cf77753e2`。ZIP、checksum、online 报告已逐字节核对并复制到根目录 `E:/tft-helper/dist/` 留存。
- 包 `vision.py` 来源 SHA `8255527a5d8c74e0f7ed1f5ca0324993e1301b25bbca09c5c9451a37b7dd7612`，相对 root 仅保留上述旧有 8 行诊断差异。`hex_family.py` 与 `hex_quality.py` 来源 SHA 与 root 最终绑定完全相同。

### 本机更新与完成边界

使用 `work/suffix-recognition-20261021/install_validated_package.py` 校验 online 成功报告及 ZIP SHA，解压到新的 `C:/Users/Robin/AppData/Local/Programs/TFT-DataJ/v0.2.17/TFT-DataJ`，安装后再次核对全部 3023 文件。旧 `v0.2.16` 未删除。`D:/Desktop/TFT-DataJ.lnk` 从 v0.2.16 改指新 EXE，备份旧 shortcut 并读回确认；`D:/Desktop/金铲铲 DataJ 助手.cmd` 仍指 `E:/tft-helper` 源码入口，本轮新逻辑已在该源码中。

源码重启按现有 owned Qt 线程的退出合同执行，未强杀或向游戏发送输入。首次预检因命令行使用正斜杠而退出，旧进程未受影响；将预期与实际路径两侧一致规范化后，严格所属路径/Pythonw 校验仍保留，旧 GUI PID196812 正常退出，旧 launcher190940 也已结束。新 launcher202668、GUI206544；09:07:38 状态 ready、automatic=true，GUI Responding=true；`input.ini` 与重启前逐字节一致。审计器读取 Windows 反斜杠 source_hashes 键时先安全退出，统一路径键后完成核验；未改包或生产源码。具体证据为 `local-install.json`、`shortcut-update.json`、`source-restart-quit.json`、`source-restart-initial-preflight.json`。

完成声明限于已核准 19 个纯罗马家族的新增证据通道、根目录/隔离目录回归、已批准原图、同机固定图时延、实际 EXE 和本机入口更新。品质不明、目录漂移或完整标题冲突继续保守；plus/混合家族阶段规则未核准，保持原路径。15 份未审核病例不算通过。未启动实际对局，没有将这些结果当作物理侧键、MuMu 现场合成、游戏 FPS、另一实体电脑或未见新画面的证明。
