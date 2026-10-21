# 2026-10-12：点击助手外部自动收起

## 目标与范围

- 用户目标：游戏中免去精确点击收起按钮；完成设计、实现及完整开发验证。
- 验收条件：默认开启，真实左键在助手外按下/抬起且无拖动时收起；内部、弹窗、模态操作与标记展开安全；原点击持续转发，不抢前台；状态保留，关闭后无监听残留。
- 设计：[点击外部自动收起](../design/点击外部自动收起-20261012.md)。历史保护追加 REG-006 / REG-022，保留全部旧条目。
- 开工分支 `main`，起始完整 SHA `1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42`；远端 `https://github.com/Robin-hhc/TFT-DataJ.git`。
- 已有未提交改动：AGENTS、README、文档索引、工作流/回归记录、打包说明与 build_windows.py 等。原始 diff / 状态保存在 `work/outside-click-20261012/pre-existing.patch` / `pre-existing-status.txt`，不纳入本轮源码范围。
- 环境：本机 Windows，`work/p0-runtime/Scripts/python.exe` 为 Python 3.12.14，沿用仓库锁定依赖。现有助手/MuMu运行实例保持不动。
- 当前状态：设计、源码实现和最终隔离统一验证完成。物理鼠标/游戏/EXE 未验收，原生 QA 的全程前台恢复失败单列；不把这些项报通过。

## 复现、正确答案与实现

- 新交互功能，原实现只提供显式收起；预期来源为本轮产品合同，不从现有代码输出生成。
- 原生 hook → QueuedConnection → 实际 Companion 的外点测试先运行红阶段；原始日志保留在本轮工作目录。
- 实现：新增 `panel_dismissal.py` 的 Qt 点击事务、popup/modal 生命周期与原生对话框作用域；现有单个 `MouseShortcut` 增加冻结 `panel_event`，事件发生时捕获窗口 root owner/PID，关闭时不查询。面板仅 `invalidate()+hide()`，不请求前台或合成输入；设置独立、默认开启、持久保存。
- 实际先红后绿：原始外点不收起 1 assertion failure（`red.log`）；缺 hook API 9 assertion failures（`hook-red.log`）。首轮集成 31 项中 4 失败（`affected-first.log`），涉及普通单调钟时间戳相同、native POINT 视图寿命。控制器/输入首轮 28 项中 2 失败（`controller-and-hook.log`），包括 QMenu 销毁阻塞残留。
- 独立 Spec 审阅发现并核对：两种时钟混用、popup 销毁残留、隐藏直接最小化仍追踪、过期 up 后需要再次点击。新增最小化与过期释放回归分别先失败（`minimized-red.log`、`expired-release-red.log`），再修正并通过；中间审阅证据在 `review-intermediate.log`。
- 新增 40 个公共方法：`test_panel_dismissal.PanelDismissalTests` 20 项、`test_mouse_panel_notice.MousePanelNoticeTests` 9 项、`test_outside_click_collapse.OutsideClickCollapseTests` 11 项。REG-006 追加 31 个、REG-022 追加 9 个精确 ID。所有旧 ID、范围、fixture 和批准图像保持；本轮未登记私人新样本。
- 全量运行暴露新测试的初始化信号假设：`offline.json` / `isolated-offline.json` 的攻略保持检查要求已当前 `about:blank` 再设置 URL 必须发 `loadFinished`，两轮各 1 failure，其余 882 / 856 方法通过。已改为实际 DOM ready/URL/固定标题读回，仍断言有实际滚动、恢复位置、无额外加载/HTTP，新增展开后同一 DOM 标题保留；独立 Spec 确认保护更强而非放宽结果。定向复验 `guide-document-green.log` 通过。运行源码没有因此修改。

## 实际检查

