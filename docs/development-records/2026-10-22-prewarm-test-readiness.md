# 2026-10-22：预热 UI 测试准备阶段超时

状态：测试修正及本机完整门槛通过；精确提交CI的完整SHA、链接、原报告与最终状态在本机 `remote-final-readiness.json` 及 `ci-readiness/` 留档。v1.0.0 已于 00:13:21 正式发布；包源码为 `e66b0abbdb9531fb643b00aafe870d2eb4ed0bfa`，其 main CI 与实际 EXE 已通过。本轮保留后续 tag/document CI 的真实失败，不将其写成全部绿色。

## 范围与证据

- 起始源码 `deb764318a760ca157f5121973edc7d1211ffdc2`；隔离树 `codex/release-v1.0.0`；main 该提交较 e66 仅文档变化。
- tag CI [39632451397](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/39632451397)：1021 tests、1 failure、0 error/skip/gap，`test_hex_prewarm_ui.HexPrewarmUI.test_new_game_cancels_queued_missing_stages_and_late_publication` 在调用 new_game 之前等待首个 exact HTTP 超时，尚未执行取消断言。
- document CI [39633408224](https://github.com/Robin-hhc/TFT-DataJ/actions/runs/39633408224)：1021 tests、1 failure、0 error/skip/gap，`test_partial_cached_ranks_keep_candidate_slots_and_exact_source_scope` 在 foreground 查询之前等待第三个 exact HTTP 超时，尚未执行槽位/统计断言。该步骤失败导致数据故障注入未运行。
- 原始报告、失败日志、原测试源码与受控时间线保留本机 `work/release-v1.0.0-20261021/ci-*-failed-attempt1*`、`prewarm-test-before.py`、`readiness-red.json/log`。

## 红色复现与修正

用同一 Python 3.12.14 执行本机 `reproduce-prewarm-readiness.py --expect red --report .../readiness-red.json`，只给原 MockTransport 响应分别增加350ms/650ms固定延迟，保持全部生产路径、原数据答案、断言及原5s/3.5s等待不变。两方法均在与CI相同的准备等待处失败，0errors。时间线证明 global、primary 与前序 exact 的完成后1s节奏先被串行经过，目标 HTTP 还未进入就到准备截止；没有重现错误发布、阶段串用或取消失败。此证据说明测试准备开销足以制造相同失败，不声称知道自然CI中每个调度延迟的来源。

Source.request 的测试覆盖只去掉普通请求节奏，后台 _prefetch_request 并不经过它；后台 adapter 完成节奏与 HexPrewarm 自身间隔均仍有效（重叠而非简单累加）。修正仅通过真实 DataJ.hexes/explore 请求、验证及缓存，提前建立这些测试本来要使用的主表和已有排名，再 pin 并进入原受控阻塞请求。partialcached 只预置两项已缓存排名，第三项仍由真实预热HTTP阻塞，foreground仍须共用其在途请求；生命周期只预置两张主表，第一项 exact 仍真实进入并阻塞后才执行原动作。

改动限本测试文件、REG-017 追加保护与本记录/索引/发布记录。未改生产代码、生产请求间隔、HTTP容量、冷却、时间门槛、250ms发布检查、业务断言、原fixture/oracle或已批准原图。三项真正冷启动/900s留存/阶段计划测试保持原样；业务准备与生产节奏的覆盖边界在台账注明。

## 实际检查与交付

后续追加受控绿、旧断言保持审计、相关坏实现拒绝、受影响模块、统一入口、独立审阅及精确 SHA CI。正式 v1.0.0 ZIP 与标签保持原字节和源码身份；只有在证实生产代码相同且新测试覆盖通过后，才保留其发布结论。无需用源码测试冒充新的 EXE、实战、物理输入或FPS验收。

| 检查 | 实际操作 | 结果 |
|---|---|---|
| 受控红→绿 | 同解释器运行 `work/release-v1.0.0-20261021/reproduce-prewarm-readiness.py --expect green --report .../readiness-green.json` | passed，同350/650ms延迟，2方法均0failure/error/skip；保留red原失败/时间线，未提高任何原等待期限 |
| 语义错误拒绝 | 本机 `check-readiness-semantic-faults.py`，正常方法先过，再在内存替换错误缓存均排/无操作new_game | passed，2/2在原业务断言失败（不是就绪断言/导入错误），修改全部恢复、四来源文件前后hash一致；`readiness-semantic-faults.json` |
| 受影响套件 | `python -X utf8 -m unittest test_hex_prewarm_ui test_hex_full_prewarm test_dataj_hex_prefetch test_hex_comp_latency test_source_budget -v`；更正误写模块名后 `python -X utf8 -m unittest test_hex_prewarm -v` | 首次命令43项真实测试通过，额外1个不存在模块的loader错误保留；实际模块14项通过，合计57项实际方法通过；`readiness-affected.log`、`readiness-affected-prewarm-corrected.log`。完整统一入口会重新覆盖全部合法模块 |
| 静态/台账审计 | 比较原测试源码与新AST，仅剔除新增准备helper和4调用；核对REG017与旧116 ledger | passed，23旧方法与断言数保持、3冷/填充方法原样；旧行/引用/46fixture/私图基线不变，新增6精确public方法；新必交122方法，旧ledger不变；`PREWARM-READINESS-AST-REGISTRY-AUDIT.json` |
| 独立审阅 | 两路只读review实际diff、受控红绿、就绪与业务分界 | passed，无实现阻断；`CI-FLAKE-FIX-REVIEW.md`、`CI-FLAKE-FIX-STANDARDS-REVIEW.md`。已发包继续绑定e66，不能重标包源码/测试指纹或覆盖tag/资产 |
| 公共统一入口/数据故障 | `E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref deb764318a760ca157f5121973edc7d1211ffdc2 --report E:/tft-helper/work/release-v1.0.0-20261021/readiness-public.json`；同解释器 `tools/check_data_mutations.py --report E:/tft-helper/work/release-v1.0.0-20261021/readiness-data-mutations.json` | passed，1021 tests/286.353s，0failure/error/skip/source_gap；356展示，28主题/458引用/46fixture；16/16数据错误caught；122/122必交方法实际passed。46原图schema_only/not_run，7私有扩展未运行 |

本轮不改变OCR、截图、生产UI或实际EXE，已有46原图/包验收属于同一不变生产版本e66；本轮公开报告将明确不执行私人扩展/46原图，不冒称重新私图验收。普通请求、后台完成后间隔/并发/冷却及250ms发布门槛由未改测试继续保护。

267来源冻结 `final-source-binding-readiness.json` SHA-256 `6c49113d798193c709eb2b8d1c1a5466515a8da9f09123592bf0a92be0869ce6`，受测为deb+本轮测试/registry diff；`READINESS-LOCAL-GATE-AUDIT.json` 逐方法/注册项/展示/私有未运行范围/16故障及来源不变性审计passed。验证后只补本文等结果文档，运行代码、依赖与资源不变；不重复构建或覆盖已发布资产，不为自含新提交SHA/后续CI结果反复创建文档提交。
