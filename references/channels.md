# Channels

The scanner is designed to keep working when some channels are unavailable.
Unavailable channels should be skipped with a status entry in `latest.json`
rather than failing the whole scan.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `COMPETITOR_SCAN_OUTPUT_DIR` | system temp directory + `competitor_scan` | Output directory |
| `COMPETITOR_SCAN_WINDOW_DAYS` | `14` | Recency window |
| `COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM` | `1` | Query budget per platform |
| `BAIDU_AI_SEARCH_API_KEY` | empty | Enables Baidu AI Search |
| `BAIDU_API_KEY` | empty | Backward-compatible Baidu key fallback and Baidu script channel key |
| `BAIDU_SEARCH_SCRIPT` | `/root/.openclaw/workspace/skills/baidu-search/scripts/search.py` | Baidu standard search helper |
| `MCPORTER` | `mcporter` on PATH, then legacy Linux path | MCP channel runner |
| `AGENT_REACH` | `agent-reach` on PATH | Agent-Reach CLI |
| `AGENT_REACH_BIN` | `/root/.agent-reach-venv/bin` | Legacy Linux helper directory |
| `AGENT_REACH_PYTHON` | auto-detected Python with `agent_reach` | Python runtime with `miku_ai` |
| `MINIMAX_API_KEY` | empty | MiniMax credential; current scanner expects a mcporter MiniMax bridge for search |
| `XHS_CLI` | `$AGENT_REACH_BIN/xhs` | Xiaohongshu CLI fallback |
| `COMPETITOR_SCAN_DISABLE_CHANNELS` | empty | Comma-separated channel names to skip |

## Agent-Reach Setup

Agent-Reach is the preferred cross-platform provider for Exa, Weibo,
Xiaohongshu, and WeChat article access. Install it in the runtime that will run
the skill:

```bash
python3 -m pip install agent-reach || python3 -m pip install https://github.com/Panniantong/Agent-Reach/archive/refs/heads/main.zip
agent-reach install --env=auto --channels=weibo,wechat,xiaohongshu
agent-reach doctor
```

The scanner calls `mcporter` from `PATH` unless `MCPORTER` is set. Node.js/npm
must be available for `mcporter`. On Windows, put the Node directory on `PATH`
before running the scanner if you use a portable Node build.

Supported Agent-Reach command shapes include:

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'weibo.search_content(keyword: "query", limit: 5)'
mcporter call 'weibo.get_trendings(limit: 20)'
mcporter call 'xiaohongshu.search_feeds(keyword: "query")'
```

Some `mcporter` versions are more reliable with key/value arguments on Windows,
so the scanner automatically falls back to calls like:

```bash
mcporter call exa.web_search_exa query="query" numResults=5
```

Xiaohongshu may require local login/cookies depending on the Agent-Reach setup.
WeChat article search uses `miku_ai.get_wexin_article` from a Python runtime
where Agent-Reach is installed. The scanner auto-detects that runtime when
`AGENT_REACH_PYTHON` is not set.

## Channel Notes

### baidu_ai

- Endpoint: `https://qianfan.baidubce.com/v2/ai_search/chat/completions`
- Requires `BAIDU_AI_SEARCH_API_KEY`; falls back to `BAIDU_API_KEY` for older
  environments.
- Parses `references[]` from the response.
- Treat HTTP 429 as quota exhaustion and continue.
- Uses Python standard library HTTP calls; no `requests` dependency is needed.

### baidu

- Calls the external Baidu search skill script.
- Requires both `BAIDU_API_KEY` and `BAIDU_SEARCH_SCRIPT`.
- Use as a fallback or supplement when Baidu AI is thin.

### minimax

- Calls `mcporter call 'minimax.web_search(query: "...", numResults: 5)'`.
- The MiniMax API key should be exposed as `MINIMAX_API_KEY`, but direct HTTP
  web-search calls are intentionally not hard-coded here because the public
  endpoint shape can differ by account/product. Configure a `mcporter` MiniMax
  bridge when using this channel.
- MiniMax often returns a JSON object whose `text` field contains another JSON
  string. Parse the inner `organic[]` array.
- If MiniMax returns no usable result, Exa remains available as a separate
  channel.

### exa

- Calls `mcporter call 'exa.web_search_exa(query: "...", numResults: 5)'`.
- Responses may be plain text with `Title:`, `URL:`, `Published:`,
  `Highlights:` sections rather than JSON.

### weibo

- Calls `mcporter call 'weibo.search_content(keyword: "...", limit: 5)'`.
- Use for direct platform/content searches.

### weibo_hot

- Calls `mcporter call 'weibo.get_trendings(limit: 20)'`.
- Keep only entries that mention the target platform or a configured alias.
- Filter obvious social noise before final reporting.

### xhs

- First calls `mcporter call 'xiaohongshu.search_feeds(keyword: "...")'`.
- Falls back to the Xiaohongshu CLI if `XHS_CLI` is available.
- Parses display title, author, relative time, note ID, and URL when present.

### wechat

- Uses `miku_ai.get_wexin_article` from the Agent Reach Python runtime.
- Extract dates from `timestamp=` URL parameters when present.
