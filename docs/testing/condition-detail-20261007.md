# 详情取条件修复与验证（2026-10-07）

## 问题与原图证据

用户反馈游戏详情已打开，但“从游戏取条件”没有读到名称。本机从绑定的 MuMu 窗口取得 **3840 × 2160** 原图，保存在 `work/condition-sword-20261007/current.png`。本次图中主标题是 **巨人腰带**，下方穿戴者是 **婕拉**；正确检索条件为 `kind="equip"`、`id="1007"`，不能读取穿戴者名称替代装备主标题。

旧读取器在该原图上返回 `scene="unknown"`、`reason="detail_header_icon_unconfirmed"`，见 `baseline.json`。检测到的浮窗为 `[1920, 354, 2700, 1050]`，原图标区域的明亮行占比为 `89/184≈0.484`，低于 `0.5` 阈值；旧标题区域还碰到了较大的图标。故障发生在详情头部候选验证阶段，尚未得到可确认的主标题身份。

工作目录沿用 `condition-sword-20261007` 名称，但本次独立真实图验证的是巨人腰带。用户口称“大剑”的目录正式名称为 **暴风之剑（1001）**；本次没有它的独立实图，不能声称已验证其识别。

## 修复与操作行为

`condition_reader.py` 仅为普通浮窗 `s18_floating_icon_title` 增加大图标布局候选 `s18_floating_large_icon_title`。相对于弹窗左上角，以弹窗宽度为尺度，新标题区域为 `(0.35, 0.07, 0.97, 0.18)`，图标区域为 `(0.07, 0.07, 0.32, 0.32)`。既有普通、库存和英雄详情裁剪保持原样；候选仍需通过图标可见性及标题边界检查，原候选有效时优先使用原候选。

确定头部候选后，仍只调用一次 `read_name` 读取主标题，再经当前赛季目录解析身份，不通过扫描正文或穿戴者来补猜。选择页仍优先进入原有海克斯或装备统计路径。

“从游戏取条件”按钮会立即读取游戏中已经打开的名称详情。也可直接在游戏按鼠标侧键，无需先点击按钮。工具提示已说明这两种入口；读取成功后填入检索条件并查询，仍需显式点击“记为已选”才计入本局资源，不自动当作玩家已选中。

失败提示区分未发现有效详情、图标未确认、标题触边及主标题未确认，并保留原检索条件。完成或失败回调先检查当前 token、绑定窗口和游戏前台；有效的未确认结果交给 `observed_condition`，复用该次完整游戏图归档为 `condition_unresolved`，不增加截图或 OCR。已确认身份、歧义候选和选择页统计路由不记录为这类失败。实际 Qt 成功界面留存在 `work/condition-sword-20261007/resolved-condition-ui.png`。

## 已执行验证及边界

| 检查 | 结果与证据 |
| --- | --- |
| 读取器定向回归 | 读取器及本机原图检查共 22 项通过，覆盖大图标标题及正文/穿戴者干扰；相关定向检查共 126 项通过 |
| 原有原图回放 | `existing-details.json` 中 21/21 通过；沿用既有开发图片、重复事件及负例，不能视为 21 张新增独立装备正例 |
| 本次巨人腰带原图 | 实际 OCR → controller → HTTP 请求序列化，得到 `equip/1007`，请求 `version="18.3"`、`setId=18`；`acceptance.json` |
| 本局资源 | 成功读取后 `resources_recorded=0`，没有隐式“记为已选”；`acceptance.json` |
| 无 oracle 的真实失败归档 | `pending_review=1`、`reviewed=0`、`passed=0`；`pending.json` |
| 看图核对后实际复验 | `reviewed=1`、`passed=1`；`reviewed.json` |
| 错误种类注入 | 保持 ID `1007`，仅将 oracle 的种类改为 `hero`，得到 `failed=1`、`passed=0`，差异为 `kind`；`wrong-kind-detected.json` |
| 原始证据保护 | 恢复正确 oracle 后，`frame.png` 与 `case.json` 的 SHA-256 均未改变；`acceptance.json` |
| 完整统一检查 | 519 项测试，0 失败、0 错误、0 跳过，耗时 95.701 秒；356 组冻结响应到实际 Qt 显示回放通过；`full-tests.json` |

