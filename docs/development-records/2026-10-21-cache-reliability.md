# 2026-10-21：缓存恢复、头像与交付一致性

当前状态：主树1026项、干净交付树986项与两边16类故障注入通过，57项交付方法两边逐项审计通过；准备全新本地候选包。正常路径固定对照达原预算；坏缓存恢复的额外成本未通过原+5/+10ms，用户故障专属取舍仍待答。尚未安装/重启或公开发布。

## 目标与范围

用户批准将反复缓存恢复故障、旧修复漏包与低内存设计一起处理；头像保留，性能预算不能放宽。设计见 [缓存合同](../specs/cache-reliability-memory.md)。

- 主树：main，起点 `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。
- 干净交付起点：`7620751de3849df4e534697b6e6a3dbd924dc6fb`。
- Python：`work/p0-runtime/Scripts/python.exe`，3.12；运行主目录保护不动，原数据库一致备份。
- 380 个开工文件、原 diff/status/hash：`work/cache-reliability-20261021/`。不将未批准的主树变更整批打包。

## 复现、正确答案与实现

此前只读审计已以真实 DataJ + 临时 SQLite 证明多入口坏 HTTP 200 持久化后，即使来源恢复和重新实例化仍失败。原证据保留于 `work/recurring-audit-20261021/`。

本轮头像测量：源码 64 张 96×96 原图，Qt 32bit 解码 2,359,296 字节；统一缩略会改变 18px 像素与高 DPI 图标。本轮拒绝该方案，不宣称普通场景显著降 RAM。

## 实际检查

| 项目 | 命令/依据 | 结果 | 证据与边界 |
|---|---|---|---|
| 开工保护 | `work/p0-runtime/Scripts/python.exe -X utf8 work/cache-reliability-20261021/snapshot.py` | passed | 380 文件，原 SQLite 81,641,472 字节一致备份 |
| 正确性基线绑定 | 前轮 995 报告＋开工运行代码、注册素材 hash 对照 | passed | `perf-agent/baseline-binding.json`，无运行来源漂移；不替代最终门槛 |
| 定向红绿 | cwd `outputs/companion`；`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 -m unittest -v test_validated_cache test_dataj test_display_contracts test_item_stats test_dataj_hex_batch test_dataj_hex_prefetch test_source_budget test_hex_prewarm_recovery test_source_failure_details` | passed | `data-agent/final-affected.log`：89项/45.080s，零失败、错误、跳过；19新方法，目录894行消费者核对通过 |
| 完整私有门槛 | `validate_data.py --include-private --release-gate`，分别绑定开工SHA | root / clean passed | root1026、clean986；两边0失败/错误/跳过、46批准原图；完整命令见末节 |
| 数据故障注入 | `python -u -X utf8 tools/check_data_mutations.py --report work/cache-reliability-20261021/mutations-final.json` | passed | 16/16捕获，最终冻结后再与门槛绑定；额外缓存6类敏感性见`data-agent/contract-evidence.json` |
| 头像真 Qt/截图 | `python -u -X utf8 -m unittest test_portrait_cache`，本机原图三类实际widget在DPR1/2截图 | passed | 原图生产hash与开工相同，4保护方法；根已查看`portrait-agent/portrait-qa-window-dpr-2.png`，普通64张场景内存不下降 |
| 目录兜底Qt | `python -u -X utf8 -m unittest test_startup_versions`；`render_catalog_fallback.py` | passed | 全15方法通过，另将网络失败测试切到生产冷却后单独通过；主activity可见本地目录提示，目录身份不借过期统计 |
| EXE缓存诊断源码 | `python -u -X utf8 -m unittest test_portable_cache_recovery test_portable_query_lifecycle test_portable_recognition_replay test_portrait_cache` | passed | `portrait-agent/portable-cache-final.log`：21项通过。仅`--diagnose`挂入临时SQLite/MockTransport检查；实际EXE待验 |
| 性能固定对照 | 原10场景预算不变，DB热0.5/1ms预算 | normal passed / recovery exception pending | v1/clean热读与基线AA尾差均留档，控制复查通过；最终OCR10场通过；故障恢复原预算仍失败 |
| 干净源码与真 EXE | 旧26＋新31方法 | source passed / EXE pending | 干净源码986与57方法审计通过，真实EXE构建验收待补 |
| 本机更新 | 保留旧目录与设置，通过验收后更新 | not_run | 未动当前运行实例 |
| 游戏FPS/另一台低内存机器 | 未取得新现场证据 | not_run | 不作跨机或FPS结论 |

## 审阅与上库状态

独立审阅见`portrait-agent/independent-review.md`：发现并修正目录行校验过弱的缺口，其余缓存/共享/并发/异步版本边界无阻断。根另审阅便携诊断的临时目录、HTTP次数和最后好值断言。

首轮运行源码冻结：`candidate-source.json`，307个运行/测试/打包来源；相对380个开工文件仅13路径本轮授权变化，无其它漂移。`dataj.py` SHA256 `afc0d8023e9da6d8792f01e4b7238bbb223fe5c7317609504ae70f3bb2ce2924`；`app.py` `ccd81bd3dcee439386167ab32bb0c9418f6fbf30436f04b01b6f687d69514c11`。生产Vision/头像与本轮开工逐字节相同。

新增29个具体方法登记REG-026/027；`perf-agent/required-delivery-methods.json`在最终门槛前冻结55个必须实际通过的方法（旧26＋新29）。目录假响应先红后绿，保留`startup-red-clean.log`两项业务失败/零设置错误及后续复测；早先导入目录、SQLite测试辅助连接未关闭和瞬时status被覆盖等试验日志保留，未算作有效业务复现。

干净提交、版本和 ZIP 验收信息在完成后追加。未授权公开发布或推送远端。

## 结论与追加修订

实施中。保留失败与复测记录，不调整既有性能预算。

### 性能首轮未通过

`perf-agent/database-ab.json`：19组各200对，源码前后未变，18组及全部正常HTTP次数通过；目录热读P50增量0.552ms（上限0.5ms）、P95增量1.460ms（上限1ms），本轮判为未通过。冷取和适配器重建路径过线不抵消热读失败。正式后续负载暂停，原报告保留。

归还串行窗口后，针对同894行校验做等语义循环调整，不缓存“已验证”结论、不降校验：首个nullable tuple短路候选反而更慢，已撤回；展开nullable检查、严格setId快分支及等价ASCII正整数判断另作候选，边界子例涵盖零、前导零、Unicode数字及换行。叶micro不代替正式DB时延结论。v1来源和证据保留，最终v2受测hash/正式结果后补。

v2最终来源为`candidate-source-v2.json`：DataJ SHA256 `2c43d07a051e5c59c6ff382f5f395317c69d28fb2dbd3252b24ba618ff03b8d6`、缓存测试 `6c3fd8a88bf66e2ba1e68f53e4f73c976a7e0d77891f678b1c3c8b8f5bb55b17`；同89方法/45.357秒全过，6/6故障及894目录消费者全过，19方法ID不变。根与独立审阅者确认ASCII整数、严格setId和nullable调整对真实JSON语义等价。没有新增内存缓存/额外请求或跳过命中校验。

### v2常规路径通过，恢复写盘预算未通过

`perf-agent/database-ab-v2.json` 19/19组通过，目录热P50/P95增量0.397/0.551ms，正常HTTP次数不增。`catalog-local-ab.json`：同7200秒旧好目录到真实Qt投影整体P50增量0.421ms/P95 -0.227ms，Qt gap P95 +0.549ms/max -1.081ms，数据相同、明确stale、统计固定为空。

`perf-agent/recovery.json` 10组各200次均成功恢复、重建适配器零HTTP命中，但相对正常cold，P50多6.46–7.41ms，超过固定5ms上限；P95多4.62–9.98ms，未超过10ms。判为失败，不能用正常路径绿色抵消。

保持FULL同步和完整构造/close计时，在临时数据库比较日志模式：`data-agent/sqlite-journals-full.json`、`sqlite-wal-full.json`。TRUNCATE/PERSIST及WAL短连接/临时keep连接都更慢，拒绝所有候选；生产数据库未切换。候选依据核对[SQLite journal_mode文档](https://www.sqlite.org/pragma.html#pragma_journal_mode)及[WAL文档](https://www.sqlite.org/wal.html)，结论以本机数据为准，没有采用OFF/NORMAL降低保障。

据此修订v3业务合同，见设计第3项：网络入口拒绝旧坏行作为miss，正确响应一次原子替换；snapshot/shared保留精确物理删除。每请求拒绝指纹避免重复解码，不是跨请求常驻缓存。独立设计审阅确认安全条件，新增SQLite observer提交数红测、网络并发替换和完整894行坏目录组；旧源/旧测试/失败报告保留，等待实际红绿及完整固定预算复测。

### 后续候选仍未达标，保留真实边界

完整894行目录（863,031字节，最后一条装备name为null）不能由上述十组小坏值代表。work-only15样本中，v2恢复比同payload正常cold多约14ms；v3重复读取/指纹候选约9ms，短生命周期data_version观察连接约6.7ms，均未满足原P50+5ms预算。观察连接仅存在于work试验，未加入生产；原始样本和全部尾部值均保留。

另在work独立目录探测msgspec0.22.0，未安装进开发运行环境：648条实际缓存的递归类型、数值及float.hex一致，28类边界经窄异常回退、2000个固定浮点数通过；863KB解码含对象释放P50仅省约1.61ms。常见应用依赖预载后，首次import仍多约11.53ms、private memory约1.07MiB；work-only原生解析＋观察连接整链warm恢复仍约+5.25ms且有保留的大尾。该方案不能算内存或时延优化，未采纳。证据：`json-probe/probe-report.json`、`import-report.json`及`data-agent/large-bad-native-observer-initial-warm.json`。

已向用户说明小坏记录约+7ms、完整坏目录约+14ms的区别，询问是否允许**仅故障恢复**的额外校验/持久化成本；正常识别、启动、头像预算不变。目前没有收到该边界的确认，不能把原恢复门槛失败写成通过，也不据此安装新版本。

### 正式性能结果与候选选择

独立串行窗口的运行代码固定为v2（DataJ `2c43d07a...`，没有msgspec/观察连接），各报告保留全部样本及源码前后哈希。

| 路径 | 实际结果 | 证据与限制 |
|---|---|---|
| clean正常DB，19组各200对 | 首轮18/19；目录hot P50+0.390ms达标、P95+1.238ms超原1ms | `perf-agent/database-clean-v2.json`，正常HTTP均不增；原失败不删除 |
| 目录热读同源复查 | baseline A/A200通过；同源码A/B200 P50+0.395ms、P95+0.793ms，通过原0.5/1ms | `database-catalog-aa-noise.json`及`database-catalog-ab-investigation.json`；不将首轮改绿 |
| 目录到真实Qt，200对 | P50+0.425ms/P95+1.016ms；5ms心跳P95+0.540ms/max−5.446ms，通过 | `catalog-local-clean-v2.json`，显式拦HTTP且0请求 |
| 原图头像，A/A15、A/B15对 | 首显P50−1.692ms/P95+0.824ms；热显+0.207/−3.947ms；心跳达标 | `portraits-aa.json`、`portraits-ab-clean-v2.json`；64张原图2.25MiB相等、80可见槽位、HTTP0，不宣称内存下降 |
| OCR基线同源A/A25 | 9/10；dim_hug_ii P95+13.885ms超11.674ms，主要为engine+13.527ms | `recognition-aa.json`完整保留；两份字节相同、同帧同13次OCR，没有新路径 |
| 该场预定反序A/A100 | P50+0.062ms/P95−1.734ms，通过；非engine P50+0.014ms | `recognition-aa100-dim-hug.json`；不改模型/ORT/CPU参数、不删样本、不与初轮混合挑绿 |
| OCR正式A/B50，10场 | 全部通过原预算；最大P50增量3.997ms、最大P95增量6.066ms；调用次数逐场相同 | `recognition-ab-clean-v2.json`；结果稳定，运行源码前后一致 |
| 完整坏缓存恢复，11组各200次 | 所有业务恢复成功、每次1HTTP、重建client后0HTTP；原时延门槛11/11未通过 | `recovery-clean-v2-11.json`；小坏P50+6.685～7.309ms，完整894行坏目录P50+13.561/P95+15.075ms；等待用户故障专属取舍 |

root决定把v2准备为可审阅的**待确认候选**，继续可逆的功能验证及本地构建；这不等于用户已接受故障恢复开销，也不授权越过该待答问题安装/重启。运行实例保持原状。原19缓存方法及断言恢复原样，另保留两个适用于v2的业务方法（普通网络并发good替换0HTTP、坏JSON失败冷却/重启恢复）；v3一次提交试验和22方法源码永存work，该内部合同从未注册，未以删除已注册保护来消除失败。

最终候选定向复验：`data-agent/v2-candidate-affected-91.log` 91项/45.457秒、`v2-candidate-portable-3.log` 3项/0.114秒全通过；`contract-evidence-v2-candidate.json` 6/6相关故障拒绝、894目录行到268 canonical实体/540头像查找通过，无wrapper参数TypeError冒充。DataJ仍为`2c43d07a051e5c59c6ff382f5f395317c69d28fb2dbd3252b24ba618ff03b8d6`；21方法测试文件为`16102ef30d12239c4f92341994822897029617a95e114a1985528d8baade0e7a`。

`candidate-source-final-v2.json`冻结最终307运行/测试/打包来源，相对开工仅13授权路径变化，Vision/头像生产原字节不变。新注册31方法（REG-026为27，REG-027为4）；`perf-agent/required-delivery-methods-final57.json`冻结旧26＋新31，共57项，原55清单永久保留。主树完整私有门槛已按开工SHA `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`开始，报告路径`root-with-private-final.json`，不以定向结果代替最终报告。

### 主树最终门槛

命令：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report work/cache-reliability-20261021/root-with-private-final.json`，退出0：1026项/310.890秒，失败0、错误0、跳过0、source_gaps=[]；27历史主题/433方法引用/46素材均通过，46批准原图全部验证，另15份无oracle素材继续pending，未计入通过。

