#!/usr/bin/env python3
"""
On-demand competitor signal scanner.

The script collects recent competitive intelligence signals from several
optional channels, normalizes them, and writes both JSON and text summaries for
an agent to turn into the final report.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


WINDOW_DAYS = int(os.environ.get("COMPETITOR_SCAN_WINDOW_DAYS", "14"))
MAX_QUERIES_PER_PLATFORM = int(
    os.environ.get("COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM", "1")
)
OUTPUT_DIR = Path(os.environ.get("COMPETITOR_SCAN_OUTPUT_DIR", "/tmp/competitor_scan"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime.now()
DATE_TODAY = NOW.strftime("%Y-%m-%d")
DATE_START = (NOW - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

BAIDU_API_KEY = os.environ.get("BAIDU_API_KEY", "").strip()
BAIDU_SEARCH_SCRIPT = os.environ.get(
    "BAIDU_SEARCH_SCRIPT",
    "/root/.openclaw/workspace/skills/baidu-search/scripts/search.py",
)
AGENT_REACH_BIN = os.environ.get("AGENT_REACH_BIN", "/root/.agent-reach-venv/bin")
AGENT_REACH_PYTHON = os.environ.get(
    "AGENT_REACH_PYTHON", str(Path(AGENT_REACH_BIN) / "python3")
)
MCPORTER = os.environ.get("MCPORTER") or shutil.which("mcporter") or (
    "/root/.nvm/versions/node/v22.22.2/bin/mcporter"
)
XHS_CLI = os.environ.get("XHS_CLI", str(Path(AGENT_REACH_BIN) / "xhs"))
DISABLED_CHANNELS = {
    c.strip()
    for c in os.environ.get("COMPETITOR_SCAN_DISABLE_CHANNELS", "").split(",")
    if c.strip()
}

PLATFORM_ORDER = ["抖音", "抖音精选", "快手", "微信视频号", "B站", "微博", "豆包"]

PLATFORM_ALIASES = {
    "抖音": ["抖音", "Douyin", "字节跳动"],
    "抖音精选": ["抖音精选"],
    "快手": ["快手", "可灵", "Kwai"],
    "微信视频号": ["视频号", "微信视频号"],
    "B站": ["B站", "哔哩哔哩", "bilibili"],
    "微博": ["微博", "Weibo"],
    "豆包": ["豆包", "Doubao", "字节跳动AI"],
}

PLATFORM_HINTS = {
    "抖音": "创作者激励 补贴 新功能",
    "抖音精选": "月榜 创作者 增长",
    "快手": "创作者激励 可灵AI 运营",
    "微信视频号": "直播 拉新 创作者分成",
    "B站": "创作者激励 新功能 用户增长",
    "微博": "创作者激励 流量扶持 热点运营",
    "豆包": "AI助手 用户增长 产品功能",
}

DIMENSION_KEYWORDS = {
    "增长策略": [
        "增长",
        "拉新",
        "新用户",
        "补贴",
        "邀请",
        "奖励",
        "KOL",
        "投放",
        "创作者激励",
        "分成",
        "流量扶持",
    ],
    "产品功能": [
        "功能",
        "上线",
        "更新",
        "改版",
        "算法",
        "推荐",
        "搜索",
        "入口",
        "AI",
        "工具",
        "模型",
    ],
    "运营动作": [
        "活动",
        "话题",
        "节日",
        "挑战赛",
        "大赛",
        "征稿",
        "直播",
        "运营",
        "扶持计划",
    ],
}

CHANNEL_LABELS = {
    "baidu_ai": "百度AI搜索",
    "baidu": "百度搜索",
    "minimax": "MiniMax",
    "exa": "Exa",
    "weibo": "微博内容",
    "weibo_hot": "微博热搜",
    "xhs": "小红书",
    "wechat": "微信公众号",
}

SOCIAL_NOISE_KEYWORDS = [
    "航班",
    "地震",
    "暴雨",
    "麻辣烫",
    "明星",
    "恋情",
    "离婚",
    "演唱会",
    "彩票",
]

channel_status: dict[str, dict[str, Any]] = {}


def log(message: str) -> None:
    print(message, flush=True)


def command_available(command: str) -> bool:
    if not command:
        return False
    if os.path.isabs(command):
        return Path(command).exists()
    return shutil.which(command) is not None


def channel_disabled(channel: str) -> bool:
    return channel in DISABLED_CHANNELS


def mark_channel(channel: str, ok: bool, detail: str = "") -> None:
    current = channel_status.setdefault(
        channel, {"ok": True, "calls": 0, "skipped": 0, "details": []}
    )
    current["calls"] += 1
    if not ok:
        current["ok"] = False
        current["skipped"] += 1
    if detail:
        current["details"].append(detail)


def run_cmd(args: list[str], timeout: int = 30, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env or os.environ.copy(),
            check=False,
        )
        return result.stdout + (result.stderr if result.returncode else "")
    except Exception as exc:
        return f"[CMD ERROR] {exc}"


def clean_text(value: Any, limit: int | None = None) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] if limit else text


def extract_json(raw: str) -> Any | None:
    if not raw or len(raw) < 2:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    for left, right in [("[", "]"), ("{", "}")]:
        start = raw.find(left)
        end = raw.rfind(right)
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                pass
    return None


def parse_date(raw_date: Any, now: datetime | None = None) -> datetime | None:
    now = now or NOW
    if not raw_date:
        return None
    text = str(raw_date).strip()
    text = re.sub(r"^(发布于|发表于|更新于)[:：]?", "", text).strip()

    full_datetime = re.search(
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?",
        text,
    )
    if full_datetime:
        candidate = full_datetime.group(0).replace("/", "-")
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, pattern)
            except Exception:
                pass

    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except Exception:
            pass

    match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if match:
        try:
            parsed = datetime(now.year, int(match.group(1)), int(match.group(2)))
            if parsed > now + timedelta(days=1):
                parsed = parsed.replace(year=parsed.year - 1)
            return parsed
        except Exception:
            pass

    match = re.search(r"(\d+)\s*天前", text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    match = re.search(r"(\d+)\s*小时前", text)
    if match:
        return now - timedelta(hours=int(match.group(1)))
    match = re.search(r"(\d+)\s*分钟前", text)
    if match:
        return now - timedelta(minutes=int(match.group(1)))
    if text.startswith("昨天"):
        return now - timedelta(days=1)
    if text.startswith("今天") or re.fullmatch(r"\d{1,2}:\d{2}", text):
        return now
    return None


def normalize_date(raw_date: Any) -> str:
    parsed = parse_date(raw_date)
    return parsed.strftime("%Y-%m-%d") if parsed else clean_text(raw_date, 20)


def in_window(raw_date: Any) -> bool:
    parsed = parse_date(raw_date)
    if parsed is None:
        return True
    return parsed >= NOW - timedelta(days=WINDOW_DAYS)


def classify_dimension(title: str, content: str = "", fallback: str = "增长策略") -> str:
    text = f"{title} {content}".lower()
    scores = {}
    for dimension, keywords in DIMENSION_KEYWORDS.items():
        scores[dimension] = sum(1 for keyword in keywords if keyword.lower() in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else fallback


def is_social_noise(title: str, platform: str) -> bool:
    text = title or ""
    aliases = PLATFORM_ALIASES.get(platform, [platform])
    mentions_platform = any(alias.lower() in text.lower() for alias in aliases)
    if mentions_platform:
        return False
    return any(keyword in text for keyword in SOCIAL_NOISE_KEYWORDS)


def make_signal(
    *,
    platform: str,
    source: str,
    title: Any,
    query: str,
    date: Any = "",
    url: Any = "",
    author: Any = "",
    content: Any = "",
    dimension: str | None = None,
) -> dict[str, str]:
    clean_title = clean_text(title, 140)
    clean_content = clean_text(content, 300)
    return {
        "platform": platform,
        "dimension": dimension or classify_dimension(clean_title, clean_content),
        "title": clean_title,
        "date": normalize_date(date),
        "raw_date": clean_text(date, 40),
        "source": source,
        "source_label": CHANNEL_LABELS.get(source, source),
        "url": clean_text(url, 300),
        "author": clean_text(author, 80),
        "content": clean_content,
        "query": query,
    }


def build_queries(platform: str) -> list[tuple[str, str]]:
    month_label = f"{NOW.year}年{NOW.month}月"
    common = "增长策略 产品功能 运营动作 创作者激励 新功能 活动 最近14天"
    hints = PLATFORM_HINTS.get(platform, "")
    queries = [("综合", f"{platform} {hints} {common} {month_label}")]
    queries.extend(
        (dimension, f"{platform} {dimension} {' '.join(keywords[:5])} {month_label}")
        for dimension, keywords in DIMENSION_KEYWORDS.items()
    )
    return queries[: max(1, MAX_QUERIES_PER_PLATFORM)]


def parse_json_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("references", "organic", "result", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    nested = data.get("data")
    if isinstance(nested, dict):
        return parse_json_items(nested)
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    return []


def parse_exa_text(raw: str, platform: str, query: str, dimension: str | None = None) -> list[dict[str, str]]:
    results = []
    for entry in re.split(r"(?=Title:)", raw or ""):
        if not entry.strip():
            continue
        title = re.search(r"Title:\s*(.+?)(?:\n|$)", entry)
        url = re.search(r"URL:\s*(.+?)(?:\n|$)", entry)
        date = re.search(r"Published:\s*(.+?)(?:\n|$)", entry)
        highlights = re.search(
            r"Highlights:\s*(.+?)(?=(?:\n[A-Z][A-Za-z ]+:|\Z))",
            entry,
            re.DOTALL,
        )
        if title:
            results.append(
                make_signal(
                    platform=platform,
                    source="exa",
                    title=title.group(1),
                    date=date.group(1) if date else "",
                    url=url.group(1) if url else "",
                    content=highlights.group(1) if highlights else "",
                    query=query,
                    dimension=dimension,
                )
            )
    return results


def parse_minimax(raw: str, platform: str, query: str, dimension: str | None = None) -> list[dict[str, str]]:
    data = extract_json(raw)
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        inner = extract_json(data["text"])
        if inner is not None:
            data = inner
    results = []
    for item in parse_json_items(data):
        title = item.get("title") or item.get("name") or ""
        if not title:
            continue
        results.append(
            make_signal(
                platform=platform,
                source="minimax",
                title=title,
                date=item.get("date") or item.get("publishedDate") or "",
                url=item.get("link") or item.get("url") or "",
                content=item.get("snippet") or item.get("content") or "",
                query=query,
                dimension=dimension,
            )
        )
    return results


def parse_generic_search(
    raw: str,
    source: str,
    platform: str,
    query: str,
    dimension: str | None = None,
) -> list[dict[str, str]]:
    data = extract_json(raw)
    results = []
    for item in parse_json_items(data):
        title = item.get("title") or item.get("display_title") or item.get("text") or ""
        if not title:
            continue
        author = ""
        user = item.get("user")
        if isinstance(user, dict):
            author = user.get("screen_name") or user.get("nick_name") or ""
        results.append(
            make_signal(
                platform=platform,
                source=source,
                title=title,
                date=item.get("date") or item.get("created_at") or item.get("published") or "",
                url=item.get("url") or item.get("link") or "",
                author=author,
                content=item.get("content") or item.get("snippet") or item.get("text") or "",
                query=query,
                dimension=dimension,
            )
        )
    return results


def search_baidu_ai(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "baidu_ai"
    if channel_disabled(channel) or not BAIDU_API_KEY:
        mark_channel(channel, False, "disabled or missing BAIDU_API_KEY")
        return []
    try:
        import requests
    except ImportError:
        mark_channel(channel, False, "missing requests")
        return []

    body = {
        "instruction": (
            "你是竞品分析助手。只总结真实搜索结果，优先保留最近14天内的增长策略、"
            "产品功能、运营动作信号。"
        ),
        "messages": [{"role": "user", "content": query}],
    }
    headers = {
        "Authorization": f"Bearer {BAIDU_API_KEY}",
        "X-Appbuilder-From": "openclaw",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            "https://qianfan.baidubce.com/v2/ai_search/chat/completions",
            json=body,
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        mark_channel(channel, False, f"request failed: {exc}")
        return []
    if response.status_code == 429:
        mark_channel(channel, False, "quota exhausted: HTTP 429")
        return []
    if response.status_code != 200:
        mark_channel(channel, False, f"HTTP {response.status_code}")
        return []

    mark_channel(channel, True)
    results = parse_generic_search(response.text, channel, platform, query, dimension)
    return results[:count]


def search_baidu(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "baidu"
    if channel_disabled(channel) or not BAIDU_API_KEY:
        mark_channel(channel, False, "disabled or missing BAIDU_API_KEY")
        return []
    if not Path(BAIDU_SEARCH_SCRIPT).exists():
        mark_channel(channel, False, f"missing BAIDU_SEARCH_SCRIPT: {BAIDU_SEARCH_SCRIPT}")
        return []
    env = os.environ.copy()
    env["BAIDU_API_KEY"] = BAIDU_API_KEY
    raw = run_cmd(
        [
            sys.executable if Path(sys.executable).exists() else "python3",
            BAIDU_SEARCH_SCRIPT,
            json.dumps({"query": query, "count": count}, ensure_ascii=False),
        ],
        timeout=20,
        env=env,
    )
    mark_channel(channel, "[CMD ERROR]" not in raw)
    return parse_generic_search(raw, channel, platform, query, dimension)[:count]


def search_minimax(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "minimax"
    if channel_disabled(channel) or not command_available(MCPORTER):
        mark_channel(channel, False, "disabled or missing mcporter")
        return []
    raw = run_cmd(
        [MCPORTER, "call", "minimax.web_search", f"query={query}", f"numResults={count}"],
        timeout=15,
    )
    results = parse_minimax(raw, platform, query, dimension)
    mark_channel(channel, True, "no usable results" if not results else "")
    return results[:count]


def search_exa(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "exa"
    if channel_disabled(channel) or not command_available(MCPORTER):
        mark_channel(channel, False, "disabled or missing mcporter")
        return []
    raw = run_cmd(
        [MCPORTER, "call", "exa.web_search_exa", f"query={query}", f"numResults={count}"],
        timeout=20,
    )
    results = parse_exa_text(raw, platform, query, dimension)
    if not results:
        results = parse_generic_search(raw, channel, platform, query, dimension)
    mark_channel(channel, True, "no usable results" if not results else "")
    return results[:count]


def search_weibo(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "weibo"
    if channel_disabled(channel) or not command_available(MCPORTER):
        mark_channel(channel, False, "disabled or missing mcporter")
        return []
    raw = run_cmd(
        [MCPORTER, "call", "weibo.search_content", f"keyword={query}", f"limit={count}"],
        timeout=20,
    )
    mark_channel(channel, "[CMD ERROR]" not in raw)
    return parse_generic_search(raw, channel, platform, query, dimension)[:count]


def search_weibo_trending(platform: str, query: str, count: int = 10) -> list[dict[str, str]]:
    channel = "weibo_hot"
    if channel_disabled(channel) or not command_available(MCPORTER):
        mark_channel(channel, False, "disabled or missing mcporter")
        return []
    raw = run_cmd([MCPORTER, "call", "weibo.get_trendings", f"limit={count}"], timeout=20)
    data = extract_json(raw)
    results = []
    for item in parse_json_items(data):
        title = item.get("description") or item.get("word") or item.get("title") or ""
        if not title or is_social_noise(title, platform):
            continue
        if not any(alias.lower() in title.lower() for alias in PLATFORM_ALIASES.get(platform, [platform])):
            continue
        results.append(
            make_signal(
                platform=platform,
                source=channel,
                title=title,
                date=f"热搜{item.get('trending', '')}".strip(),
                content=item.get("desc") or "",
                query=query,
                dimension=classify_dimension(title, fallback="运营动作"),
            )
        )
    mark_channel(channel, True)
    return results


def search_xhs(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "xhs"
    if channel_disabled(channel) or not command_available(XHS_CLI):
        mark_channel(channel, False, "disabled or missing XHS_CLI")
        return []
    raw = run_cmd([XHS_CLI, "search", query], timeout=20)
    titles = re.findall(r"display_title:\s*(.+?)(?:\n|\r|$)", raw)
    authors = re.findall(r"nick_name:\s*(.+?)(?:\n|\r|$)", raw)
    dates = re.findall(
        r"text:\s*(\d+天前|\d+小时前|\d+分钟前|昨天 \d+:\d+|\d+:\d+)(?:\n|\r|$)",
        raw,
    )
    results = []
    for index, title in enumerate(titles[:count]):
        results.append(
            make_signal(
                platform=platform,
                source=channel,
                title=title,
                author=authors[index] if index < len(authors) else "",
                date=dates[index] if index < len(dates) else "",
                query=query,
                dimension=dimension,
            )
        )
    mark_channel(channel, True, "no usable results" if not results else "")
    return results


def search_wechat(platform: str, query: str, dimension: str | None = None, count: int = 5) -> list[dict[str, str]]:
    channel = "wechat"
    if channel_disabled(channel) or not command_available(AGENT_REACH_PYTHON):
        mark_channel(channel, False, "disabled or missing AGENT_REACH_PYTHON")
        return []
    code = """
