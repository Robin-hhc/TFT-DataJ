# 2026-10-21：缓存恢复、头像与交付一致性

当前状态：已安装v0.2.19并更新桌面EXE入口，源码版正常退出后重启，新GUI实际选中18.4且恢复收起。用户已明确接受仅坏缓存恢复的额外几毫秒；有限重试及17新回归完成，主树1043/交付树1003项、两边16类故障注入与74方法逐项审计通过，46批准原图复验通过。新EXE离线/联网/9原图/后台持续故障封顶诊断通过；正常帧时延A/A及A/B达原预算。旧v0.2.17安装与v0.2.18候选保留；未推送或公开发布，不宣称实战FPS/物理侧键/异机重新验收。

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

当时试验v3业务合同（最终未采纳）：网络入口拒绝旧坏行作为miss，正确响应一次原子替换；snapshot/shared保留精确物理删除。每请求拒绝指纹避免重复解码，不是跨请求常驻缓存。独立设计审阅确认安全条件，新增SQLite observer提交数红测、网络并发替换和完整894行坏目录组；旧源/旧测试/失败报告保留。最终选择及原预算未通过情况见后文，不把这一试验描述当作当前生产实现。

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

干净范围已提交为`e101e70ec54ef25c88059048373dde44bd881823`（本地分支`codex/roman-suffix-20261020`，未推送）；31个文件，独立审阅通过的暂存补丁SHA256为`1314cf5d15bae06bef35215db5604f501068f89ce58786fde39913d6813ce8f8`。提交后工作树无改动，先前主树未授权变化继续留在主树。

### 全新候选包及EXE验收

旧`work/package-build`经绝对路径、无reparse及无进程依赖核验后，可逆移至同交付workspace的`work/pb17-20261021`，旧v0.2.17 manifest SHA256 `7cf8786eb410908b33260b90b4893904055c5a434f9c81b68e8af22c5febabb0`保持不变。证据：`build-work-archive-preflight.json`、`build-work-archive-result.json`。从空目录运行真正PyInstaller，不使用skip-build、不复用旧Analysis/PYZ、不覆盖旧ZIP/安装或模型。

构建命令（cwd为上述干净交付树）：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 packaging/build_windows.py --version 0.2.18`，退出0。新ZIP 281,185,363字节，SHA256 `eef3aab16167a7400c3492e05d08906f62bb45dcbefb6dbe69ab908b81ef54be`；3023个manifest文件逐一核对。`build-v0.2.18.log`保留完整构建输出，`package-offline-v0.2.18.json`单独保留实际EXE离线验收：退出0、status=passed、frozen=true；缓存修复2HTTP、fresh-adapter命中、坏刷新拒绝、最后好目录保留、snapshot 0HTTP均通过。此为本机隔离路径和环境验证，不是另一台物理机器。

联网与9张批准原图命令：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 packaging/verify_windows.py C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper/dist/TFT-DataJ-0.2.18-windows-x64.zip --online --recognition-fixture E:/tft-helper/work/suffix-recognition-20261021/package-agent/exe-recognition-v0.2.17.json`，退出0、status=passed。真实DataJ HTTPS与英雄头像读取通过；9张既有批准原图及独立oracle hash均匹配，9/9通过，三个slot均resolved、mismatches=[]。目录hash `37f4d7f4559c9c189353ecb315d14887699c7acdd14fa6d5fe1351f456a5f925`。完整日志`package-online-v0.2.18.log`，原始在线报告`package-online-v0.2.18.json`的SHA256为`5b32179f80f5f553035b5149b87c20d7e3a468f55ad49bfa57b574d79716c499`。

ZIP、checksum和在线报告复制到主树`dist/`同名路径，目标预先确认不存在，复制前后流式hash相同，未覆盖v0.2.17或任何旧产物。`candidate-package-final.json`记录全部路径/大小/hash及离线缓存合同。候选manifest为干净提交e101e70、working_changes=false；manifest hash `752a3acde1e81572d00bc943d62969a38a7f9257c7fb36758a64c502a2688d4e`。

