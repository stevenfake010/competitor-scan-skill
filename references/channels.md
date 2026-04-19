# Channels

The scanner is designed to keep running when some channels are unavailable.
Unavailable channels should appear in `latest.json -> channels` and in the
final report's “监测质量与缺口” section instead of failing the whole scan.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `COMPETITOR_SCAN_OUTPUT_DIR` | system temp directory + `competitor_scan` | Output directory |
| `COMPETITOR_SCAN_WINDOW_DAYS` | `14` | Recency window |
| `COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM` | `1` | Query budget per platform |
| `COMPETITOR_SCAN_MIN_SIGNAL_SCORE` | `48` | Minimum total score to keep a signal |
| `COMPETITOR_SCAN_TOP_PRIORITY_SIGNAL_LIMIT` | `6` | Global top-signal cap in the management section |
| `COMPETITOR_SCAN_PLATFORM_EVENT_LIMIT` | `5` | Maximum events shown per platform in the text report |
| `COMPETITOR_SCAN_REPORT_AUDIENCE` | `业务负责人` | Audience label in final report |
| `BAIDU_AI_SEARCH_API_KEY` | empty | Enables Baidu AI Search |
| `BAIDU_API_KEY` | empty | Enables legacy Baidu search helper |
| `BAIDU_SEARCH_SCRIPT` | legacy Linux path | External Baidu search helper path |
| `MCPORTER` | `mcporter` on PATH, then legacy Linux path | MCP channel runner |
| `AGENT_REACH` | `agent-reach` on PATH | Agent-Reach CLI |
| `AGENT_REACH_BIN` | legacy Linux path | Legacy helper directory |
| `AGENT_REACH_PYTHON` | auto-detected Python with `agent_reach` | Python runtime with `miku_ai` |
| `MINIMAX_API_KEY` | empty | MiniMax credential |
| `MINIMAX_SEARCH_ENDPOINT` | `https://api.minimax.io/v1/coding_plan/search` | Direct MiniMax endpoint |
| `MINIMAX_AUTH_MODE` | `bearer` | `bearer` or `raw` auth header mode |
| `XHS_CLI` | `$AGENT_REACH_BIN/xhs` | Xiaohongshu CLI fallback |
| `XHS_COOKIE_SOURCE` | `auto` | Browser cookie source for Xiaohongshu login |
| `XHS_COOKIE_HEADER` | empty | Manual Xiaohongshu `Cookie:` header string |
| `XHS_COOKIE_JSON` | empty | Manual Xiaohongshu cookie JSON or Cookie-Editor export |
| `XHS_RUNTIME_HOME` | empty | Optional dedicated home directory for `xhs-cli` runtime state |
| `XHS_AUTO_LOGIN` | `1` | Whether to try browser-cookie login automatically |
| `COMPETITOR_SCAN_DISABLE_CHANNELS` | empty | Comma-separated channel names to skip |

## Agent-Reach Setup

Agent-Reach remains the preferred cross-platform provider for Exa, Weibo,
Xiaohongshu, and WeChat article access:

```bash
python3 -m pip install agent-reach || python3 -m pip install https://github.com/Panniantong/Agent-Reach/archive/refs/heads/main.zip
agent-reach install --env=auto --channels=weibo,wechat,xiaohongshu
agent-reach doctor
```

If you use a portable Node build on Windows, put the Node directory on `PATH`
before running the scanner so `mcporter` can start correctly.

## Channel Notes

### baidu_ai

- Endpoint: `https://qianfan.baidubce.com/v2/ai_search/chat/completions`
- Requires `BAIDU_AI_SEARCH_API_KEY`
- Primary structured source for recent Chinese search results

### baidu

- Calls the external Baidu search skill script
- Requires `BAIDU_API_KEY` and `BAIDU_SEARCH_SCRIPT`
- Best used as a supplement or compatibility fallback

### minimax

- First tries `mcporter minimax.web_search`
- Falls back to direct HTTP via `MINIMAX_SEARCH_ENDPOINT`
- Supports `MINIMAX_AUTH_MODE=bearer|raw`
- If the service returns `invalid api key`, mark the channel gap explicitly

### exa

- Calls `mcporter exa.web_search_exa`
- May return plain text with `Title / URL / Published / Highlights`
- Useful for mainstream media and domain-specific fallback searches

### official

- Uses Exa with platform-specific `site:` filters over configured official or
  help-center domains
- Targets official announcements, creator centers, help pages, agreements,
  rules, and support pages
- Only keep results that look like actual documentation or announcements; do
  not treat platform content pages as official rule evidence
- When adding platforms whose official domains also host user videos, posts, or
  profiles, configure content-page URL markers in `PLATFORM_CONFIG`

### creator_activity

- Uses Exa to find creator tasks, submission campaigns, cash rewards, creator
  recruitment, MCN/talent calls, and platform activity pages
- Best used as a source for creator supply, activation, and campaign events

### ad_signal

- Uses Exa to find ad-buying, paid acquisition, creative/material, and platform
  advertising signals
- Treat marketing-service pages cautiously; they may indicate market activity
  but should not drive P1 priority without corroboration

### weibo

- First tries `mcporter weibo.search_content`
- Falls back to direct `mcp_server_weibo` Python-package calls on Windows or
  when MCP stdio is unstable

### weibo_hot

- First tries `mcporter weibo.get_trendings`
- Falls back to direct `mcp_server_weibo` Python-package calls
- Only keep trendings that mention the target platform or its aliases

### xhs

- First tries `mcporter xiaohongshu.search_feeds`
- If `XHS_COOKIE_HEADER` or `XHS_COOKIE_JSON` is provided, writes an isolated
  `xhs-cli` cookie store under a temporary or configured runtime home
- Then tries `xhs status --json`
- If unauthenticated and `XHS_AUTO_LOGIN=1`, attempts
  `xhs login --cookie-source <XHS_COOKIE_SOURCE> --json`
- Then retries `xhs search <query> --sort latest --json`
- This path works on Windows/macOS/Linux because it does not require Docker or
  a Linux-only browser-cookie layout
- If cookies are unavailable or invalid, mark the gap explicitly as an auth gap

### wechat

- First uses `miku_ai.get_wexin_article`
- If that returns nothing useful and `mcporter` is available, falls back to
  `site:mp.weixin.qq.com` search through Exa

## Reliability Model

The scanner scores each signal on two axes:

1. **Credibility**
   - official/platform domains
   - mainstream media
   - public-article evidence
   - low-credibility SEO/aggregation sites

2. **Business relevance**
   - platform alias hit
   - growth keyword hit
   - dimension keyword hit
   - direct evidence of creator incentives, traffic rules, AI capability, or
     commercialization

The final report only keeps signals above the configured score threshold.

The text report is event-based:

- Signals are filtered for user-growth relevance.
- Similar signals are clustered into events.
- Event priority is computed from the strongest signal plus evidence mix,
  source diversity, and recency.
- The report shows event clusters by platform; raw retained signals remain in
  `latest.json -> by_platform`.
- Platform-specific keywords and event phrases are clustering aids, not a report
  perspective. The default report should stay neutral across all monitored
  competitors.
