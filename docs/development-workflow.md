# 统一开发、验证与交付流程

这是本项目每轮开发的执行入口，由根目录 [AGENTS.md](../AGENTS.md) 引用。适用于功能、修复、重构、文档及发布任务；步骤按改动范围选择，执行结果按轮次留档。用户已确认的范围与授权持续有效，不重复请求确认。

## 1. 开始一轮任务

1. 阅读本流程、与任务相关的设计；涉及故障时再读 [回归积累机制](testing/regression-accumulation.md) 和 [历史问题索引](testing/regressions.json)。有已采纳的架构决定时，保持设计文档与实现一致。
2. 确认真实仓库、分支、起始提交、远端和未提交改动。目录搬迁后重新检查，不能沿用旧路径。以下命令在仓库根目录执行：

   ```powershell
   git rev-parse --show-toplevel
   git branch --show-current
   git rev-parse HEAD
   git remote -v
   git status --short
   ```

3. 保存开工 SHA：`$taskBase = git rev-parse HEAD`，本轮后续复用，不在实现后重新赋值。写下目标、验收条件、改动范围和不确定项。复杂的新交互需要用户讨论时，先给可审阅的设计；已经批准的方案直接执行。实现者负责开发、验证、归档和交付，不能把基础验证转交用户。
4. 从 [验收模板](development-records/template.md) 建立 `docs/development-records/YYYY-MM-DD-主题.md`。命令输出与 JSON 放在 `work/<本轮唯一名称>/`，与原始样本目录分开。继续同一轮时补充记录，不重写过去的结果。

保护其他人的改动、运行实例、OCR 模型、真实素材及已批准基线。不要用 `git reset --hard`、`git clean`、强推或批量结束进程来“恢复环境”。本轮无法隔离验证时，记录阻碍并继续能独立完成的工作；构建发布包应另用目标提交的干净目录。

## 2. 实现与问题积累

1. 故障先定位并复现用户实际遇到的行为，独立核对正确答案，再写能对该故障失败的回归。先记录失败，再修复，再记录通过。已有修复尚缺回归时，通过受控错误注入证明测试确实拒绝错误，明确说明没有原始失败运行。
2. 实现后先跑受影响测试。数据请求、实体 ID、阶段、版本、全局/阵容范围、排序、样本门槛、缓存及实际显示，需要按真实链路核对；仅测格式化函数或模拟返回值不足以证明显示正确。
3. 更新历史索引的具体测试方法、公开/私有范围及独立证据。真实问题画面先归档，再核对，再登记批准；识别观察值不能直接生成预期结果。`pending_review` 不算通过。
4. 改动设计、接口、启动方式或发布流程时，同步对应文档。新检查接入现有统一入口，不另留一套不会被后续 agent 执行的手工流程。

具体样本登记、哈希保护、测试替换和基线比较按 [回归积累机制](testing/regression-accumulation.md) 执行。不能通过删除旧测试、跳过批准样本、放宽断言或用新实现重算答案来消除失败。

## 3. 按改动选择验证

本表是必选项，叠加选择；例如识别结果还影响排名，则同时执行识别和数据两行。记录每项实际结果和未覆盖范围，不能用测试数量代替覆盖证明。

| 改动 | 本轮至少验证 | 可证明的范围及必要限制 |
|---|---|---|
| 纯文档、说明、链接 | 校对命令与实际脚本参数、检查链接、审阅本轮 diff | 无需新增照抄实现的 UT；没有运行代码时不能声明功能重新验收 |
| 运行代码、重构 | 受影响套件后运行公共统一入口；检查启动/退出等受影响行为 | 显式读取 JSON 中的失败、跳过、来源缺口和历史回归状态 |
| 数据查询、版本、排名、缓存、数据展示 | 公共统一入口 + 数据故障注入；独立请求/响应基准到实际 Qt 显示的回放 | 同时覆盖身份、阶段、全局/阵容、版本切换、排序和样本门槛；来源无数据应如实展示，不挪用其他范围 |
| OCR、截图、选项/详情取条件 | 公共入口 + 已批准私有原图回放；新增故障原图核对和登记 | 使用对应赛季真实图片。只证明已核对图片上的场景、身份和阶段；排名另用数据验证 |
| UI、浮层、异步、闪现 | 公共入口中的实际 Qt/生命周期检查 + 受影响界面截图，必要时连续帧/原生窗口检查 | 覆盖刷新、换牌、迟到回调、收起展开、失焦；真实 MuMu 合成与游戏 FPS 不能由离线测试推断 |
| 内存、延迟、后台任务、截图频率 | 受影响稳定性检查 + 公共入口；按受影响路径做性能对照 | 固定素材和运行条件，记录工作集、CPU、Qt 事件间隔与延迟；不要把单次体感或进程 CPU 当游戏 FPS |
| 打包、依赖、启动入口、EXE 交付 | 对应源码检查 + 全新 ZIP 的独立解压和真实 EXE 验证；受影响入口实际启动/退出 | 不能用源码启动代替 EXE；本机隔离验证不等于另一台实体电脑 |