import asyncio
import json
import re
import time
from miku_ai import get_wexin_article

async def main():
    rows = []
    for article in await get_wexin_article(%r, %d):
        url = article.get("url", "")
        match = re.search(r"timestamp=(\\d+)", url)
        date = ""
        if match:
            date = time.strftime("%%Y-%%m-%%d", time.localtime(int(match.group(1))))
        rows.append({"title": article.get("title", ""), "url": url, "date": date})
    print(json.dumps(rows, ensure_ascii=False))

asyncio.run(main())
""" % (query, count)
    raw = run_cmd([AGENT_REACH_PYTHON, "-c", code], timeout=20)
    results = parse_generic_search(raw, channel, platform, query, dimension)
    mark_channel(channel, True, "no usable results" if not results else "")
    return results[:count]


def dedupe_and_filter(platform: str, results: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    filtered = []
    for result in results:
        title = result.get("title", "")
        if not title or is_social_noise(title, platform):
            continue
        if not in_window(result.get("raw_date") or result.get("date")):
            continue
        key = re.sub(r"\s+", "", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        filtered.append(result)
    return filtered


def search_all_channels(platform: str) -> list[dict[str, str]]:
    log(f"  [{platform}] 启动扫描...")
    results: list[dict[str, str]] = []
    for dimension, query in build_queries(platform):
        dim = None if dimension == "综合" else dimension
        results.extend(search_baidu_ai(platform, query, dim, 3))
        results.extend(search_baidu(platform, query, dim, 5))
        results.extend(search_minimax(platform, query, dim, 5))
        results.extend(search_exa(platform, query, dim, 3))
        results.extend(search_weibo(platform, query, dim, 5))
        results.extend(search_xhs(platform, query, dim, 5))
        results.extend(search_wechat(platform, query, dim, 5))
        results.extend(search_weibo_trending(platform, query, 10))

    filtered = dedupe_and_filter(platform, results)
    log(f"  [{platform}] 原始 {len(results)} 条，保留 {len(filtered)} 条")
    return filtered


def build_text_summary(by_platform: dict[str, list[dict[str, str]]]) -> str:
    lines = [
        f"竞品动态扫描 · {DATE_TODAY}",
        f"时间窗口：{DATE_START} ～ {DATE_TODAY}（{WINDOW_DAYS}天）",
        "覆盖：" + "、".join(PLATFORM_ORDER),
        "渠道：" + " + ".join(CHANNEL_LABELS.values()),
        "",
    ]
    for platform in PLATFORM_ORDER:
        lines.append(f"【{platform}】")
        rows = by_platform.get(platform, [])
        if not rows:
            lines.append("  暂无有效信号")
            lines.append("")
            continue
        for dimension in DIMENSION_KEYWORDS:
            dim_rows = [row for row in rows if row.get("dimension") == dimension]
            lines.append(f"  ▶ {dimension}")
            if not dim_rows:
                lines.append("    暂无有效信号")
                continue
            for index, row in enumerate(dim_rows, 1):
                label = row.get("source_label") or row.get("source") or "未知来源"
                date = row.get("date") or row.get("raw_date") or "日期未知"
                extra = row.get("url") or row.get("author") or ""
                lines.append(f"    {index}. {row['title']}")
                lines.append(f"       [{date} · {label}] {extra}".rstrip())
                if row.get("content"):
                    lines.append(f"       {row['content'][:160]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    log(f"[竞品扫描] {DATE_TODAY} · window={WINDOW_DAYS}d · queries/platform={MAX_QUERIES_PER_PLATFORM}")
    by_platform = {}
    for platform in PLATFORM_ORDER:
        by_platform[platform] = search_all_channels(platform)

    raw_count = sum(status["calls"] for status in channel_status.values())
    effective_count = sum(len(rows) for rows in by_platform.values())
    text_report = build_text_summary(by_platform)

    payload = {
        "scan_time": datetime.now().isoformat(),
        "window": {"start": DATE_START, "end": DATE_TODAY, "days": WINDOW_DAYS},
        "platforms": PLATFORM_ORDER,
        "dimensions": list(DIMENSION_KEYWORDS.keys()),
        "raw_channel_calls": raw_count,
        "effective_signal_count": effective_count,
        "channels": channel_status,
        "by_platform": by_platform,
    }

    json_path = OUTPUT_DIR / "latest.json"
    text_path = OUTPUT_DIR / "latest_report.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(text_report, encoding="utf-8")

    log("")
    log("扫描完成")
    log(f"  结构化数据: {json_path}")
    log(f"  原始报告: {text_path}")
    log(f"  有效信号: {effective_count}")
    log("")
    print(text_report)


if __name__ == "__main__":
    main()