只读安装预检命令：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 work/cache-reliability-20261021/delivery-agent/install_validated_package.py E:/tft-helper/dist/TFT-DataJ-0.2.18-windows-x64.zip E:/tft-helper/dist/TFT-DataJ-0.2.18-windows-x64.validation.json --source-root C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper --expected-commit e101e70ec54ef25c88059048373dde44bd881823`，退出0。3023成员及192打包来源hash、干净HEAD、9原图/oracle/目录、真实HTTPS头像、EXE缓存修复证据与旧安装/桌面身份全部匹配；mode=preflight、shortcut_updated=false、old_version_retained=true。原审计`delivery-agent/local-install-20261021-130546-596035.json`，日志`installation-preflight-v0.2.18.log`。未使用`--execute`。

`final-active-state-unchanged.json`在预检后只读核对源GUI PID206544/launcher202668及原创建时间、命令和路径，input.ini、CMD、EXE快捷方式hash均未改变，v0.2.18安装目录仍不存在。源307个冻结文件hash继续匹配。一次辅助摘要使用了错误字段`cmd_sha256`而KeyError；按实际schema改读`source_cmd_sha256`后上述检查通过，失败的辅助查询没有修改运行实例或设置。

该候选构建不代表已接受故障恢复预算例外，也不更新当前实例。桌面CMD、EXE快捷方式、源实例和旧安装均保持原状；任何最终安装/重启仍受上文待答边界约束。本轮没有证据证明常规RAM显著下降，也未采纳另一个DB、缩略头像或原生解析依赖。未推送，因此没有该提交的远端CI或公开release证据；本机源码、隔离EXE、硬件/游戏FPS与跨机结果分别记录，不能互相替代。

### 16:30后：用户接受故障成本，并复核持续来源异常

用户明确答复“增加几毫秒就加吧”，撤销上文故障恢复成本待答状态；正常路径原性能要求不变。随后追问持续网站异常是否一直重试、是否有阈值。只读复核发现两处需要修正，尚未将v0.2.18安装到本机：

- 固定阵容HexPrewarm原来只有限速：唯一Timer、至少60秒及共享冷却；缺少累计轮数上限。
- 同画面全局统计完全失败会清空stats_payload，普通accept_frame兜底因而约每2秒重新OCR和查询。HTTP/JSON包络错误受60秒共享冷却；业务字段无效则仅有原1秒成功请求间隔。真实DataJ+Qt红测6次同帧导致7次HTTP，证明不是仅检查内部计数。

本轮开始前保存`before-retry-limits/`四文件原字节/hash，原e101e70/v0.2.18包、全部旧测试和失败报告继续保留。追加合同已写设计第5项；同对象总3轮SourceError（含首次），前两轮至少60秒重试，第三轮停止自动恢复，成功或缓存命中不重置总失败计数，已成功表/精确值/待办保留。普通start/prioritize与晚到Timer不能解锁；新任务有独立预算但仍尊重共享来源冷却。这里是“三轮失败”，不是保证每轮恰好一次HTTP。

同候选组全局失败保留失败token，普通同帧不重复OCR/查询；已确认三卡时侧键/「立即补查一次」直接复用身份补查、不再OCR。换牌检测与既有两次partial补读保留，真正换阶段/版本/新局能继续；过时组或旧adapter的失败回调不能清掉当前结果。失败状态不伪装成成功统计。

定向红绿与敏感性：`retry-cap/RETRY-CAP-RESULTS.md`记录旧恢复8方法/原helpers逐字和AST不变，首红第三次失败仍产生第三个Timer（3 != 2），新4方法及受影响61项/76.498s全过，去掉上限、成功即清零两故障均被业务断言捕获（0error/skip）。`global-retry/RESULTS.md`记录真实red及11新方法、82受影响项/9.011s全过，3/3故障捕获；partial实际请求链路保留初次+两次后停止，普通画面捕获仍继续。

为真EXE加入仅诊断模式的`check_retry_limits()`：临时SQLite、MockTransport、受控时钟/延迟回调分别测持续503和坏HTTP200，均3HTTP/2Timer后停止；晚到回调及start/prioritize不产生新HTTP。`test_portable_retry_limits`先红（诊断缺失）、后绿；将运行上限错误改4的故障被明确“continued scheduling after three failures”断言拒绝。与旧缓存诊断共5方法/0.163s通过。该嵌入诊断不接触活动数据库，也不真实等待两分钟，不算现场网站故障。

REG-028登记共17新公共方法（4后台、11同画面、2EXE诊断）；`retry-cap/final-17-methods.json`逐项列出，`perf-agent/required-delivery-methods-final74.json`在最终门槛前冻结旧57+新17。当前仅定向检查通过；下面追加最终统一门槛、新包与本机更新的实际结果，不能沿用1026/986或v0.2.18验收当作新增保护已交付。

追加独立审阅：后台/EXE诊断经另一实现者及独立Standards审阅，无阻断；全局失败token/app与EXE诊断由后台实现者独立审阅，无阻断，见`retry-cap/APP-PORTABLE-REVIEW.md`。其边界明确：嵌入EXE的新retry_limits只实际执行后台封顶分支；全局失败同帧分支由11个源码Qt方法及最终包精确来源绑定证明，不称作在frozenEXE完整执行了那11个分支。

正常帧时延：`retry-cap/profile_accept_frame.py --help`后先2对/1warm验证隔离，再按冻结500对/20warm、交错顺序串行A/A、A/B。`accept-frame-normal.json`（SHA256 `31612e7babd579d7f948fc2cc47d420776769a131d99ead11d6c49c55c9736d2`）四场均过原P50+5ms/P95+max(5%,10ms)：A/B自动P50+0.000500ms/P95+0.012255ms；手动P50−0.000400ms/P95−0.020425ms；A/A通过。真实Qt排队回调及accept_frame状态/文本生成，每帧相同3文本，OCR/query_stats/HTTP=0，源前后hash相同；不包含截图、OCR、像素准备、原生浮层定位、实战FPS或完整冷启动。没有通过减少调用或降低刷新换绿色。

`candidate-source-final-retry-limits.json`冻结309运行/测试/打包文件，相对v2只有app/hex_prewarm/恢复测试/portable_check四个既有来源改变，另加两测试模块；DataJ、Vision、头像生产仍是原字节。旧fixtures及所有旧回归条目保持。`retry-integration/scoped-retry.patch`仅将本轮增量应用到干净e101e70，保留隔离外点收起范围；根与干净树的accept_frame/query_stats AST一致，`retry-integration/performance-binding.json`单独绑定本次正常帧性能与干净交付。

### 有界重试：最终主树门槛

命令：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report E:/tft-helper/work/cache-reliability-20261021/retry-final-validation/root-with-private.json`，退出0；1043项/331.655秒，失败0、错误0、跳过0、source_gaps=[]；46批准原图实际回放和46/46原始frame/case/oracle校验通过，15未审核原样pending、未算通过。

