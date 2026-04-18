# Channels

The scanner is designed to keep working when some channels are unavailable.
Unavailable channels should be skipped with a status entry in `latest.json`
rather than failing the whole scan.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `COMPETITOR_SCAN_OUTPUT_DIR` | `/tmp/competitor_scan` | Output directory |
| `COMPETITOR_SCAN_WINDOW_DAYS` | `14` | Recency window |
| `COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM` | `1` | Query budget per platform |
| `BAIDU_API_KEY` | empty | Enables Baidu AI and Baidu script channels |
| `BAIDU_SEARCH_SCRIPT` | `/root/.openclaw/workspace/skills/baidu-search/scripts/search.py` | Baidu standard search helper |
| `MCPORTER` | `/root/.nvm/versions/node/v22.22.2/bin/mcporter` or `mcporter` on PATH | MCP channel runner |
| `AGENT_REACH_BIN` | `/root/.agent-reach-venv/bin` | Base path for xhs and Python helpers |
| `AGENT_REACH_PYTHON` | `$AGENT_REACH_BIN/python3` | Python runtime with `miku_ai` |
| `XHS_CLI` | `$AGENT_REACH_BIN/xhs` | Xiaohongshu CLI |
| `COMPETITOR_SCAN_DISABLE_CHANNELS` | empty | Comma-separated channel names to skip |

## Channel Notes

### baidu_ai

- Endpoint: `https://qianfan.baidubce.com/v2/ai_search/chat/completions`
- Requires `BAIDU_API_KEY`.
- Parses `references[]` from the response.
- Treat HTTP 429 as quota exhaustion and continue.

### baidu

- Calls the external Baidu search skill script.
- Requires both `BAIDU_API_KEY` and `BAIDU_SEARCH_SCRIPT`.
- Use as a fallback or supplement when Baidu AI is thin.

### minimax

- Calls `mcporter call minimax.web_search`.
- MiniMax often returns a JSON object whose `text` field contains another JSON
  string. Parse the inner `organic[]` array.
- If MiniMax returns no usable result, Exa remains available as a separate
  channel.

### exa

- Calls `mcporter call exa.web_search_exa`.
- Responses may be plain text with `Title:`, `URL:`, `Published:`,
  `Highlights:` sections rather than JSON.

### weibo

- Calls `mcporter call weibo.search_content`.
- Use for direct platform/content searches.

### weibo_hot

- Calls `mcporter call weibo.get_trendings`.
- Keep only entries that mention the target platform or a configured alias.
- Filter obvious social noise before final reporting.

### xhs

- Calls the Xiaohongshu CLI and parses display title, author, and relative time
  from the CLI text output.

### wechat

- Uses `miku_ai.get_wexin_article` from the Agent Reach Python runtime.
- Extract dates from `timestamp=` URL parameters when present.
