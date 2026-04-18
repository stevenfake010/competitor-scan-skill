---
name: competitor-scan
description: >
  Run a full competitive intelligence scan across 7 platforms (抖音、抖音精选、快手、视频号、B站、微博、豆包),
  covering user growth signals in 3 dimensions: 增长策略、产品功能、运营动作.
  Trigger phrases: "竞品监控"、"竞品动态"、"竞品报告"、"跑一下竞品"、"生成竞品日报"、"竞品扫描".
  No scheduled push — this skill is called on-demand.
metadata:
  openclaw:
    homepage: null
    standalone: true
    trigger_priority: high
---

# Competitor Scan Skill

## Purpose

Generate a competitive intelligence report on demand, covering **7 platforms** and **3 dimensions**:

**Platforms**: 抖音、抖音精选、快手、微信视频号、B站、微博、豆包

**Dimensions**:
- 增长策略（拉新活动、新用户补贴、邀请奖励、KOL合作、分享激励、渠道投放、创作者激励计划、现金分成）
- 产品功能（新功能上线、算法改版、内容分发策略、搜索推荐入口、AI工具）
- 运营动作（话题活动、节日活动、创作者激励计划补贴政策、大赛征稿）

**Time window**: 双周内（14天），动作/信号导向，不含数据统计

---

## Execution

### Step 1: 确保 mcporter daemon 运行

```bash
/root/.nvm/versions/node/v22.22.2/bin/mcporter daemon start
```

> mcporter 路径：`/root/.nvm/versions/node/v22.22.2/bin/mcporter`（注意：不是 `~/.agent-reach-venv/bin/mcporter`）

### Step 2: 运行扫描

```bash
python3 skills/competitor-scan/scripts/scan.py
```

### Step 3: 读取结构化数据，生成报告

数据文件：
- `/tmp/competitor_scan/latest_report.txt`（原始文本）
- `/tmp/competitor_scan/latest.json`（结构化数据，含 source/date/title/content/platform）

---

## 报告模板（已确认格式）

```
📡 竞品动态日报 · YYYY-MM-DD
覆盖：7平台 | 渠道：百度AI搜索+MiniMax+微博热搜+微信公众号+小红书+Exa | 窗口：MM-DD～MM-DD

共 N 条有效信号（原始X条，已过滤微博热搜社会噪音）

🔵 抖音
  ▶ 增长策略
  ① 信号标题
     [日期 · 来源标签]
     内容描述（可选，若有实质性内容）
  ② 信号标题
     [日期 · 来源标签]
  ...

🔶 抖音精选
  ...

🟢 快手
  ...

🔴 微信视频号
  ...

🟣 B站
  ...

🟠 微博
  ...

🟡 豆包
  ...
```

### 格式规则（严格遵守）
- emoji 平台标识：🔵抖音 🔶抖音精选 🟢快手 🔴微信视频号 🟣B站 🟠微博 🟡豆包
- 每条信号：① 标题；单独一行 `[日期 · 来源]`
- 内容描述：单独一行缩进，提取实质内容（略去页面导航碎片）
- **不限制条数**，所有有价值的信号全部展示
- 时间格式：`YYYY-MM-DD`（有明确日期的）或相对表达（"3天前"）
- 过滤：微博热搜中与竞品无关的社会噪音（如"航班取消""麻辣烫阿姨"类话题）

### 信号去重规则
- 以标题60字符为去重key
- 保留第一条出现的信号

---

## 渠道配置

| 标签 | 来源 | 状态 |
|------|------|------|
| baidu_ai | 百度AI搜索（/v2/ai_search/chat/completions，100次/天） | ✅ 正常 |
| baidu | 百度标准搜索（/v2/ai_search/web_search，50次/天，配额耗尽则0） | ⚠️ 配额制 |
| minimax | MiniMax MCP（via mcporter，12s超时，自动fallback Exa） | ✅ 正常 |
| exa | Exa MCP（via mcporter，解析纯文本key-value格式） | ✅ 正常 |
| weibo | 微博内容搜索（via mcporter mcp-server-weibo） | ✅ 正常 |
| weibo_hot | 微博热搜（via mcporter，实时） | ✅ 正常 |
| xhs | 小红书 CLI（/root/.agent-reach-venv/bin/xhs） | ✅ 正常 |
| wechat | 微信公众号（miku_ai，URL解析timestamp提取日期） | ✅ 正常 |

---

## 技术要点

### 百度AI搜索（baidu_ai）
- **Endpoint**：`https://qianfan.baidubce.com/v2/ai_search/chat/completions`
- **响应格式**：`{"references": [{"id", "url", "title", "date", "content"}]}`
- **解析方式**：直接从 `references[]` 提取，`date` 字段做14天过滤
- **配额**：100次/天，超出返回429

### MiniMax MCP
- **调用方式**：`mcporter call minimax.web_search`
- **响应格式**：双层嵌套 `{"type":"text","text":"{...organic...}"}`
- **解析方式**：先解析外层 `text` 字段，再从 inner JSON 取 `organic[]`
- **超时**：12秒，超时则 fallback 到 Exa

### Exa MCP
- **调用方式**：`mcporter call exa.web_search_exa`
- **响应格式**：纯文本 key-value（非JSON），如 `Title: xxx\nURL: xxx\nPublished: xxx\nHighlights: xxx`
- **解析方式**：用正则 `(?=Title:)` 分割条目，分别提取各字段

### 微信公众号（wechat）
- **调用方式**：miku_ai（`/root/.agent-reach-venv/bin/python3`）
- **日期解析**：从 URL 参数 `timestamp=XXXXXXXXXX` 提取unix时间戳，转为 `YYYY-MM-DD`
- **miku_ai测试**：`/root/.agent-reach-venv/bin/python3 -c "import miku_ai; print('OK')"`

### mcporter 路径
- **正确路径**：`/root/.nvm/versions/node/v22.22.2/bin/mcporter`
- **错误路径**：`/root/.agent-reach-venv/bin/mcporter`（不存在）
- scan.py 中已修正为正确路径

---

## 维护说明

- **新增平台**：在 `scan.py` 的 `PLATFORM_QUERIES` 字典中添加条目
- **新增渠道**：在 `search_all_channels()` 函数中添加新的搜索调用
- **更新搜索词**：修改对应平台的查询关键词列表
- **调试**：`/tmp/competitor_scan/latest_report.txt` 检查原始输出
- **Syntax check**：`python3 -c "import ast; ast.parse(open('scan.py').read()); print('OK')"`
