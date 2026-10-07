# 问题画面归档与核对后复验（2026-10-07）

## 实现范围

助手将识别或数据查询失败时已经取得的 MuMu 游戏画面保存在本机，供后续逐图核对。自动归档复用现有截图，不增加自动截图或 OCR 次数，也不自动上传图片、日志或核对结果。演示和离线实例禁用游戏问题归档。

自动记录的条件包括：

| 场景 | 归档条件 | 原因字段 |
| --- | --- | --- |
| 海克斯选择 | 三个槽位中有身份未确认 | `hex_unresolved` |
| 海克斯选择 | 身份已确认，但阶段未确认 | `hex_stage_unconfirmed` |
| 海克斯统计 | 已识别 ID 缺少对应阶段的有效全局数据 | `hex_data_gap` |
| 海克斯统计 | 全局或固定阵容查询失败 | `hex_query_failed` / `hex_comp_query_failed` |
| 装备选择 | 已确认选择标题，3–5 个槽位中有身份未确认 | `item_unresolved` |
| 装备统计 | 已识别装备缺少全局数据，或查询失败 | `item_data_gap` / `item_query_failed` |
| 从游戏取条件 | 用户触发后未确认详情身份，或读取异常 | `condition_unresolved` |

正常识别成功、后台看到的普通未知画面、未确认装备选择标题、装备选择中已明确排除的基础装备等，不自动形成问题样本。查询失败归档还需通过当前会话、游戏前台和画面新鲜度检查；迟到或失效的回调不能把旧画面写入新会话的记录。

`condition` 领域只在用户点击“从游戏取条件”或按侧键触发读取后记录失败，复用该次已捕获的完整游戏图；即使结果为 `unknown`，也可作为明确用户操作的故障证据。已确认身份、待人工选择的歧义候选及转入海克斯/装备选择页统计的结果不走此归档路径。完成回调须先通过当前 token、窗口和前台检查，再调用 `observed_condition`；不会为归档重新截图或 OCR。海克斯及装备选择的既有规则不变，基础装备可以是详情取条件的合法身份。

“识别 / 设置”页提供两个按钮：

- **记录问题**：收起助手并返回已绑定的 MuMu，读取一次当前游戏窗口。此操作不运行 OCR；即使场景未知，也可保存为人工反馈。未绑定窗口时仅在找到唯一有效 MuMu 游戏窗口后继续；捕获失败或目标变化时不保存其他窗口或桌面。
- **记录文件夹**：打开本机归档目录。容量已满或保存失败时，助手显示提示，已确认的识别及排名结果不因此清空。

## 保存、去重与资源限制