| 项目 | 命令/范围 | 结果 | 证据与限制 |
|---|---|---|---|
| 开工公共基线 | `work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report work/outside-click-20261012/baseline.json` | passed | 817 tests，0 failure/error/skip；356 显示；25 历史主题；31 私图明确未运行 |
| 功能红阶段 | `work/p0-runtime/Scripts/python.exe -X utf8 -m unittest discover -s outputs/companion -p test_outside_click_collapse.py -v` | failed（已修正） | 外点仍展开的实际 Qt 断言；`red.log`；非缺模块加载错误 |
| 受影响检查 | 在 `outputs/companion`：`../../work/p0-runtime/Scripts/python.exe -X utf8 -m unittest test_outside_click_collapse test_panel_dismissal test_mouse_panel_notice test_mouse_shortcut test_compact_header test_selection_controller test_selection_tracker test_overlay_flicker_sequences test_item_overlay_stability -v` | passed | `affected-reviewed.log`：135 项，12.794s，0 failure/error/skip；之后只加强攻略测试初始化与 DOM 内容核对，最终统一入口覆盖修订版 |
| 中间公共统一入口 | 公共入口分别在工作树 / 第一个隔离 clone，报告 `offline.json` / `isolated-offline.json` | failed（测试已修正，保留原报告） | 883 / 857 项各 1 攻略初始化 failure；均 356 显示通过；不能把这些报告作为最终绿色 |
| 旧测试纯功能检查 | 同入口，报告原定 `feature-only-offline.json` | not_run（中途停止） | `feature-only-offline.log` 是未完成旧测试版本；精确核对自己 venv launcher/child 后仅结束过时验证 child，保留日志；无最终通过声明 |
| 最终公共统一入口 | 在 `work/outside-click-20261012/feature-only-source`：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/validate_data.py --release-gate --regression-base-ref 1ae8f6a6c40cacebebaf0c5b6bbe4afb55be4c42 --report E:/tft-helper/work/outside-click-20261012/feature-only-final.json` | passed | exit0；857 tests，341.642s；0 failure/error/skip；40 新方法均 passed；356 显示、25 历史主题/268 方法引用/25 fixture、0 来源缺口；7 私人扩展及 31 批准图像明确未运行 |
| 相关交互故障注入 | 在仓库根目录：`work/p0-runtime/Scripts/python.exe -X utf8 work/outside-click-20261012/check-panel-mutations.py --snapshot work/outside-click-20261012/review-source-snapshot-v2.json --report work/outside-click-20261012/mutations-panel-final.json` | passed | 最终 6/6 断言捕获、0 error/skip；5 精确方法正常基线先通过；6/6 内存替换还原、六文件前后全部匹配、2.347s；原 v1 报告/日志保留 |
| 数据错误注入 | 在纯功能隔离 clone：`E:/tft-helper/work/p0-runtime/Scripts/python.exe -X utf8 tools/check_data_mutations.py --report E:/tft-helper/work/outside-click-20261012/feature-only-data-mutations.json` | passed | 原有 8/8 数据故障捕获；本轮额外防回归检查，不认领其他任务的新数据保护 |
| Qt/原生窗口与截图 | `work/p0-runtime/Scripts/python.exe -X utf8 work/outside-click-20261012/native_qa.py` | 功能范围 passed；整轮恢复前台 failed | `native-qa.json`：实际 WindowFromPoint/GA_ROOTOWNER/PID、自有 Companion/攻略/标记/popup、独立 child 外部归属、真实 dispatcher/Qt queue，28 功能检查通过，DPI192；1 全程恢复原前台未通过，详见下段 |
| 已批准私图 | 本轮只改鼠标/窗口交互及文件选择外层阻塞，不改帧内容、截图/OCR、统计语义 | not_applicable（未运行） | 公共入口明确列出 31 份基准批准原图和私人扩展未运行；不报私人回放通过 |
| EXE、物理鼠标/侧键、MuMu/FPS、异机 | 未要求发布包，自动通知不等于现场点击 | not_run | 单独报告；不以源码检查推断通过 |

## 审阅与后续复测

- 独立设计/验证路径审阅以及实现后的独立代码审阅均已完成。
- Standards 与 Spec 两轴由不同 agent 独立审阅，报告在 `standards-review.md` / `spec-review.md`，六个文件的第一版冻结哈希逐一一致。两轴均无未解决运行代码问题；Spec 的四项实测发现均保留失败与修正证据。
- 最后只修改攻略保留测试的就绪判据与 DOM 保留断言。独立 Spec 再审通过，测试新 SHA-256 `62f77d84f5587b93298be7247650f5de866a4e0d80aad1a11c031626680127ca`，其余五个冻结文件不变。第一版与第二版索引分别为 `review-source-snapshot.json` / `review-source-snapshot-v2.json`，不覆盖旧证据。
- 主工作树同时有其他开发：数据失败诊断/预热/身份/来源预算等及其测试/台账新增，app.py 也有其他任务的诊断 hunk。整个工作树检查仅是当时快照，不将该任务的更改算作本轮功能；其他测试文件在首轮统一运行期间漂移，所以最终采用固定 SHA 的独立本地 clone。
- `app-feature-only.patch` / `app-scope.json` 明确 8 个本功能 hunk、4 个排除的其他任务 hunk；`feature-only-final-source-snapshot.json` 锁定最终 clone 的 8 文件。隔离 app.py SHA-256 `7b3ac3b63cb787fe35e544181074911eb2f8e8f647373540694b25f2d6396483`；主工作树 app.py 含其他任务诊断，SHA-256 `4ac95df53900b3e9c36973734e1ef0ad9c0680e7215ed31b1b26a2af7281fc6b`。二者本功能 hunk 一致，不能将两个完整文件哈希混为同一测试版本。
- 文档/索引、已采纳架构和设置使用说明同步。`docs-check.json`：113 本地链接均存在；本轮代码 `py_compile`、工作树 `git diff --check` / `git diff --cached --check` 通过。暂存区为空，不混入其他开发。

## 上库与发布状态

- 本轮未要求推送或发布版本；远端 CI / Release 为 not_applicable。
- 未要求上库/发布，此轮保留可检查的工作树源码与文档，没有提交、推送、创建 tag 或改变 Release。当前运行实例保留，没有强制重启；本功能在后续源码启动时读取。

## 结论、限制与交接

- 已满足源码范围的完整外点收起、内部/拖动/popup/modal 排除、旧队列/快点击/过期释放/最小化保护、默认持久设置、状态及攻略保留。最终公共统一入口无未解释失败/跳过，新增 40 个保护都在报告中；相关 6/6 交互坏实现与原有 8/8 数据坏实现均被拒绝。源码自动合同、原生归属和实际现场输入分开报告。
- 全部原始日志、JSON 与界面截图保留本机 `work/outside-click-20261012/`。
- 原生 QA 不能报“全部通过”：首轮本地网页 `setHtml` 被生产 GuidePage 守卫拒绝；第二轮 QA 未正确模拟 main 的 topmost flag，WebEngine 重建 HWND 后命中外部窗；第三轮误将英雄页当设置截图。已修 QA 并保留每轮原始 JSON/图片，最终设置/攻略/标记像素由 root 实际打开检查。最终 28 功能项通过，但整个 QA 前台从原始 HWND198816 变为外部 HWND2034908，Windows 拒绝 SetForegroundWindow 恢复。被动收起这个 seam 的前后台 HWND2034908 相同；不推断整个 QA 的焦点恢复成功。没有继续强制抢回前台，自有 QA/child 窗口全部关闭、child exit0，后续采样只见外部进程窗口。
- 截图最终文件 `native-expanded-attempt5.png`、`native-settings-attempt5.png`、`native-collapsed-marker-attempt5.png`、`native-reopened-attempt5.png`、`native-local-guide-attempt5.png`；哈希在 native QA 报告。全部为隔离测试 UI，无玩家原图。
- 尚未运行：真正安装 hook 后的物理鼠标首点、游戏收到第一次点击、MuMu 窗口/全屏合成、混合 DPI 实体多屏、物理侧键/FPS、便携 EXE 和异机。源码及自有原生窗不能替代这些项；现有发行 ZIP 未更新。
- 最终报告 SHA-256：`feature-only-final.json` = `f161805c73a78d6a3aacb76a6748f241d34f46c52b0309118ebe2ff459ee0a86`；`mutations-panel-final.json` = `e966ef97180b61d570f7956f3bc97419430b9006be6bd9b5c9288c2aaafb3a5d`。隔离八文件前后无漂移；主工作树六个本功能 source/test 文件与 v2 索引匹配。
- 文档结果收口后 `docs-check-final.json` 的 114 个本地链接均存在，本轮已跟踪及新增设计/验收文件的 diff whitespace 检查通过；仅追加文档结果，没有再次修改运行源码。

## 追加修订

- 2026-10-13（Asia/Shanghai）最终收口：本轮跨日完成，文件名保留开工日期 2026-10-12；仅同步设计/架构的收口日期，源码、测试、报告和旧失败证据均不变。
