---
name: competitor-scan
description: >
  Run an on-demand competitive intelligence scan for Chinese content and social
  platforms, especially 抖音、抖音精选、快手、微信视频号、B站、微博、豆包. Use when
  the user asks for 竞品监控、竞品动态、竞品报告、竞品扫描、生成竞品日报、跑一下竞品,
  or needs recent user-growth signals across 增长策略、产品功能、运营动作. The skill
  collects recent signals with bundled scripts, then turns structured results
  into a concise Chinese report.
---

# Competitor Scan

## Goal

Generate an on-demand competitive intelligence report for recent user-growth
signals. Focus on actions and evidence from the last 14 days by default, not on
full statistical market sizing.

Default platforms:

- 抖音
- 抖音精选
- 快手
- 微信视频号
- B站
- 微博
- 豆包

Default dimensions:

- 增长策略: 拉新活动、新用户补贴、邀请奖励、KOL 合作、分享激励、渠道投放、创作者激励、现金分成
- 产品功能: 新功能上线、算法改版、内容分发、搜索推荐入口、AI 工具
- 运营动作: 话题活动、节日活动、补贴政策、大赛征稿、创作者计划

## Workflow

1. Confirm whether the user wants the default 7 platforms and 14-day window. If
   they do not specify otherwise, use the defaults.
2. If MCP-backed channels are needed, install and check Agent-Reach, then start
   mcporter when your local setup requires a daemon:

   ```bash
   python3 -m pip install agent-reach || python3 -m pip install https://github.com/Panniantong/Agent-Reach/archive/refs/heads/main.zip
   agent-reach doctor
   mcporter daemon start
   ```

3. Run the scanner from the skill directory:

   ```bash
   python3 scripts/scan.py
   ```

4. Read the generated structured data first:

   - `$COMPETITOR_SCAN_OUTPUT_DIR/latest.json`
   - `$COMPETITOR_SCAN_OUTPUT_DIR/latest_report.txt`

5. Produce the final report in Chinese. Prefer the structured JSON over raw
   text. Keep source/date labels visible for each signal. Do not invent details
   that are not present in the scan output.

## Output Contract

The scanner writes:

- `latest.json`: structured scan data with `platform`, `dimension`, `title`,
  `date`, `source`, `source_label`, `url`, `author`, `content`, and `query`.
- `latest_report.txt`: raw human-readable scan summary for quick inspection.

When writing the final report:

- Group by platform in the fixed order above.
- Within each platform, group by 增长策略、产品功能、运营动作.
- Include every valuable signal. Omit obvious social noise and unrelated hot
  search topics.
- Show each signal as title, date/source label, optional URL or author, and a
  short substance summary when available.
- Mark sections as `暂无有效信号` only after checking the structured JSON.

Read `references/report-format.md` when exact formatting matters.

## Configuration

The script supports environment overrides. Set secrets as environment variables;
never paste them into the skill files.

- `COMPETITOR_SCAN_OUTPUT_DIR`
- `COMPETITOR_SCAN_WINDOW_DAYS`
- `COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM`
- `BAIDU_AI_SEARCH_API_KEY`
- `BAIDU_API_KEY`
- `BAIDU_SEARCH_SCRIPT`
- `MCPORTER`
- `AGENT_REACH`
- `AGENT_REACH_BIN`
- `AGENT_REACH_PYTHON`
- `MINIMAX_API_KEY`
- `XHS_CLI`
- `COMPETITOR_SCAN_DISABLE_CHANNELS`

Read `references/channels.md` for channel behavior, dependencies, and fallback
rules. Read `references/maintenance.md` before adding platforms, channels, or
new parsing logic.
