# 白银命运目录缺项核对（2026-10-10）

## 结论

19:51:57–19:52:17 的 2-1 海克斯选择中，右侧“白银命运”连续多次被 OCR 正确读出，单次七个视图读数一致。真实画面标题没有 `+`，描述为获得一个随机白银阶强化符文和 **2 金币**。

当时归档的目录和本次重新获取的 [DataJ S18 目录](https://www.dataj.cc/api/web/gamedata?setId=18) 均缺少这个无后缀版本。本次 [18.3 全局强化统计](https://www.dataj.cc/api/web/stats/hex?setId=18&gameVersion=18.3) 也没有它。目录共 263 项，统计共 225 项；来源提供的另外两个版本不能替代：

| 名称 | 来源 ID | 描述中的金币 | 有统计的阶段 |
| --- | --- | --- | --- |
| 白银命运+ | 20494 | 4 | 3-2 |
| 白银命运++ | 30494 | 7 | 4-2 |

因此本次是来源目录缺项，非截图、阶段识别或 OCR 读不到标题。当前身份未确认的显示没有细分这个原因；本轮只核对问题并增加回归，不修改运行逻辑、不猜测无后缀 ID、不删除后缀匹配其他版本，也不承诺来源没有提供的均排。

## 原图与回放

两张原图保存在本机 `work/companion/bug-cases/`，原始 `frame.png` 与 `case.json` 均未改动；增加了独立核对、哈希绑定的 `expected.json`。

| 记录 | 原图标题（从左到右） | PNG SHA-256 |
| --- | --- | --- |
| case-c2d5cd7c6a6fb8bd5c86d97cf9199065617253a96bf5174aa28d4b4337a3e98c | 灌铅骰子、基础装备自助餐、白银命运 | d1204500447a9098d4f8fe57bae99d9c124aa6d4fdb001700e3a70d568111434 |
| case-52f977784ba7bdc30854d88e0d8da17525b75f568f96aa47d7fbf3039c0d64c0 | 银汤匙、弈子配送、白银命运 | 753d9f9301c702500389f8d7d5997f82dc515e90d1f23ca2cbf334eaac812ac2 |

海克斯原图回放 **2/2 通过**：阶段 2-1 和另外两项身份均正确，白银命运预期拒绝 ID。这里的“通过”表示没有把它错配成 `+` 或 `++`，不表示已经取得该海克斯的排名。其余 28 例仍待核对，不纳入本次通过数量。

```powershell
work\p0-runtime\Scripts\python.exe -X utf8 tools/validate_bug_cases.py --run-reviewed --report work/hex-unrecognized-20261010/reviewed-replay.json
```

当前接口快照与来源清单位于 `work/hex-unrecognized-20261010/`；保存的 JSON 经解析后重新序列化，其 SHA-256 绑定保存文件，不是未经处理的 HTTP 字节。

永久回归使用 `fixtures/hex-catalog-gap-20261010.json` 中的两个真实来源行，经 `canonical_hex_catalog`、`resolve_name` 和 `stage_stat` 公共接口核对缺项拒绝、后缀身份及阶段隔离。真实原图只保存在本机，不进入公共仓库。

本轮目录、标题共识、身份解析和原图回放工具相关测试 **62 项通过，0 失败、0 错误、0 跳过**；报告保存在 `work/hex-unrecognized-20261010/regression.json`。这是针对本次诊断范围的检查，不代表重新执行完整发布验收。

测试编写者另在独立进程内注入两类错误：强行把无后缀匹配到 `+`、缺阶段时使用其他阶段统计。新断言均捕获这些错误；注入未写入运行代码。

19:54:22 另有一次右侧英雄详情 `condition_unresolved`，原因 `detail_header_icon_unconfirmed`，与此次白银命运缺项分开记录；本轮没有验证或修复该详情问题。
