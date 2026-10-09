# 定阵后全量预读海克斯的可行性

2026-10-09。先核验并提出方案，用户随后确认实施；采用的行为见[实施规格](../specs/hex-full-prewarm.md)。

## 结论

可以实现后台全量补齐。v0.2.10 已整张预读来源主表，但缺项仍在候选出现后补查，因此尚未实现完整预读。[旧版预读入口](https://github.com/Robin-hhc/TFT-DataJ/blob/be877522a95cbc1fdee320066f5ea8c04dc27a76/outputs/companion/app.py#L1439)、[缺项触发](../../outputs/companion/hex_stats.py#L37)。

## 已核验事实

- 主表读取调用 `/comp/{compId}/hexes`，保留接口全部行及其阶段统计，没有在客户端按阶段或样本量截断。[旧版适配器](https://github.com/Robin-hhc/TFT-DataJ/blob/be877522a95cbc1fdee320066f5ea8c04dc27a76/outputs/companion/dataj.py#L236)。官网前端也调用该完整表接口；未验证出可返回全部缺项的批量接口或开关。[既有官网与请求核验](../../work/hex-comp-data-audit-20261008/report.md)。
- 22:26 仅执行两次 GET，核验 S18 / 18.3 / 阵容107：全局225个ID，阵容表73个ID。全局有效阶段记录与阵容表覆盖分别为：2-1 115/25、3-2 118/58、4-2 86/40，共196个缺失的ID+阶段组合。这些组合可能需要补查，不代表检索器一定有该阵容数据，也不代表其他阵容有相同缺项数。[本轮覆盖记录](../../work/hex-latency-20261009/full-prewarm-coverage.json)。
- 已验证的补查路径是单海克斯ID加精确获得阶段，读取检索器返回的目标阵容记录。任意阶段查询不能替代三个精确阶段的数据。[旧版查询契约](https://github.com/Robin-hhc/TFT-DataJ/blob/be877522a95cbc1fdee320066f5ea8c04dc27a76/outputs/companion/dataj.py#L380)、[已有精确补查核验](../../work/hex-comp-data-audit-20261008/report.md)。
- 默认缓存有效期900秒；游戏早期的预读可能在后续阶段过期。现有查询共享最多3个活跃HTTP槽位，直接把全量补查接入交互批次会与即时查询竞争。[旧版缓存有效期](https://github.com/Robin-hhc/TFT-DataJ/blob/be877522a95cbc1fdee320066f5ea8c04dc27a76/outputs/companion/dataj.py#L85)、[旧版HTTP上限](https://github.com/Robin-hhc/TFT-DataJ/blob/be877522a95cbc1fdee320066f5ea8c04dc27a76/outputs/companion/dataj.py#L36)。
- 来源缺项与低样本相关，但没有来源服务端源码证明固定过滤阈值；不能把“每个阶段不足50局”当成已证实原因。[既有实测范围与限制](../../work/hex-comp-data-audit-20261008/report.md)。

## 建议的下一步策略

1. 定阵后立即预读全局和阵容主表，再建立尚未经过阶段的缺项清单；下一次海克斯阶段优先，其余未来阶段随后处理。
2. 后台采用低并发和明确请求间隔，为当前画面补查保留容量。切换阵容、版本、新一局时取消过时任务；同一精确查询共享结果。
3. 结果按赛季、版本、阵容、海克斯和阶段缓存，本局已预读结果保留到本局结束；跨局更新时间另设策略。无目标阵容记录也应记录本局已查，以免反复空查。
4. 海克斯出现时，先用已预读结果；尚未完成的当前三项提升优先级并逐项显示。网络不返回的记录仍显示缺数据，不能借全局或其他阶段的均排填补。
5. 验收重点是等待期后台补齐、即时请求不被后台阻塞、跨15分钟缓存仍可读、切换上下文不串数据、重复空查去重，以及不同缺项覆盖的截图回放。

这会把等待前移到两次选择之间。请求量和来源可用性仍有边界，不能保证定阵后立刻覆盖全部候选，也尚未实测全量任务对游戏帧率的影响。