公共统一入口使用 **Python 3.12** 和 `packaging/requirements-runtime.txt`。确认所选解释器版本，不依赖系统 `python` 恰好正确。本机已有环境时：

```powershell
$taskPython = (Resolve-Path 'work/p0-runtime/Scripts/python.exe').Path
& $taskPython --version
```

其他电脑没有该环境时，可在仓库根目录建立独立环境（先确认没有同名目录）；这仅用于开发，发布用户直接运行便携 EXE：

```powershell
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw '开发环境创建失败' }
$taskPython = (Resolve-Path '.venv/Scripts/python.exe').Path
& $taskPython -m pip install -r packaging/requirements-runtime.txt
if ($LASTEXITCODE -ne 0) { throw '运行依赖安装失败' }
```

后续命令都复用已确认的 `$taskPython`。按本轮名称更改报告路径；`$taskBase` 是开工时保存的完整提交 SHA：

```powershell
& $taskPython -X utf8 tools/validate_data.py --release-gate --regression-base-ref $taskBase --report work/TASK/offline.json
if ($LASTEXITCODE -ne 0) { throw '公共验证失败，保留报告并定位' }
& $taskPython -X utf8 tools/check_data_mutations.py --report work/TASK/mutations.json
if ($LASTEXITCODE -ne 0) { throw '数据故障注入失败' }
```

`$taskBase` 必须在实现前保存，不能在修复后覆盖成新 HEAD。历史基线比较约束来自这个提交；报告目录 `TASK` 要替换为本轮唯一名称。命令失败立即处理并保留失败报告，不继续按成功流程提交主分支。公共入口不需要 MuMu、私人图片或网站请求。

识别/截图改动及已有批准原图的本机复验，还需：

```powershell
& $taskPython -X utf8 tools/validate_data.py --include-private --release-gate --regression-base-ref $taskBase --report work/TASK/with-private.json
if ($LASTEXITCODE -ne 0) { throw '私人素材复验失败或必需证据缺失' }
```

私人样本缺失不能报通过；另一台机器可报告公共验证通过、私人检查未运行及具体原因。自定义归档不能替代或削弱项目已有批准基线。截图与玩家信息保留本机，仅提交批准索引和可公开的结论。

性能测量不要与构建、其他高负载检查并行。先设置 `$taskImage` 为本轮已核对的真实图片完整路径并确认存在；新电脑不能依赖脚本的本机默认素材路径。测反复触发、首次识别和截图释放时使用真实图片副本：

```powershell
& $taskPython -X utf8 tools/profile_runtime.py --image $taskImage --copy-frames --report work/TASK/performance-refresh.json
if ($LASTEXITCODE -ne 0) { throw '重复触发性能测量失败' }
& $taskPython -X utf8 tools/profile_runtime.py --image $taskImage --copy-frames --fresh --report work/TASK/performance-fresh.json
if ($LASTEXITCODE -ne 0) { throw '首次识别性能测量失败' }
& $taskPython -X utf8 tools/profile_runtime.py --image $taskImage --copy-frames --captures 200 --report work/TASK/performance-stress.json
if ($LASTEXITCODE -ne 0) { throw '截图释放性能测量失败' }
```

受影响测试、截图、采样和性能参数详见 [测试运行说明](testing/README.md)。网站抽查只在需要新基准时采集，串行限流、先确认可用版本，不能每轮重新抓全站，也不能自动覆盖已批准答案。