上述问题记录位于隔离目录 `work/condition-sword-20261007/verified-cases/`，来源是旧读取器在真实游戏原图上的失败，证据明确标记 **`failure_simulated=false`**。这与较早 [归档工具实验](bug-recording-20261007.md) 中真实图片加模拟失败输出的 `failure_simulated=true` 案例不同；两者没有混入日常问题库。

本次控制器链路测得 **185.93 ms**，包含实际 OCR、条件解析、Qt 控制器回调与 HTTP 请求序列化。捕获/前台适配和网络响应由验收脚本模拟，不能推导真实截图耗时、鼠标侧键送达、网络延迟、游戏 FPS 或完整现场端到端性能。原有原图回放也只验证读取和路由，不证明排名数值正确。统一报告中的条件问题原图另列为 `reviewed=1`、`passed=1`，不以单元测试总数代替原图核对。

另做了一次有限的真实 API 查询：18.3 版本、赛季 18、单个装备条件暴风之剑 `1001`，在本地时间 **15:43:54** 返回 `SourceError`（请求失败或结构变化），见 `query-proof.json`。随后立即停止，没有重试，也没有请求巨人腰带统计。该结果不是“零样本”，不能声称在线统计或均排正常；请求失败不改变本次离线身份识别和请求序列化的验收范围。

**15:45:43** 已重启本机源码助手，子进程 `71760` 进入 `watching_stage`，`automatic=true`、`bound=true`；MuMu 进程 `61068` 保持不变，最新运行日志为 0 字节，见 `restart.json`。这证明新源码进程已恢复运行，不替代用户在游戏中再开详情按侧键的验收；本轮没有发布新 EXE。

## 条件样本核对规则

`condition` 记录保存完整原图及 `hex`、`equip`、`hero`、`trait` 目录快照。人工或 agent 必须先看图、核对主标题及对应版本目录，再提供绑定该 PNG 哈希的 `expected.json`；失败 observation 不构成正确答案。完整严格格式见 [问题画面归档与核对后复验](bug-recording-20261007.md#核对后建立-expectedjson)。

确认巨人腰带时使用 `scene="condition_detail"`、`kind="equip"`、`cards=[{"slot":0,"id":"1007"}]`。其他支持种类为 `hex` 和 `hero`。明确预期拒绝详情身份时，该场景的 `kind` 与唯一槽位的 `id` 同时为 `null`；明确不应填入详情条件时使用 `scene="unknown"`、`kind=null`、`cards=[]`。歧义结果不作为 resolved，跨种类同 ID 不能通过身份核对。未知断言字段、排名或统计字段均判为 invalid。

待核对、非法、未执行与实际通过分别统计；**pending 不等于通过**。复验读取记录时的目录，不联网、不捕获窗口、不改原图、不进入游戏，也不会自动上传任何样本。只有合法 oracle 进入实际 `ConditionReader`；默认清单不初始化 OCR。

## 可执行命令

在仓库根目录、安装运行依赖的 Python 3.12 环境中执行；开发机可将 `python` 换为 `work\p0-runtime\Scripts\python.exe`。下列 `*-recheck.json` 是重跑报告，避免覆盖本次验收证据。需要本机原图及 OCR 模型的命令只用于显式复验。

只检查隔离样本及 oracle 状态，不运行 OCR：

```powershell
python -X utf8 tools/validate_bug_cases.py --cases-dir work/condition-sword-20261007/verified-cases --report work/condition-sword-20261007/inventory-recheck.json
```

对已核对的真实原图复验：

```powershell
python -X utf8 tools/validate_bug_cases.py --cases-dir work/condition-sword-20261007/verified-cases --run-reviewed --report work/condition-sword-20261007/review-recheck.json
```

重跑原有详情原图回放：

```powershell
python -X utf8 tools/validate_condition_screenshots.py --rounds 1 --report work/condition-sword-20261007/existing-details-recheck.json
```

通过统一入口执行离线检查、原有私人扩展及本次已核对归档：

```powershell
python -X utf8 tools/validate_data.py --include-private --release-gate --bug-cases-dir work/condition-sword-20261007/verified-cases --report work/condition-sword-20261007/full-tests-recheck.json
```

统一报告的 `bug_cases` 单独列出 pending、invalid、reviewed、passed 和 failed。报告目标须在样本目录之外；工具拒绝样本及报告中的链接路径，不能用输出报告覆盖原始证据。海克斯、装备选择及公开排名显示回归沿用既有检查，不因增加条件原图复验而改变。