| 运行方式 | 保存目录 |
| --- | --- |
| 源码运行 | 仓库根目录下 `work/companion/bug-cases/` |
| Windows EXE | `%LOCALAPPDATA%\TFT-DataJ\bug-cases\` |

以上 EXE 路径是打包后的运行规则；本轮只更新并重启本机源码助手，已发布的 v0.2.5 尚未包含此功能。

每个问题对应 `case-<语义指纹>/`，包含不可覆盖的 `frame.png` 和 `case.json`。指纹包含原因、赛季、统计版本、固定阵容、领域、捕获范围、场景、阶段和选项身份/读数；不使用背景动画产生的 PNG 哈希替代问题身份。同一指纹保留首张完整记录，切换版本或阵容不会误合并。手动记录未知场景没有选项身份，因此另用原始像素指纹区分画面；相同画面重复反馈保留首次记录，动画变化后的画面可能成为另一条人工记录。

默认上限为 **100 例、500 × 1024 × 1024 字节**，通常称为 500 MB。达到任一上限后停止新增，不自动删除旧样本、不循环覆盖。损坏或不完整的既有记录也占用容量，应先人工检查和转存后再整理。

PNG 编码和磁盘写入在专用后台工作池执行，同一时刻最多一个归档任务。自动归档请求之间至少间隔 **15 秒**，同一问题的去重检查先于写盘；手动点击可绕过自动冷却，但仍受单任务、去重、容量和游戏窗口检查限制。归档只暂时引用已有图片，不为保存额外复制整张游戏图；任务完成或失败后释放任务引用。关闭时停止新增任务并等待已开始的保存结束。

`case.json` 记录创建时间、原因、会话/赛季/版本/阵容上下文、当时的实际识别输出、对应目录快照及相关查询证据。`image.sha256` 绑定保存后的 PNG 字节；目录的语义指纹与图片哈希是不同概念。归档不会把实际失败输出转换成正确答案，也不会自动创建 `expected.json`。

详情失败记录使用 `context.domain="condition"`、`source="bound_game"` 和 `frame_scope="full_game"`，证据标记 `user_triggered=true`、`trigger="take_condition"`，目录快照包含 `hex`、`equip`、`hero`、`trait` 四组。它与选择页的 `hex` / `item` 记录分开复验，并沿用同一去重、单任务、冷却及容量限制。

## 装备区域图片的限制

`context.frame_scope` 为 `full_game` 时，图片来自完整游戏窗口。为 `item_band` 时，原捕获仅读取窗口高度约 55% 以下的区域；保存图按游戏窗口原始尺寸补黑上半部分，保持下半部分原像素及坐标。它不是完整屏幕的原始全图。

复验直接读取归档 PNG，不重组、补拍或重新进入游戏。`item_band` 适用于当前底部装备识别路径，不能据此验证上半屏内容、完整游戏阶段、全屏场景或未捕获的信息。人工核对时须保留这一限制。

## 核对后建立 expected.json

新样本是 **pending_review（待核对）**。只有逐图核对后，在同一目录手工提供完整合法的 `expected.json`，工具才将它视为可复验样本。核对依据应来自 PNG 原图和可信目录，不能将 `observation` 中的失败识别结果直接抄作正确答案。`case.json.status` 保持 `pending_review`；复验状态由外部 oracle 的合法性派生，工具不修改原始记录。

以下仅为格式示例，不能直接作为某张图片的答案。必须依据原图确认每个预期 ID、阶段和场景，并填入该图及 `case.json` 的真实哈希和版本信息：

```json
{
  "schema_version": 1,
  "image_sha256": "替换为frame.png的64位小写SHA256",
  "set_id": 18,
  "patch": "18.3",
  "scene": "choice_candidates",
  "round": "3-2",
  "cards": [
    {"slot": 0, "id": "1625"},
    {"slot": 1, "id": null},
    {"slot": 2, "id": null}
  ],
  "reviewed_by": "human:填写核对人或agent标识",
  "review_note": "填写逐槽核对依据；示例中的null也必须有明确预期拒绝依据"
}
```

核对约束：

- `schema_version` 必须是整数 `1`；`image_sha256` 必须同时匹配 `case.json.image.sha256` 和实际 `frame.png`。不得把目录指纹填作图片哈希。
- `set_id` 和 `patch` 必须与记录上下文的值及类型一致，防止跨赛季、历史版本混用。
- 海克斯场景为 `choice_candidates`、`choice_unresolved` 或 `unknown`，并要求 `round`；装备场景为 `item_candidates` 或 `unknown`，不填写 `round`。`unknown` 必须是核对后的明确预期拒绝，不是尚未看图的占位值。
- 海克斯完整行必须包含槽位 `0–2`；装备完整行包含连续的 3–5 个槽位，不能重复或省略。明确预期拒绝整个场景时，`unknown` 可配空 `cards`。
- `id` 使用字符串；`null` 表示有依据的预期拒绝身份，不能用于填补尚未核对的槽位。没有足够证据时保留待核对状态。
- `reviewed_by` 和 `review_note` 均须非空。仅允许各领域声明的字段；每张卡片仅允许 `slot` 和 `id`。加入 `avgPlacement`、`statistics` 等额外断言会判为 invalid，不会静默忽略后报告通过。

详情取条件的 oracle 使用下面的格式，不填写 `round`。其中 ID 和种类必须同时核对；相同 ID、不同种类也会复验失败：

```json
{
  "schema_version": 1,
  "image_sha256": "替换为frame.png的64位小写SHA256",
  "set_id": 18,
  "patch": "18.3",
  "scene": "condition_detail",
  "kind": "equip",
  "cards": [{"slot": 0, "id": "1007"}],
  "reviewed_by": "human:填写核对人或agent标识",
  "review_note": "逐图核对主标题与版本目录；不可把穿戴者或正文中的名称当主标题"
}
```

条件领域的严格约束如下，原有海克斯与装备 oracle 格式保持不变：

- `scene` 仅允许 `condition_detail` 或 `unknown`；顶层必须提供 `kind`，仅允许 `hex`、`equip`、`hero` 或 `null`。`trait` 目录用于名称解析上下文，不是本次支持的详情身份种类。
- `condition_detail` 必须恰好一张 `slot=0` 的卡片。确认身份时，`kind` 和字符串 `id` 均须非空；有依据地预期拒绝身份时，两者同时为 `null`。
- `unknown` 必须同时使用 `kind=null` 和空 `cards`。它表示不应填入详情条件，不能作为未核对的占位答案。海克斯/装备选择优先路由在详情复验中归一为 `unknown`；它们不能通过正确详情身份的 oracle。
- 实际结果只有 `status="resolved"` 才读取 `entity.kind` 及 `entity.id`；歧义结果不能冒充已确认身份。报告中的 `actual.route` 和 `actual.reason` 仅用于诊断，不能作为 oracle 的额外断言字段。
- 顶层仅允许 `schema_version`、`image_sha256`、`set_id`、`patch`、`scene`、`kind`、`cards`、`reviewed_by`、`review_note`。哈希、版本、审阅说明、文件与路径安全检查沿用共同规则。

这次真实巨人腰带故障的原图、错误种类注入及 HTTP 条件序列化证据见 [详情取条件修复与验证](condition-detail-20261007.md)。

## 可执行命令

以下命令在仓库根目录、安装运行依赖的 Python 3.12 环境中执行。开发机可将 `python` 换为 `work\p0-runtime\Scripts\python.exe`。问题原图复验工具只读样本，不联网、不捕获窗口、不进入游戏；只有复验合法 oracle 时才初始化本机 OCR 模型。`condition` 原图通过 `ConditionReader(Vision, EntityResolver).read` 读取，解析器使用记录时的完整目录快照。

先列出待核对和非法记录，**不运行 OCR**：

```powershell
python -X utf8 tools/validate_bug_cases.py --report work/data-validation/bug-cases-inventory.json
```

核对完成后，仅对合法 `expected.json` 绑定的原图运行识别复验：

```powershell
python -X utf8 tools/validate_bug_cases.py --run-reviewed --report work/data-validation/bug-cases-reviewed.json
```

从源码工具检查 EXE 保存的本机记录：

```powershell
python -X utf8 tools/validate_bug_cases.py --cases-dir "$env:LOCALAPPDATA\TFT-DataJ\bug-cases" --report work/data-validation/exe-bug-cases-inventory.json
```

需要实际复验时，在该命令中再加 `--run-reviewed`。读取单张 PNG 的真实哈希可用 PowerShell 的 `Get-FileHash -LiteralPath "完整frame.png路径" -Algorithm SHA256`，将哈希转为小写后与记录比较；这一步不生成预期答案。

统一验证入口默认运行纯归档/复验单元测试，不读取私人问题图库。增加 `--include-private` 后，会运行原有私人截图扩展，并自动复验归档中已合法核对的样本：

```powershell
python -X utf8 tools/validate_data.py --include-private --release-gate --report work/data-validation/with-private.json
```

指定 EXE 或其他本机归档目录时使用统一入口的 `--bug-cases-dir`：

```powershell
python -X utf8 tools/validate_data.py --include-private --bug-cases-dir "$env:LOCALAPPDATA\TFT-DataJ\bug-cases" --report work/data-validation/with-exe-bug-cases.json
```

两个入口均拒绝将 `--report` 写入所选样本归档目录，也拒绝经过 symlink/junction 的样本或报告路径；外部报告使用原子替换，避免经硬链接覆盖原图。

## 如何解读结果

独立工具的 `summary` 分别列出 `pending_review`、`reviewed`、`invalid`、`passed`、`failed` 和 `skipped`。默认清单中，即使 oracle 合法也只标记 `not_run`，不计通过；缺少 oracle 的样本保持 pending，非法/不完整 oracle 单列 invalid。

**pending 不是通过。** 没有已执行的合法复验时，整体状态为 `pending_review`、`not_run` 或 `no_cases`，不能报告“问题原图回归已通过”。pending 本身不会使命令失败，因此退出码 `0` 不能替代状态和计数检查。原图哈希变化、版本不符、缺失/非法文件、非法 oracle 或识别差异会产生非零退出码。

统一报告在 `bug_cases` 子字段保留上述完整状态和计数。统一报告的总体 `passed` 表示已执行检查通过，不代表待核对图库已验证；未开启私人扩展时，`bug_cases.status` 为 `not_run`。原有私人截图扩展缺资料仍按其既有规则明确失败或跳过，不通过遗漏资料取得全绿。

这条原图复验路径仅核对 **场景、选项/详情身份、详情种类及海克斯阶段**。即使归档原因是数据缺失或查询失败，也不证明排名数值正确、接口恢复、网站显示一致或游戏性能达标。排名显示继续由已有的公开响应快照和实际 Qt 显示回归验证；问题记录中的相关统计行只是后续调查证据。

## 本机原图验收与性能实验

使用已有真实 MuMu 原图 `work/companion/live-validation/choice-2-1.png`，尺寸为 **3840 × 2160**。实验在隔离目录注入“识别失败”的 observation，保存时明确记录 **`evidence.failure_simulated=true`**。归档 PNG 解码后的 RGB 像素与输入图逐字节相同；这里模拟的是失败输出，不是改造图片，也不能将此实验称为现场自然发生的识别故障。

原图经逐槽看图及对应版本目录核对，预期阶段为 `2-1`，三个 ID 分别为 `1023`（应急护甲 I）、`1479`（一，二，三）、`1006`（装备百宝袋 I）。随后调用实际 `Vision.analyze_fast` 复验，并进行了独立的错误预期注入：

| 步骤 | 结果 | 本机证据 |
| --- | --- | --- |
| 保存模拟失败，但不提供 oracle | `pending_review=1`、`reviewed=0`、`passed=0` | `work/bug-capture-20261007/pending.json` |
| 提供已核对的正确 oracle，运行实际 OCR | `reviewed=1`、`passed=1` | `work/bug-capture-20261007/reviewed.json` |
| 仅把 oracle 的 slot 0 错改为 `1006` | `failed=1`、`passed=0`，差异为 `cards` | `work/bug-capture-20261007/wrong-id-detected.json` |
| 恢复正确 oracle，复核原始证据 | `frame.png` 与 `case.json` 的 SHA-256 均保持不变 | `work/bug-capture-20261007/acceptance.json` |

以上证明待核对不会被计为通过，合法 oracle 会驱动真实识别，错误 ID 能被检出，复验不改原图及原记录。验收目录为 `work/bug-capture-20261007/acceptance-cases/`，与日常游戏归档分开保存。

同一张 4K 原图进行三次独立后台保存，记录在 `work/bug-capture-20261007/performance.json`：

| 指标 | 本机结果 |
| --- | --- |
| 主线程提交请求 | 1.28–1.55 ms |
| 后台 PNG 编码及保存 | 177.50–184.04 ms |
| 每张 PNG 大小 | 7,455,923 字节 |
| Qt 计时器最大间隔：空闲基线 | 6.65 ms |
| Qt 计时器最大间隔：保存期间 | 7.12 ms |

三次写入均由单个后台线程执行，实验断言没有额外调用游戏捕获。这是本机三次保存及 Qt 事件循环测量，未并行运行 OCR，不能推导游戏 FPS、全部磁盘环境或长期性能。`work/bug-capture-20261007/bug-actions-ui.png` 留存了实际 Qt 界面截图，“记录问题”和“记录文件夹”按钮显示完整。

本轮统一验证命令：

```powershell
python -X utf8 tools/validate_data.py --include-private --release-gate --bug-cases-dir work/bug-capture-20261007/acceptance-cases --report work/bug-capture-20261007/full-tests.json
python -X utf8 tools/check_data_mutations.py --report work/bug-capture-20261007/mutations.json
```

493 项测试通过，0 失败、0 错误、0 跳过；包括本轮新增的70项归档、复验、后台路由及生命周期检查。356 组冻结响应到实际 Qt 显示回放通过（阵容116、英雄144、海克斯72、装备24），8种错误注入全部检出。统一报告中的隔离问题样本复验另列为 `reviewed=1, passed=1`。日常问题目录的独立清单为 `no_cases`，未把实验样本混入真实游戏问题库。

15:15 已优雅关闭旧源码进程并重启新源码助手，状态为 `ready`、`automatic=true`、`bound=true`；MuMu 进程保持不变。新进程关闭旧的循环诊断截图开关，持久问题归档默认启用。进程及启动时间见 `work/bug-capture-20261007/restart.json`。本轮未发布新EXE，也未进入新的对局；以上实验不替代实际 MuMu 对局端到端验收。