真实游戏、物理侧键、全屏合成器、游戏 FPS 或另一台电脑的结论，必须分别有实测证据。截图回放足以完成的修复，不要求为了形式重新开匹配；需要实测但当前无法完成时，明确未覆盖范围，不把模拟结果算作现场通过。

## 4. 上库前收口

1. 审阅本轮 diff 对照验收条件。涉及异步、缓存、数据身份或性能边界的改动，安排独立审阅；记录发现、修复及对应复测。审阅通过不能替代执行验证。
2. 更新验收记录：原始命令、解释器/依赖、测试源码 SHA 或起始 SHA + 已测 diff、结果、证据位置、历史回归 ID、新增样本、未运行项和原因。工作树有其他改动时列明范围，不能称作干净构建。
3. 验证后再次改运行代码/依赖/资源，重跑受影响检查，提交前完成相应统一验证；仅补文档结果无需重复重负载测试。记录要绑定最终受测代码，不能借用上一轮绿色结果。
4. 只暂存本轮明确文件，审阅暂存区。禁止 `git add .` 把其他工作一起带走。至少执行：

   ```powershell
   git diff --check
   git diff --stat
   git diff --cached --check
   git diff --cached
   ```

   全工作树检查若发现别人的问题，只记录归属；本轮文件必须通过。先用 `git add -- <本轮文件列表>` 显式暂存，再检查并提交。

完成开发的条件是：验收条件在声明的范围内满足、必需检查无未解释失败/跳过、保护旧证据、记录齐全。尚有必要验证未完成时，保留改动及记录，说明阻碍，不称为“全部修好”。

## 5. 推送与 CI

用户要求或已授权上库时，完成提交、推送和远端验证。当前项目常用 `main`，实际以开工检查到的分支/授权范围为准；不要为了匹配示例切换他人的工作分支。先设置 `$taskPushBranch` 为已确认的授权目标分支，保存本轮完整 SHA，再显式推送这个提交：

```powershell
$taskPushedSha = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw '无法读取本轮提交' }
git push origin "${taskPushedSha}:refs/heads/$taskPushBranch"
if ($LASTEXITCODE -ne 0) { throw '推送失败，不继续交付流程' }
git ls-remote origin "refs/heads/$taskPushBranch"
if ($LASTEXITCODE -ne 0) { throw '远端提交查询失败' }
gh run list --workflow data-validation.yml --branch $taskPushBranch --event push --commit $taskPushedSha --json databaseId,headSha,status,conclusion,url
if ($LASTEXITCODE -ne 0) { throw 'CI 查询失败' }
```

逐条核对原生命令退出码（PowerShell 的 `$LASTEXITCODE`）；推送失败不要继续记录为成功。核对远端分支 SHA 与 `$taskPushedSha` 一致，并选取 `headSha` 相同的 CI。若他人随后推进远端，核查本轮提交已包含在远端历史并记录情况，不强推恢复。CI 正在排队/运行时等待完成，不引用别的提交的绿色结果。使用 `gh run view <RUN_ID> --json headSha,status,conclusion,url` 查询；用 `gh run download <RUN_ID> --name data-validation-report --dir work/TASK/ci` 保留原始 JSON，下载目录不要覆盖已有记录。

当前 [CI 定义](../.github/workflows/data-validation.yml) 在 Windows/Python 3.12 上运行公共统一入口和故障注入，上传 `data-validation-report`。它**没有**构建 EXE，也没有私人原图或实际游戏。核对 `offline.json` 的源码 SHA、历史回归、显示、来源缺口、跳过/扩展状态，以及 `mutations.json` 中每项是否捕获；不能只看 Actions 绿色图标。

CI 失败时定位、修复、按受影响范围复测后重新提交；继续核对新的 SHA。验收记录补充推送 SHA、CI 链接及最终结论。结果产生在首次提交之后的，可单独提交验收记录，并注明该补充仅修改文档、引用的是哪个源码提交；不要为了让记录“自含自身 SHA”反复造提交。

## 6. 用户要求发布版本时

发布是单独的交付阶段。用户只要求设计/修复/上库时，按该范围完成；要求重新发布时，下面各项全部完成才算交付。