随后`tools/check_data_mutations.py --report work/cache-reliability-20261021/mutations-root-final-v2.json`退出0，16/16被相关业务断言拒绝。`perf-agent/audit_gate.py --validation .../root-with-private-final.json --mutations .../mutations-root-final-v2.json --requirements .../perf-agent/required-delivery-methods-final57.json --report .../root-final57-audit.json`通过：57/57实际passed、0缺失、0未注册。报告绑定开工SHA＋最终受测diff/冻结运行文件，不把dirty主树写成干净提交。

完整stderr里的CLI usage/error文本来自有意拒绝覆盖批准baseline等负向测试，最终unittest/JSON均为0错误。单次PowerShell摘要曾对整数0使用`.Count`而误显示1；立即按原始标量重读纠正，原始报告、测试结果与审计未改动。

### 干净交付树最终门槛

cwd为`C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper`，解释器仍为绝对路径`E:/tft-helper/work/p0-runtime/Scripts/python.exe`：

```powershell
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 7620751de3849df4e534697b6e6a3dbd924dc6fb --bug-cases-dir E:/tft-helper/work/companion/bug-cases --report E:/tft-helper/work/cache-reliability-20261021/perf-agent/clean-final-with-private.json
& E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/check_data_mutations.py --report E:/tft-helper/work/cache-reliability-20261021/perf-agent/mutations-clean-final-v2.json
```

两命令退出0：986项、失败0/错误0/跳过0、source_gaps=[]；27主题/393方法引用/46素材通过，批准46/46原图回放通过、15pending不计通过。16/16故障被捕获；`clean-final57-gate-audit.json`证明57/57具体方法实际passed且已注册。root比clean多出的40项属于开工已有的外点收起范围，本轮保留主树但未混入交付包。

`clean-gate-source-after.json`核对373个非ignored来源前后无漂移；`final-production-performance-binding.json`确认最终运行代码与正式性能来源0差异，仅增加两业务测试的一文件改变。`private-materials-readiness.json`验证批准46份的frame/case/expected共138文件及其它39旧私有素材全部匹配原hash；未省略私有回放或生成oracle。主树`root-runtime-and-lock-post-gate.json`确认307运行来源未变，全部运行/构建依赖精确匹配锁定版本，msgspec未安装。

下一步从干净提交构建未使用v0.2.18。旧`work/package-build`将经绝对路径/运行依赖核验后在同workspace内可逆归档，从空目录运行真正PyInstaller，避免copy2保留旧mtime而复用旧Analysis/PYZ；不使用skip-build，不覆盖旧ZIP/安装或模型。该候选构建不代表已接受故障恢复预算例外，也不更新当前实例。
