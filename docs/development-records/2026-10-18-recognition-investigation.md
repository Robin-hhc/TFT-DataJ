# 2026-10-18：近期识别失败调查

## 目标与范围

- 用户目标：检查近期“识别不到”的问题，依据原图、日志和当前实现定位。
- 起始分支：`main`；HEAD：`1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；远端：`https://github.com/Robin-hhc/TFT-DataJ.git`。
- 环境：Windows / `work/p0-runtime/Scripts/python.exe` / Python 3.12.14。
- 开工已有大量未提交的 10-10/12 工作流、识别/来源诊断、预读恢复、外点收起及其测试/文档改动。保留原样；本轮初始状态与 diff 存入 `work/recognition-investigation-20261018/`。
- 本轮首先只读调查；确认新缺陷后按先复现、独立核对、回归、修复、统一验证流程处理。原始截图和日志不修改，未核对病例不计通过。
- 相关历史项：REG-014 / REG-018 / REG-019 / REG-020 / REG-021 / REG-024。

## 调查结论

本轮完成定位，**没有修改识别/查询生产代码；下述两个 OCR 缺陷尚未修复**。不要将诊断探针的成功解释为通用修复验收。

| 原始证据（本地时间） | 当前复现与根因 | 边界 |
|---|---|---|
| 10-16 19:40，`case-2d049c…`，3-2，中间「弑君突刺」 | 原图、品质、描述与冻结目录唯一 ID `10196` 相符；当前 OCR 四次可信读数均为「弒君突刺」，精确目录匹配失败。替换成 10-18 最新目录仍失败 | `catalog_missing_title` 是字符串查不到，不足以证明真实实体缺失。独立像素/目录核对确认这是字形匹配问题 |
| 10-13 23:02，`case-e9518b…`，2-1，中间「拥抱 II」 | 独立原图对应唯一 `10616`；当前返回三次空读数。标题区域最暗颜色通道最大 159，低于 `vision.py` 重试掩码的固定 175 门槛，因此没有进入二值/加宽重试 | 保持原纵向范围的横向裁剪探针能得到两次精确 II（.98186 / .98624），但部分紧裁产生错误 `ⅡI`。不能据少数成功探针直接调整全局阈值并称全部修好 |
| 10-13 23:12，`case-99abb0…`，装备「视界专注」 | 七次可信文字均正确；冻结装备目录没有该项。10-18 22:13 重新请求的当前目录已有 `6079`，仅在内存替换为当前目录即可恢复四件装备全部身份 | 历史缺项与当前缺项分开。历史原图、旧目录和预期不改写；新目录并不证明旧版本/阶段统计存在 |
| 10-15 22:59 的两例及 23:07 一例 | 三例海克斯身份均为 3/3 resolved。一例 3-2「扩展包+」全局快照无 `20731`；另两例阵容补查受 ReadTimeout 后的共享冷却拒绝 | 这些是来源统计/请求失败，不能用增加 OCR 重试修复。超时源头与精确请求来自归档诊断，未在本轮重发历史统计请求 |

### 当前实际运行版本

- 10-18 当前活动进程 PID `157656` 来自 `%LOCALAPPDATA%/Programs/TFT-DataJ/v0.2.5/TFT-DataJ/TFT-DataJ.exe`。
- 独立核对 manifest `version=0.2.5`、`base_commit=53bab236f8cad0ef7d8cf6023d6162e919e06222`、`working_changes=false`；实际 EXE SHA-256 `e6d69d4575aa5ce1bd754a3ba03a56e9b9c579ebcbcd50fd2165127474502cf0` 与 manifest 对应项一致。本轮没有重算所有包内 DLL 哈希。
- 源码运行日志停在 10-16，今晚的活动进程不是当前源码。修改工作树不会更新这个 EXE。旧安装版没有问题原图归档目录，今晚的 `diagnostic_frame` 全部为空，无法逐项独立核对。
- 今晚冻结日志中 `ocr_complete` 826 次，其中 105 次含未确认项、共 131 个未确认槽位观察。599 次 `unknown/no_refresh_glyphs` 包含普通棋盘画面，不是 599 个问题。重复扫描、过渡动画及同一张卡的多次读数不能算作独立对局失败率。
- 今晚日志还出现秘法帮派、珍藏财宝、潘朵拉装备等罗马数字/后缀读数以及同名歧义。没有原图，不为它们生成接受答案，也不宣称更新版本即可全部修复。
- 另用批准的公共「秘法帮派 II++」裁图对照算法：在当前 Python/OCR/模型环境中，加载 v0.2.5 对应准备提交 `53bab236…` 的 Vision、core、名称归一化仍拒识，当前 HEAD 与工作树均识别为 `30679`。两边七次读数相同，旧逻辑未组合跨重试组的两个完整标题读数。主报告 `known-arcane-v025-prepared-comparison.json`、当前/HEAD对照 `known-arcane-title-comparison.json`。这是内存加载源码对照，不是打包 EXE 验收或今晚原图回放；旧报告中 `091d657` 对照使用当前 core，主结论以精确 `53bab236` 三模块对照为准。