1. 查看已有远端 tag/release 与本机 `dist`、`dist/archive`，选择未使用版本。不要沿用脚本中的历史默认版本，不覆盖旧 ZIP、标签或已发布资产。在 `docs/releases/v<版本>.md` 写最终行为、修复点、验证与已知限制。
2. 固定已通过 CI 的源码提交。使用这个提交的干净构建目录，包含本轮源码、依赖和资源；不要把别人的未提交代码打入包。发布说明/验收记录的后续文档提交可单独记录，包的源码提交必须明确。

   建立干净交付树时，先检查运行源码与上一包之间是否存在用户已批准、验证过却尚未交付的修复；这些修复属于本次更新范围，不能仅因“不在本轮补丁”而遗漏。冻结必须交付的具体测试方法清单、依赖、素材与注册条目，在干净树报告中逐项核对实际 `passed`，再绑定包 manifest 的源码 SHA。主目录测试总数、干净树自身绿色或目录名称都不能代替这项范围核对。隔离时仍排除其它未批准工作，不能整树复制。
3. 安装 `packaging/requirements-build.txt`，从头构建。代码、资源、依赖改变或构建输出被清理后，不使用 `--skip-build`。先设置 `$taskVersion` 为确认未使用的版本，格式为 `X.Y.Z` 或 `X.Y.Z-后缀`（后缀限字母、数字、点），再执行：

   ```powershell
   & $taskPython -m pip install -r packaging/requirements-build.txt
   if ($LASTEXITCODE -ne 0) { throw '构建依赖安装失败' }
   & $taskPython -X utf8 packaging/build_windows.py --version $taskVersion
   if ($LASTEXITCODE -ne 0) { throw '候选包构建或隔离验证失败' }
   ```

4. 核对构建退出码、ZIP、`.sha256` 和 `.validation.json`。构建器自动独立解压，在仓库外中文路径限制模块/PATH 来源，运行真正 EXE。包内 `manifest.json` 的 `base_commit` 应等于已验证源码 SHA，`working_changes=false`；验证器使用当前 checkout 的展示矩阵，因此也须在这个源码提交的目录执行。

   `.validation.json` 成功条件是顶层 `exit_code=0`、嵌套 `report.status=passed`，不能查不存在的顶层 `status`；核对 `sha256/version/manifest_files_verified` 和实际检查项。先把自动离线报告复制到本版证据目录，再做联网验证，因为再次验证会覆盖 ZIP 同名报告。设置 `$taskZip` 为新 ZIP 的完整路径：

   ```powershell
   & $taskPython -X utf8 packaging/verify_windows.py $taskZip --online
   if ($LASTEXITCODE -ne 0) { throw '真正 EXE 联网验收失败' }
   Get-FileHash -LiteralPath $taskZip -Algorithm SHA256
   ```

   联网报告需实际包含 `DataJ HTTPS and real hero portrait` 的通过检查；缺少本机真实图片时，不能声称图片验收也通过。失败保留候选包与诊断，不直接公开。
5. GitHub Release 先建草稿，目标是固定源码提交，使用已保存的发布说明文件；上传 ZIP 和校验文件，等资产完成上传。不要用 `--clobber` 覆盖旧资产。检查资产名称、状态、大小、校验和与目标提交，再公开为本项目沿用的 prerelease；若用户要求正式版则按其要求。
6. 公开后重新读取 Release 状态、tag 实际解析的提交和资产列表，确认不再是 draft、下载资产可用，远端 SHA/大小与本机一致。记录 release URL、tag、源码 SHA、ZIP SHA-256、包验收报告及检查结果。

手工发布命令顺序如下。变量先从本轮记录取值：`$taskReleaseSha` 为固定完整源码 SHA；`$taskTag` 为 `v` 加新版本；`$taskNotes` 是本版发布说明路径；`$taskChecksum` 是 `$taskZip` 加 `.sha256`；`$taskDownloadDir` 是新的下载验收目录。发布说明中的相对链接需换成可从 Release 页面访问的 GitHub 链接。若用户要求正式版，创建时去掉 `--prerelease`，公开时使用 `--prerelease=false`。

