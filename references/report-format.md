# Report Format

Use this format when the user asks for a formal 竞品动态日报.

```text
竞品动态日报 · YYYY-MM-DD
覆盖：7 平台 | 渠道：百度AI搜索+MiniMax+微博热搜+微信公众号+小红书+Exa | 窗口：MM-DD～MM-DD

共 N 条有效信号（原始 X 条，已过滤过期信息和无关社会噪音）

🔵 抖音
  ▶ 增长策略
  ① 信号标题
     [YYYY-MM-DD · 来源标签]
     内容描述（可选，保留实质动作、政策、功能或运营信息）

  ▶ 产品功能
  暂无有效信号

  ▶ 运营动作
  ① 信号标题
     [3天前 · 来源标签]
     内容描述

🟡 抖音精选
...
```

## Platform Order And Labels

- 🔵 抖音
- 🟡 抖音精选
- 🟢 快手
- 🔴 微信视频号
- 🟣 B站
- 🟠 微博
- 🟤 豆包

## Rules

- Keep the title on one line.
- Put `[日期 · 来源]` on a separate line.
- Put content summary on a separate indented line only when it adds substance.
- Keep all valuable signals. Do not impose an arbitrary top-N cap in the final
  report unless the user asks for a brief version.
- Prefer exact dates. If only a relative time exists, keep it as given.
- Filter unrelated 微博热搜 social noise, such as celebrity gossip, travel
  disruptions, food trends, or public incidents that do not mention the target
  platform or a directly relevant creator/product/growth action.
- When a source appears multiple times with the same title, keep the first
  useful instance and avoid repeating duplicates.