### 目录来源发生变化

10-18 22:13 单次 GET `https://www.dataj.cc/api/web/gamedata?setId=18` 返回 HTTP 200：268 海克斯 / 158 装备；原始响应 SHA-256 `bd30489cdb796bf869cb3b5c59cf73895539a5abbae2dd7750b88776b0860ebe`。当前已有「战时补给：女神之泪」`10581` 与「视界专注」`6079`（来源 version `18.18.4`）。旧 10-12/16 归档海克斯目录 263 行，其中女神之泪缺失。该历史结论当时成立，现在须以本轮新响应为准。

当前「致命丽花」仍有 `20760` / `30760` 两个同名、同描述、不同图标条目；本轮没有独立依据合并 ID。来源 `season=S19` 与请求 `setId=18` 的元数据差异也不单独作为跨赛季故障证据。

进一步用 SQLite `mode=ro` 检查磁盘缓存：源码目录在 10-16 19:27:25、EXE 目录在 10-18 13:22:01 获取的 `/gamedata` 已是 268 / 158，两个完整目录 JSON 值均与本轮新响应完全一致（canonical SHA-256 `f2f7cedba0d9eda7b141069cbdc87879bda5a688537cb9958ac831e05805368c`）。因此**没有当前磁盘目录内容过旧的证据**，不能把旧归档缺项解释为今晚这两项仍缺失；进程内存目录未直接读取。原件 `cache-catalog-summary.json`。

当前源码在启动、手动「更新目录」、版本切换时调用 `load_catalog`；`DataJ.catalog()` TTL 3600 秒，仅发起请求时检查 TTL，没有发现定时刷新。`/gamedata` 请求键仅含 setId、不含 patch。这些是当前代码事实，不等于已证明今晚出现目录刷新缺陷。

## 原图核对、复现与检查

证据目录：`work/recognition-investigation-20261018/`。原始截图仅保留本机；文档不发布玩家画面。