```powershell
git tag -a $taskTag $taskReleaseSha -m "TFT-DataJ $taskTag"
if ($LASTEXITCODE -ne 0) { throw '标签创建失败，检查是否已存在' }
git push origin $taskTag
if ($LASTEXITCODE -ne 0) { throw '标签推送失败' }
git ls-remote origin "refs/tags/$taskTag" "refs/tags/$taskTag^{}"
if ($LASTEXITCODE -ne 0) { throw '远端标签查询失败' }
gh release create $taskTag --verify-tag --draft --prerelease --title "TFT-DataJ $taskTag" --notes-file $taskNotes
if ($LASTEXITCODE -ne 0) { throw '草稿创建失败，先核查已有状态' }
gh release upload $taskTag $taskZip $taskChecksum
if ($LASTEXITCODE -ne 0) { throw '附件上传失败，保持草稿' }
gh release view $taskTag --json tagName,isDraft,isPrerelease,targetCommitish,assets,url
if ($LASTEXITCODE -ne 0) { throw 'Release 状态读取失败' }
gh api "repos/Robin-hhc/TFT-DataJ/releases/tags/$taskTag"
if ($LASTEXITCODE -ne 0) { throw '资产上传状态读取失败' }
```

只有前述 CI、包身份/验证、附件哈希/大小与两个资产的 `state=uploaded` 都已核对，才执行公开：

```powershell
gh release edit $taskTag --draft=false --prerelease
if ($LASTEXITCODE -ne 0) { throw '公开 Release 失败，重新查询实际状态' }
gh release view $taskTag --json tagName,isDraft,isPrerelease,publishedAt,assets,url
if ($LASTEXITCODE -ne 0) { throw '公开状态核对失败' }
$taskZipName = Split-Path -Leaf $taskZip
gh release download $taskTag --pattern $taskZipName --pattern "$taskZipName.sha256" --dir $taskDownloadDir
if ($LASTEXITCODE -ne 0) { throw '远端附件下载验收失败' }
Get-FileHash -LiteralPath (Join-Path $taskDownloadDir $taskZipName) -Algorithm SHA256
```

核对下载哈希及校验附件与本机一致，并用 tag 的剥离 SHA（`refs/tags/...^{}`）核对源码；`targetCommitish` 单独不能证明注解标签实际目标。任一步失败都不能记录为发布完成，查明后续执行状态后再续跑，避免重复创建 tag 或覆盖资产。

源测试、公共 CI、隔离 EXE、现场游戏、异机运行分别记录。发布说明不能把其中一项写成其余项目也通过。完整构建与验证选项以 [打包说明](../packaging/README.md) 和实际脚本为准，执行时重新核对。

## 7. 留档与交接

| 内容 | 存放位置 | 后续 agent 如何使用 |
|---|---|---|
| 当前统一流程 | 本文 + 根目录 `AGENTS.md` 入口 | 开工先读；流程变化直接更新本文，通过 Git 留下历史 |
| 本轮验收摘要 | `docs/development-records/YYYY-MM-DD-主题.md` | 阅读目标、受测提交、命令、结果、限制及交付状态 |
| 历史问题与确切测试 | `docs/testing/regressions.json` | 保留历史 ID，检查对应行为是否实际运行 |
| 专题验证细节 | `docs/testing/*.md` | 复现某个领域的检查；过往日期记录不是当前通过证明 |
| 原始日志/JSON/性能/截图输出 | `work/<本轮名称>/` | 在摘要中记录相对路径、必要哈希和 CI 备份；本机缺失时标为不可取 |
| 私人原图与批准索引 | 本机问题归档 + `docs/testing/private-bug-baseline.json` | 保留原图，按索引核对；不公开玩家画面 |
| 发布说明与包身份 | `docs/releases/` + Release 资产、包验证报告 | 使用 tag/源码 SHA/包 SHA-256 关联实际交付版本 |

原始证据丢失时，已有摘要只证明过去记录过这些结果，不能重新宣称本轮验证通过。记录修订应追加日期、原因与新证据，不抹掉失败或未运行项。清理工作目录须先盘点依赖、进程和证据；保留运行环境、模型、游戏素材、问题归档与仍被进程使用的目录。旧发布包经 SHA-256 校验后归档并留索引，不能直接清空整个 `work` 或 `dist`。

对用户的完成答复应说明：改了什么、实际验证结果、未覆盖项，以及本轮适用的提交/CI/Release 链接。不要让用户从多份日志自行判断是否交付完成。
