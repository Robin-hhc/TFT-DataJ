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
| 身份规则 TDD | 精确命令和逐阶段 red/green 保留于 `family-agent/` | in_progress | 新接口行为先失败后实现；不改旧 core 合同 |
| 图标 TDD、集成回归、完整门槛、故障注入 | 完成后记录实际命令与报告 | not_run | 不能借用上一轮绿色结果 |
| 串行性能与独立审阅 | `review-agent/profile_compare.py` 已准备场景清单，正式运行待最终代码 | not_run | 记录 OCR 次数、P50/P95、真实原图和受控目录/冲突场景边界 |
| EXE、本机更新、Git/CI/发布 | 验证通过后记录各项实际交付 | not_run | 不把源码回归当作 EXE/真实游戏验收 |

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
