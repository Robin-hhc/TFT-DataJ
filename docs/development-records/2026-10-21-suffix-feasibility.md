# 2026-10-21：后缀海克斯的前缀、品质与阶段识别可行性

## 目标与范围

- 用户要求：统计当前所有后缀海克斯，验证准确中文前缀、品质颜色和出现阶段能否替代易错后缀。
- 可检查条件：全量家族与 ID 清单；纯罗马和加号分开；唯一性可重算；阶段有来源边界；原图品质信号实际检查；公开摘要不包含私人原图。
- 本轮产物：[调查报告](../research/suffix-identity-feasibility-20261021.md)、[100 条成员 CSV](../research/suffix-identity-catalog-20261021.csv)、本记录及记录索引一行。实验脚本、原始响应、截图裁图及 JSON 留在 `work/suffix-feasibility-20261021/`。
- 不修改生产代码、批准 oracle、回归登记、运行实例、启动器或发行包。相关历史范围 REG-019、REG-024、REG-025；本轮不增加修复完成声明或测试登记。
- 起始仓库 `E:\tft-helper`，分支 `main`，SHA `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`，远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。
- 根工作树已有多轮未提交改动。开始时保存 `initial-status.txt` 及 510 份源码、文档、原图、病例和预期文件的 SHA-256；记录索引允许追加本轮一行，其他原有文件按快照检查。
- 环境 Windows / PowerShell，实验解释器 `work/p0-runtime/Scripts/python.exe`，Python 3.12；原图为既有 MuMu 16:9 截图，本轮未启动游戏。

## 正确答案与检查方式

- 当前 DataJ 原始目录由阶段代理单次直接 GET，HTTP 200，268 行。源目录没有写入运行缓存。与只读缓存、10-18 原始响应及最新病例冻结目录对照，全部 100 条家族成员逐字段一致。
- 当前响应时间 `2026-10-21T00:37:40+08:00`，原始响应 SHA-256 `bd30489cdb796bf869cb3b5c59cf73895539a5abbae2dd7750b88776b0860ebe`。公开报告仅转录必要目录字段；完整响应留本机。
- 48 家族包含 72 条显式后缀和 28 条无后缀成员。19 纯罗马 /34 条、28 纯加号 /62 条、1 混合 /4 条。纯罗马 19 家族的前缀＋品质全部唯一，其中 13 个多成员、6 个单成员。
- 根代理独立重算 34 个纯罗马成员，使用目录真实品质和准确前缀；34/34 唯一回到来源 ID，另 11 个边界检查通过。这是信息充分性实验，不证明自动 OCR、颜色分类或生产补全通过。
- 27 个同品质多候选家族中：18.4 统计正向阶段分离 21、部分缺失 3、全缺 3。没有用缺失记录排除任何 ID。100 条描述全核查，含阶段/回合等效果时间的 32 条均不能构成完整生成阶段约束。
- 官方旧 16.1 的阶段规则、18.3 原图/历史统计与当前 18.4 快照分别留档，不跨版本导出当前硬规则；电火花 I、日月同辉原图与同版本统计缺项说明统计非完整出现白名单。
- 原图颜色、阶段检查结果与分母见报告及 `color-agent/`，均不计作自动分类准确率。

## 实际检查