| 检查 | 实际命令/操作 | 结果与报告 |
|---|---|---|
| 开工身份、Python | `git rev-parse --show-toplevel` / `git branch --show-current` / `git rev-parse HEAD` / `git remote -v` / `git status --short`；`work/p0-runtime/Scripts/python.exe --version` | passed；起始 SHA 如上、Python 3.12.14；`initial-status.txt`、`initial-working-tree.diff` |
| 归档与运行包盘点 | 只读解析 50 份源码归档、活动进程/manifest、冻结两份 pipeline；10-12 起新增 10 例逐一核对图片绑定哈希；安装包 EXE 单文件哈希核对 | passed；`archive-inventory.json`、`package-log-summary.json`、`launcher-inventory.json`。34 例已有正式 expected，另 16 例未登记批准 |
| 三张原图独立核对 | 独立 agent 先查看原 PNG，再核对冻结目录标题、品质及描述；不使用 OCR/observation 生成答案 | `independent-oracle-review.json`。两个 hex 预期分别 `[10752,10196,10632]` / `[20593,10616,20661]`；旧目录装备 `[null,6085,6069,6087]`。这些是诊断 oracle 提案，未加入正式基线 |
| 当前源码真实 OCR 复现 | `work/p0-runtime/Scripts/python.exe -X utf8 work/recognition-investigation-20261018/reproduce_recent.py` | **actual exit 1**；两个 hex 的中间 ID 与独立正确答案不同；装备对旧目录的安全拒绝符合预期。原件 `reproduction.json` / `reproduction.log`；首次完整输出 `current-source-replay-before.json` |
| 当前目录受控替换 | 同一真实 Vision / item_vision runner，仅在内存将三个病例目录换为上述单次新响应 | actual exit 0（诊断运行）；`current-catalog-replay.json`：视界专注变为 `6079`，两个 hex 仍拒识。不覆盖旧素材或把新结果写回历史 expected |
| 当前缓存内容 | 对两个 SQLite 文件使用 `file:…?mode=ro`，查询 `/gamedata` 行并与新响应比较完整 data 对象 | passed；两者已具备新目录，`cache-catalog-summary.json`，不修改原数据库、不读取凭据或玩家上下文 |
| 暗标题根因探针 | 保留原图只读输入，执行明确的裁剪、重采样、阈值/反色 OCR 探针 | 三次运行 actual exit 0；`e9518-title-probe.json`、`e9518-adaptive-title-probe.json`、`e9518-padding-title-probe.json`。探针中有错误/低置信结果，全部保留，不只选成功结果 |
| 完整公共/私有统一入口、故障注入 | not_run | 本轮未修改生产代码、正式测试或基线；本轮定位的两个缺陷仍为 RED，未以旧验收记录宣称通过 |
| 文档链接/本轮 diff、原始证据完整性 | 本轮结尾运行，见追加结果 | 不通过删除测试、降低门槛或改写批准哈希消除失败 |

受测源码为起始 HEAD + 当前未提交组合工作树，文件 SHA-256 在 `tested-source-manifest.json`；不是干净构建。源码调查集中在 `outputs/companion/vision.py:106`、`core.py:47`、`outputs/mumu-p0-probe/choice_reader.py:7` 以及目录加载/查询链路。

## 修复顺序与限制

1. 修复暗标题重试的亮度/裁剪边界，以本轮独立核对原图写先失败的固定回归，覆盖罗马数字冲突否决，再完整回放现有批准原图。不能直接把全部 OCR 阈值调低。
2. 「弑/弒」需经审阅的完整标题字形等价规则、至少两个可信读数、目录碰撞/冲突否决和领域限制；不能全局改写繁简字、品质后缀或依统计猜 ID。Unicode 官方材料列出了 [5F11 / 5F12 字形关系](https://www.unicode.org/wg2/docs/n3318-org-Appendix.pdf)，实体身份仍以本轮原图和目录唯一项为依据。
3. 将历史目录缺项与当前状态分开：当前两份磁盘目录已恢复，无依据要求靠清空缓存修复今晚问题。仍须区分主表无数据、精确补查超时、冷却、同名歧义；目录有实体不等于排名链路通过。
4. 修复完成并通过统一公共/私有回放、相关故障注入后，按用户要求另行构建、验收和更新实际运行包。仅更新启动版本不能解决当前源码仍复现的两个缺陷。

本轮未要求推送或发布，没有提交、推送、构建/替换 EXE、重启活动助手或操作游戏。现场物理输入、MuMu 合成器、游戏 FPS、其他电脑均未验证。两处已复现缺陷和无原图的今晚其他观察均明确保留，不称「全部修好」。

## 结尾完整性检查

- `final-integrity-check.json`：本轮记录与索引的本地链接缺失 0、受测源码/台账/批准索引哈希漂移 0、10-12 起十份近期原图绑定失败 0；诊断 oracle SHA-256 `80f975dd52910c8b178f4f89952b48eefb44beb87d930a0fe8b6d3a626fe13bd`。
- `git diff --check -- docs/development-records/README.md` passed；新记录逐行空白检查及 Markdown 本地链接检查 passed。索引开工已有修改，本轮仅追加 10-18 行，原有行与其他人的工作不回退、不暂存。
- 独立 agent 分别核对归档/运行包、原图正确答案、识别源码与探针；最终交叉复核确认「旧目录缺项」不能推广到当前缓存、旧源码对照不能当 EXE 通过、探针成功不能当通用修复。
- 本轮新增版本化内容仅为本记录和索引一行；其他新脚本、日志、JSON、诊断裁图全部留在本轮 `work/`，不发布原始玩家截图。