随后`tools/check_data_mutations.py --report E:/tft-helper/work/cache-reliability-20261021/retry-final-validation/mutations-root.json`退出0，16/16捕获；`perf-agent/audit_gate.py --validation .../retry-final-validation/root-with-private.json --mutations .../retry-final-validation/mutations-root.json --requirements .../perf-agent/required-delivery-methods-final74.json --report .../retry-final-validation/root-74-audit.json`退出0，74/74具体方法实际passed、0缺失、0未注册。`root-source-unchanged.json`证明309冻结文件检查后无变化。

干净交付树正在按原7620751开工SHA、独立工作树diff及同74方法、原46素材执行最终门槛。v0.2.18构建目录已在运行依赖/reparse/绝对目标检查后可逆移动到同workspace的`work/pb18-20261021`，原manifest `752a3acde1e81572d00bc943d62969a38a7f9257c7fb36758a64c502a2688d4e`保持一致，见`retry-final-validation/build-v18-archive.json`。下一新包使用未占用v0.2.19，不覆盖v0.2.18候选或v0.2.17安装。

### 有界重试：最终交付树门槛

cwd为隔离交付树，解释器仍为绝对路径Python3.12：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref 7620751de3849df4e534697b6e6a3dbd924dc6fb --bug-cases-dir E:/tft-helper/work/companion/bug-cases --report E:/tft-helper/work/cache-reliability-20261021/retry-final-validation/clean-with-private.json`，退出0；1003项、0失败/错误/跳过、source_gaps=[]，28历史主题/410方法引用/46素材均通过，46批准原图均校验/回放通过，15pending不计通过。

随后相同解释器执行`tools/check_data_mutations.py --report E:/tft-helper/work/cache-reliability-20261021/retry-final-validation/mutations-clean.json`与`perf-agent/audit_gate.py --root C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper --validation .../retry-final-validation/clean-with-private.json --mutations .../retry-final-validation/mutations-clean.json --requirements .../perf-agent/required-delivery-methods-final74.json --report .../retry-final-validation/clean-74-audit.json`，均退出0，16/16故障捕获、74/74方法通过，0缺失/未注册。两边测试后未再改运行代码/依赖/资源。

本机交付脚本按v0.2.19单独保留于`delivery-v0.2.19/`，不会覆盖原v0.2.18预检证据；安装器增加实际EXE retry_limits字段、持续503/坏200各3HTTP/2wake/min60s的强校验。独立只读审阅发现正常shutdown保存panel_geometry/mark_position可能令旧脚本在退出后中止：现改为备份退出前和正常保存后的文件，仅允许这两个合法窗口位置字段变化，后续使用退出后设置，不回写旧值。3个专门核对及3脚本compile通过，日志`settings-validation.log`；该修正仅在work交付脚本，不进入产品或影响已过源码门槛。

### v0.2.19包与本机更新完成

最终产品源码提交`9cc6fef243152895867c2a84e10a010cd0bfd36f`（9个范围文件，657插入/8删除），暂存补丁SHA256 `1fc04499e6dbcf9e3d8839c7419b25b401b9d6a99aac7a499689bbdbef1420c5`。提交前175个交付Python来源与全套后审计hash完全一致；提交后工作树干净。仅本地提交，未推送/tag/公开Release。

在空work/package-build从头执行`E:/tft-helper/work/p0-runtime/Scripts/python.exe -u -X utf8 packaging/build_windows.py --version 0.2.19`，退出0。新`dist/TFT-DataJ-0.2.19-windows-x64.zip`为281,188,988字节，SHA256 `52fd69e26fdc5dbc1cd56deafe0e6a7a9064c48db9ce8734a0d888c429c80cc0`；manifest源码为9cc6fef、working_changes=false，3023个文件和194来源指纹逐项核对，manifest SHA256 `976f6e0ba6eba2e593b4762e0dd752aee9fa0516d3971771ebfaba24f51985f7`。完整日志`retry-final-validation/build-v0.2.19.log`，离线原报告另存`package-offline-v0.2.19.json`。

随后同解释器运行`packaging/verify_windows.py C:/Users/Robin/.codex/worktrees/recognition-fix-20261018/tft-helper/dist/TFT-DataJ-0.2.19-windows-x64.zip --online --recognition-fixture E:/tft-helper/work/suffix-recognition-20261021/package-agent/exe-recognition-v0.2.17.json`，退出0、report.status=passed；真实HTTPS英雄头像及9张批准原图回放通过，原图/目录/独立oracle hash不变，三个slot逐项resolved且无mismatch。实际EXE的retry_limits分别在持续503和业务无效200下3请求/2延迟wake后停止，min60秒、过期回调与重复start无新增请求；cache_recovery全部合同也通过。联网原报告`package-online-v0.2.19.json` SHA256 `dbc89b38fb1085e24e98d16228f8f319060cc10b64d6dc135fe21a7e07adfce3`。ZIP/checksum/在线报告复制到主树dist不存在的同名路径，源与目标hash相同，不覆盖旧版本。

本机安装：`delivery-v0.2.19/install_validated_package.py`按README完整参数先preflight、再`--execute --update-shortcut`，两次退出0。新目录`%LOCALAPPDATA%/Programs/TFT-DataJ/v0.2.19/TFT-DataJ`全部3023文件核对通过，旧v0.2.17 EXE hash `5d98a088962c5cad1ddcd338441669ada0e68745d47c2fc9da47e574d49390bb`未改变。桌面TFT-DataJ.lnk目标/图标/描述均为v0.2.19，参数保留，link SHA256 `b1123bc9a0df796763018190020899dc074d29a0ef6df040ccd21978c4a33855`；源码CMD仍指向E:/tft-helper且字节hash `63ceb22957232c7ab934ac0cf15f0a870b68bef67fe227a39fbf36745ae5f374`未变。原快捷方式备份在交付work目录，原始执行日志`installation-execute-v0.2.19.log`保留。

源码更新：`delivery-v0.2.19/restart_source.py --source-fingerprint E:/tft-helper/work/cache-reliability-20261021/candidate-source-final-retry-limits.json --expected-patch 18.4`先只读preflight，再`--execute`。原GUI206544/launcher202668经creation/exe/argv确认后，仅向其拥有的Qt线程投递原app.quit的WM_HOTKEY/id53，正常退出，未强杀。窗口浮标位置由Qt正常保存，只有General/mark_position值变化；退出前及正常保存后均备份，不覆盖新位置，其余偏好值未变。启动及后续验收的input.ini SHA256固定为`0d56a0ab19d6205411c016a5771247a11a5ecadadd0a0853708770fcbc495880`。

新launcher193684/GUI207648（创建于2026-10-21T09:01:33.1915920Z），同root/source命令和--start-collapsed；PID绑定ready与所有owned窗口WM_NULL响应通过，309源码冻结hash仍匹配。初次隐藏UIA没有版本控件，脚本明确退出1并留存`source-restart-incomplete-20261021-170142-678158.json`，没有再次退出/重启。随后只对新GUI线程使用已有WM_HOTKEY/id51短暂展开，实际同PID的ComboBox selected value为18.4，与先前独立保存的当前网页首个set18 gameVersions条目一致，再收起。`source-restart-final-ui.json`与`local-delivery-final.json`最终通过；后者再次核对3023安装文件、旧EXE保留、快捷方式、设置、309来源及16个owned窗口响应。初始未完成记录保留，未以缓存query key或构造器默认版本冒充UI验证。

收口：本轮已完成授权的本机修复、回归、打包和两个入口更新。没有新增数据库/解析依赖或缩略头像，没有证实常规RAM明显减少；正常路径原预算保持，原故障恢复5/10ms失败报告与用户接受成本的决定均保留。未重新开展实战FPS、MuMu合成、物理侧键或另一台电脑验证；这些边界不由源码与隔离EXE结果替代。
