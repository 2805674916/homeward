---
name: train-plan
description: 归途火车出行规划。用户说买火车票回家、查余票、换乘、买短乘长、买长乘短，或给出出发地、目的地、日期和预算时使用；生成单文件离线 HTML 的归途车票与省界地图报告。
---

# 归途 / train-plan

用本目录 `scripts/search.py` 进行受限、串行的 12306 查询和最多三次换乘的候选路径搜索。不要代用户下单，不要将候补或车上补票描述为可立即购买的全程票。

## 输入与默认值

- 出发/到达城市、日期、到达截止为必要信息；人数默认 1、最早出发 00:00、最多换乘 3 次。
- 到达截止不明确时可以从语义合理推断，例如“次日上午”取 12:00，并明确说明；只有改变实际搜索边界的歧义才向用户确认。
- 单人预算可选。官方查询节流至少 3 秒，不并发、不多开；`--max-queries` 默认 120（含约 30 次核价预留），不要超过 150。

## 运行

从本 skill 的 `scripts/` 目录运行（不要依赖当前工作目录）：

```bash
python search.py --from-city 上海 --to-city 武汉 --date YYYY-MM-DD \
  --after 18:00 --arrive-by "YYYY-MM-DD 12:00" \
  --people 1 --budget 800 --max-transfers 3 --max-queries 80 --out report.html
```

首次运行会把 12306 站名表下载到 `scripts/.cache/`；已打包的 Public Domain 省界位于 `assets/china_adm1.geojson`。`search.py --out` 一次生成包含 CSS、SVG、数据的离线 HTML。若只重绘已有 JSON，可运行 `python render.py plans.json report.html`。

向用户给出报告绝对路径及最值得关注的几个方案，明确每段的上车站、下车站、车次、换乘时间、实际可买席别和每人票价。仅当所有已购票段核价成功才报确定合计；补票区间和接口缺价标“待核价”。结果受候选枢纽、接口状态和查询额度限制，不是全国穷举。买长乘短与买短乘长仅作有限候选尝试，补票可能失败。

说明地图是站点间地理示意，并非真实铁轨；余票、票价和时刻以 12306 官方页面为准。领域策略与风险见 `references/tactics.md`，搜索的图模型与完备性边界见 `references/math.md`。不公开用户真实行程报告、Cookie 或查询缓存。
