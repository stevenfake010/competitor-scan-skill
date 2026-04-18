---
name: competitor-scan
description: >
  Run an on-demand competitor intelligence scan for Chinese content and social
  platforms, especially 抖音、抖音精选、快手、微信视频号、B站、微博、豆包.
  Use when the user asks for 竞品扫描、竞品监控、竞品动态、竞品日报、用户增长情报、
  创作者生态变化、平台增长动作，或需要一份能直接给业务负责人阅读的竞品用户增长简报。
  The skill collects recent signals, scores source credibility and business
  relevance, and outputs a leadership-ready Chinese report with analyst
  judgements and implications for 小红书.
---

# Competitor Scan

## Goal

Generate a business-ready competitor user-growth brief for leadership review.
The output should read like a strategy analyst's note, not a raw search dump.
Focus on recent actions that affect:

- 创作者供给争夺
- 流量与分发机制
- 内容/产品能力升级
- 商业化与变现链路
- 运营活动与增长动作

Default platforms:

- 抖音
- 抖音精选
- 快手
- 微信视频号
- B站
- 微博
- 豆包

Default time window:

- 最近 14 天

## Workflow

1. Use the bundled scanner:

   ```bash
   python3 scripts/scan.py
   ```

2. Read structured output first:

   - `$COMPETITOR_SCAN_OUTPUT_DIR/latest.json`
   - `$COMPETITOR_SCAN_OUTPUT_DIR/latest_report.txt`

3. Prefer the JSON payload when writing a final answer. The scanner already
   computes:

   - source credibility
   - business relevance
   - priority (`P1`/`P2`/`P3`)
   - action type
   - analyst judgement
   - implication for 小红书

4. Preserve uncertainty. If a channel is unavailable, use the channel status in
   `latest.json` instead of inventing coverage.

## Output Contract

The scanner writes:

- `latest.json`
  - `summary.management_summary`
  - `summary.priority_signals`
  - `summary.monitor_gaps`
  - `platform_analysis`
  - `channels`
  - `by_platform`
- `latest_report.txt`
  - a leadership-ready Chinese brief that can be sent directly to a business
    owner

When writing a final response:

- Lead with the top management takeaways.
- Prefer exact dates.
- Keep evidence visible for every important signal.
- Call out monitoring gaps separately from business conclusions.
- Do not treat low-credibility SEO pages as strong evidence unless corroborated.

Read `references/report-format.md` when exact structure matters.

## Configuration

Never hard-code secrets. Read them from environment variables only.

Core variables:

- `COMPETITOR_SCAN_OUTPUT_DIR`
- `COMPETITOR_SCAN_WINDOW_DAYS`
- `COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM`
- `COMPETITOR_SCAN_MIN_SIGNAL_SCORE`
- `COMPETITOR_SCAN_TOP_PRIORITY_SIGNAL_LIMIT`
- `COMPETITOR_SCAN_REPORT_AUDIENCE`

Channel variables:

- `BAIDU_AI_SEARCH_API_KEY`
- `BAIDU_API_KEY`
- `BAIDU_SEARCH_SCRIPT`
- `MCPORTER`
- `AGENT_REACH`
- `AGENT_REACH_BIN`
- `AGENT_REACH_PYTHON`
- `MINIMAX_API_KEY`
- `MINIMAX_SEARCH_ENDPOINT`
- `MINIMAX_AUTH_MODE`
- `XHS_CLI`
- `XHS_COOKIE_SOURCE`
- `XHS_COOKIE_HEADER`
- `XHS_COOKIE_JSON`
- `XHS_RUNTIME_HOME`
- `XHS_AUTO_LOGIN`
- `COMPETITOR_SCAN_DISABLE_CHANNELS`

Read `references/channels.md` for dependency and fallback behavior.
Read `references/maintenance.md` before changing the schema, scoring model, or
report structure.