| 项目 | 完整命令或实际操作 | 范围与结果 | 证据与限制 |
|---|---|---|---|
| 目录库存 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/catalog-agent/audit_suffix_catalog.py --live-api-file work/suffix-feasibility-20261021/stage-agent/current-gamedata-response.json`；`& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/catalog-agent/augment_suffix_types.py` | passed：四源 100 条成员一致，48 家族分类完整 | `catalog-agent/catalog-family-audit.json`、`all-family-table.json`；补充哈希/48 行汇总后再运行分型脚本一次；不等于全部条目游戏中当前必定有效 |
| 信息充分性实验 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/audit_lookup.py` | passed：34 个纯罗马成员、11 边界；46 批准图中 43 个家族槽位的条件分析 | `lookup-upper-bound.json`；正确前缀、品质为假设输入，未冒充 OCR |
| 阶段证据 | 原始 gamedata GET 一次；SQLite URI `mode=ro`；全 27 组逐候选统计与原图核对 | passed：21/3/3 的证据分层；当前全量生成规则 unknown | `stage-agent/stage-evidence.json`、`stage-evidence.md`、请求元数据和缓存快照 |
| 当前回合 OCR 原图实验 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/check_round_reader.py` | passed：45 份有选择阶段 oracle 的原图 45/45，0 失败；1 份 unknown/无回合 oracle 单列，不计通过 | `round-reader.json`；`vision.py` SHA-256 `b4f41fe0ac76481fdb500e3ddb026cf8609184b063ac602fff88e9f81aa32cad`；只验证固定回合裁图 OCR，不是整条识别回归或新颜色算法 |
| 私人原图信号检查 | 原图代理按批准 baseline 校验 46 份原图 SHA，生成只含原像素的图标/阶段联系图并查看重点图片；根代理查看全部 5 页和重点完整原图，固定人工颜色标签后运行 `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/check_manual_colors.py` | 138 个固定位置人工标色：银 50、金 56、彩 22、无有用图标 10；105 个已批准 ID 位置与目录品质 105 相符/0 不符，其他 33 个位置不计颜色正确；2 位置部分遮挡 | `root-manual-colors.json`、`color-agent/`；人工可辨不等于自动分类，动画和遮挡仍需场景/稳定性/品质置信度门槛 |
| 公开摘要 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/build_note.py`，其后补充颜色、回合实际核查段及跨版本边界说明 | 48 家族 Markdown、100 条 CSV | 本次生成的是报告，不生成/改写测试的 accepted answers |
| 独立审阅 | 库存代理复核报告、CSV 与独立 lookup 分母；最终增量再核人工颜色和当前回合 OCR | passed：首轮 12 项，最终增量 11 项；`review.json`、`review-final.json` | 最终审阅绑定报告 SHA-256 `e3603b01db88fd3d91beef88c5cb69d8d283854c2827593e0996168670245ff9`；不以自检替代目录的独立来源核验 |
| 文档/原文件保护 | `& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/check_documentation.py`；`& work/p0-runtime/Scripts/python.exe -X utf8 work/suffix-feasibility-20261021/protect_scope.py check`；本轮 diff/check | 结果见本机 `documentation-check.json`、`protected-check.json` | 只审阅本轮新增文档及记录索引单行；其他脏改动保留 |
| 公共/私有统一运行回归、故障注入、Qt、性能、EXE 与现场 | not_applicable / not_run：本轮只调查、产出说明与独立数据实验，未修改运行代码 | 不引用上轮运行结果作为本轮验收 | 自动品质分类、生产识别回归、真实游戏连续帧/FPS、打包、异机均未由本轮证明 |

## 审阅与交付状态

- 原始目录、规则与阶段核查由库存、阶段两名代理分别执行；根代理独立家族重算；原图品质信号由原图审核代理实际查看。
- 文档检查实际通过：35 个本地链接、48 行家族表、100 行 CSV，字段与来源一致；记录索引与暂存区 whitespace 检查退出码均为 0。原有 510 个受保护文件检查通过，0 改变、0 新生产源码；人工标色与回合 OCR 的实验结果已分别留存，原有批准文件未改写。
- 报告建议先对 19 个纯罗马家族采用前缀＋品质交叉确认，再对已独立核准的加号家族加入版本化阶段规则。方案可行性已证实的范围与尚待工程验收的范围分开。
- 本轮没有 Git 提交/推送、CI、tag、Release、ZIP 或本机应用更新。用户本条请求为可行性核对，这些交付项不在本轮声明中。
- 公开文档未发布私人原图；本机完整证据位于 `work/suffix-feasibility-20261021/`。后续源码实现需按统一流程补实际失败回归、品质/阶段负例及完整运行验证，不能拿本报告的条件查询结果代替。
