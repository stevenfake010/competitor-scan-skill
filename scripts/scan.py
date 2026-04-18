#!/usr/bin/env python3
"""
Analyst-grade competitor signal scanner.

This scanner collects recent competitive-intelligence signals from several
search/social channels, normalizes them, scores their credibility and business
relevance, and writes both a structured JSON payload and a business-ready text
brief for leadership review.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


WINDOW_DAYS = int(os.environ.get("COMPETITOR_SCAN_WINDOW_DAYS", "14"))
MAX_QUERIES_PER_PLATFORM = int(
    os.environ.get("COMPETITOR_SCAN_MAX_QUERIES_PER_PLATFORM", "1")
)
MIN_SIGNAL_SCORE = int(os.environ.get("COMPETITOR_SCAN_MIN_SIGNAL_SCORE", "48"))
TOP_PRIORITY_SIGNAL_LIMIT = int(
    os.environ.get("COMPETITOR_SCAN_TOP_PRIORITY_SIGNAL_LIMIT", "6")
)
REPORT_AUDIENCE = os.environ.get("COMPETITOR_SCAN_REPORT_AUDIENCE", "业务负责人").strip() or "业务负责人"
OUTPUT_DIR = Path(
    os.environ.get(
        "COMPETITOR_SCAN_OUTPUT_DIR",
        str(Path(tempfile.gettempdir()) / "competitor_scan"),
    )
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime.now()
DATE_TODAY = NOW.strftime("%Y-%m-%d")
DATE_START = (NOW - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

BAIDU_API_KEY = os.environ.get("BAIDU_API_KEY", "").strip()
BAIDU_AI_SEARCH_API_KEY = os.environ.get(
    "BAIDU_AI_SEARCH_API_KEY", BAIDU_API_KEY
).strip()
BAIDU_SEARCH_SCRIPT = os.environ.get("BAIDU_SEARCH_SCRIPT", "").strip()
AGENT_REACH = os.environ.get("AGENT_REACH") or shutil.which("agent-reach") or "agent-reach"
AGENT_REACH_BIN = os.environ.get("AGENT_REACH_BIN", "").strip()
AGENT_REACH_PYTHON = os.environ.get("AGENT_REACH_PYTHON", "").strip()
MCPORTER = os.environ.get("MCPORTER") or shutil.which("mcporter") or "mcporter"
_xhs_default = shutil.which("xhs")
if not _xhs_default and AGENT_REACH_BIN:
    xhs_name = "xhs.exe" if os.name == "nt" else "xhs"
    _xhs_default = str(Path(AGENT_REACH_BIN) / xhs_name)
XHS_CLI = os.environ.get("XHS_CLI", _xhs_default or "xhs")
XHS_COOKIE_SOURCE = os.environ.get("XHS_COOKIE_SOURCE", "auto").strip() or "auto"
XHS_COOKIE_HEADER = os.environ.get("XHS_COOKIE_HEADER", "").strip()
XHS_COOKIE_JSON = os.environ.get("XHS_COOKIE_JSON", "").strip()
XHS_RUNTIME_HOME = os.environ.get("XHS_RUNTIME_HOME", "").strip()
XHS_AUTO_LOGIN = os.environ.get("XHS_AUTO_LOGIN", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
MINIMAX_API_KEY = (
    os.environ.get("MINIMAX_API_KEY")
    or os.environ.get("MINIMAX_CODE_PLAN_KEY")
    or os.environ.get("MINIMAX_CODING_API_KEY")
    or ""
).strip()
MINIMAX_SEARCH_ENDPOINT = os.environ.get(
    "MINIMAX_SEARCH_ENDPOINT", "https://api.minimax.io/v1/coding_plan/search"
).strip()
MINIMAX_AUTH_MODE = os.environ.get("MINIMAX_AUTH_MODE", "bearer").strip().lower()
DISABLED_CHANNELS = {
    c.strip()
    for c in os.environ.get("COMPETITOR_SCAN_DISABLE_CHANNELS", "").split(",")
    if c.strip()
}

DIMENSION_KEYWORDS = {
    "增长策略": [
        "增长",
        "拉新",
        "新用户",
        "补贴",
        "邀请",
        "奖励",
        "创作者激励",
        "流量扶持",
        "分成",
        "站外播放",
        "达人",
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
        "视频生成",
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
        "招商",
        "扶持计划",
    ],
}

ACTION_TYPE_RULES = {
    "创作者激励": [
        "创作者激励",
        "扶持计划",
        "流量扶持",
        "激励计划",
        "现金奖励",
        "补贴",
        "奖金",
        "投稿",
        "征稿",
    ],
    "分发/流量机制": [
        "推荐",
        "搜索",
        "流量",
        "站外播放",
        "分发",
        "曝光",
        "入口",
        "算法",
        "作者榜",
    ],
    "商业化/变现": [
        "分成",
        "广告",
        "带货",
        "招商",
        "流量主",
        "电商",
        "变现",
        "广告分成",
    ],
    "AI能力": [
        "AI",
        "模型",
        "智能体",
        "视频生成",
        "图文生成",
        "可灵",
        "豆包",
        "大模型",
    ],
    "运营活动": [
        "活动",
        "话题",
        "挑战赛",
        "节",
        "打卡",
        "赛事",
        "直播",
    ],
}

GLOBAL_STRATEGIC_KEYWORDS = sorted(
    {
        keyword
        for keywords in DIMENSION_KEYWORDS.values()
        for keyword in keywords
    }
    | {
        "创作者",
        "作者",
        "达人",
        "UP主",
        "权益",
        "短剧",
        "内容供给",
        "商业化",
        "智能体",
        "中长视频",
        "电商",
    }
)

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
    "交通事故",
    "明星同款",
    "吃瓜",
]

MAINSTREAM_DOMAINS = [
    "36kr.com",
    "sohu.com",
    "qq.com",
    "163.com",
    "ifeng.com",
    "jiemian.com",
    "thepaper.cn",
    "donews.com",
    "chinaz.com",
    "zol.com.cn",
    "finance.sina.com.cn",
    "news.sina.com.cn",
    "baike.baidu.com",
    "zhihu.com",
    "mp.weixin.qq.com",
]

LOW_CREDIBILITY_DOMAINS = [
    "80tg.com",
    "11467.com",
    "bypdw.com",
    "egvsh.cn",
    "jxwddz.com",
]

PLATFORM_CONFIG = {
    "抖音": {
        "aliases": ["抖音", "douyin", "字节跳动"],
        "official_domains": [
            "douyin.com",
            "iesdouyin.com",
            "oceanengine.com",
            "jinritemai.com",
            "bytedance.com",
        ],
        "focus_keywords": [
            "创作者激励",
            "流量扶持",
            "站外播放",
            "短剧",
            "电商",
            "广告分成",
            "直播",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 创作者激励 流量扶持 站外播放 补贴 分成 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 推荐 搜索 算法 新功能 AI 入口 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 短剧 扶持计划 招商 活动 直播 最近14天 {month_label}",
            },
        ],
    },
    "抖音精选": {
        "aliases": ["抖音精选", "青桃", "中长视频"],
        "official_domains": [
            "douyin.com",
            "bytedance.com",
            "sina.com.cn",
        ],
        "focus_keywords": [
            "中长视频",
            "作者榜",
            "引流",
            "增长",
            "内容风向",
            "新入口",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 中长视频 作者榜 增长 引流 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 新功能 分发 推荐 入口 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 活动 创作者 运营 最近14天 {month_label}",
            },
        ],
    },
    "快手": {
        "aliases": ["快手", "可灵", "kwai"],
        "official_domains": [
            "kuaishou.com",
            "kwai.com",
            "klingai.com",
            "kuaishou.cn",
        ],
        "focus_keywords": [
            "AI灵境计划",
            "可灵",
            "创作者扶持",
            "现金激励",
            "流量扶持",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 创作者扶持 流量扶持 补贴 现金激励 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 可灵 AI 新功能 视频生成 工具 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} AI灵境计划 活动 扶持计划 最近14天 {month_label}",
            },
        ],
    },
    "微信视频号": {
        "aliases": ["微信视频号", "视频号", "weixin"],
        "official_domains": [
            "weixin.qq.com",
            "support.weixin.qq.com",
            "qq.com",
            "mp.weixin.qq.com",
        ],
        "focus_keywords": [
            "创作者权益",
            "流量主",
            "带货短视频",
            "直播",
            "商品分享",
            "分成",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 创作者权益 流量主 分成 增长 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 新功能 入口 推荐 搜索 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 带货短视频 直播 运营 规则 最近14天 {month_label}",
            },
        ],
    },
    "B站": {
        "aliases": ["B站", "哔哩哔哩", "bilibili"],
        "official_domains": ["bilibili.com", "b23.tv"],
        "focus_keywords": [
            "创作者激励",
            "UP主",
            "暂停广告",
            "商业化",
            "播放页",
            "增长",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 创作者激励 UP主 扶持 增长 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 新功能 暂停广告 播放页 推荐 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 活动 征稿 运营 最近14天 {month_label}",
            },
        ],
    },
    "微博": {
        "aliases": ["微博", "weibo", "新浪微博"],
        "official_domains": ["weibo.com", "m.weibo.cn", "sina.com.cn"],
        "focus_keywords": [
            "创作活力分",
            "金V",
            "流量扶持",
            "内容标准",
            "热搜",
            "作者生态",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 创作者激励 流量扶持 创作活力 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} 创作活力分 内容标准 金V 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 活动 热点 运营 扶持 最近14天 {month_label}",
            },
        ],
    },
    "豆包": {
        "aliases": ["豆包", "doubao", "字节跳动AI"],
        "official_domains": ["doubao.com", "bytedance.com", "volcengine.com"],
        "focus_keywords": [
            "AI助手",
            "电商",
            "智能体",
            "视频生成",
            "产品能力",
            "流量",
        ],
        "queries": [
            {
                "dimension": "增长策略",
                "query": "{platform} 增长 用户 运营 策略 最近14天 {month_label}",
            },
            {
                "dimension": "产品功能",
                "query": "{platform} AI 新功能 智能体 视频生成 电商 最近14天 {month_label}",
            },
            {
                "dimension": "运营动作",
                "query": "{platform} 活动 运营 推广 最近14天 {month_label}",
            },
        ],
    },
}

PLATFORM_ORDER = list(PLATFORM_CONFIG.keys())
PLATFORM_ALIASES = {
    platform: config["aliases"] for platform, config in PLATFORM_CONFIG.items()
}
PLATFORM_HINTS = {
    platform: " ".join(config["focus_keywords"])
    for platform, config in PLATFORM_CONFIG.items()
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


channel_status: dict[str, dict[str, Any]] = {}
_xhs_login_attempted = False
_xhs_runtime_env: dict[str, str] | None = None
_xhs_runtime_detail = ""
_xhs_runtime_home: Path | None = None


def log(message: str) -> None:
    print(message, flush=True)


def command_available(command: str) -> bool:
    if not command:
        return False
    if os.path.isabs(command):
        return Path(command).exists()
    return shutil.which(command) is not None


def mcporter_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def format_mcporter_call(tool: str, params: dict[str, Any]) -> str:
    args = ", ".join(f"{key}: {mcporter_literal(value)}" for key, value in params.items())
    return f"{tool}({args})"


def collapse_details(details: list[str]) -> list[str]:
    seen = set()
    collapsed = []
    for detail in details:
        if not detail or detail in seen:
            continue
        seen.add(detail)
        collapsed.append(detail)
    return collapsed


def mark_channel(channel: str, ok: bool, detail: str = "") -> None:
    current = channel_status.setdefault(
        channel,
        {
            "ok": True,
            "calls": 0,
            "skipped": 0,
            "successes": 0,
            "details": [],
        },
    )
    current["calls"] += 1
    if ok:
        current["successes"] += 1
    else:
        current["ok"] = False
        current["skipped"] += 1
    if detail:
        current["details"].append(detail)
        current["details"] = collapse_details(current["details"])


def run_cmd(
    args: list[str],
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env or os.environ.copy(),
            check=False,
        )
        return result.stdout + (result.stderr if result.returncode else "")
    except Exception as exc:
        return f"[CMD ERROR] {exc}"


def parse_cookie_header(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for chunk in raw.split(";"):
        item = chunk.strip()
        if not item:
            continue
        name, sep, value = item.partition("=")
        if not sep:
            continue
        name = name.strip()
        value = value.strip()
        if name and value:
            cookies[name] = value
    return cookies


def parse_xhs_cookie_payload(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}

    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return {
                str(key): str(value)
                for key, value in data.items()
                if str(key).strip() and str(value).strip()
            }
        if isinstance(data, list):
            cookies: dict[str, str] = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                value = str(item.get("value", "")).strip()
                if name and value:
                    cookies[name] = value
            return cookies

    return parse_cookie_header(text)


def write_xhs_cookie_store(runtime_home: Path, cookies: dict[str, str]) -> Path:
    config_dir = runtime_home / ".xiaohongshu-cli"
    config_dir.mkdir(parents=True, exist_ok=True)
    cookie_path = config_dir / "cookies.json"
    payload = {**cookies, "saved_at": NOW.timestamp()}
    cookie_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        cookie_path.chmod(0o600)
    except OSError:
        pass
    return cookie_path


def cleanup_xhs_runtime_home() -> None:
    if _xhs_runtime_home and not XHS_RUNTIME_HOME:
        shutil.rmtree(_xhs_runtime_home, ignore_errors=True)


def get_xhs_cmd_env() -> tuple[dict[str, str], str, str]:
    global _xhs_runtime_env, _xhs_runtime_detail, _xhs_runtime_home

    if _xhs_runtime_env is not None:
        return _xhs_runtime_env.copy(), _xhs_runtime_detail, ""

    env = os.environ.copy()
    runtime_home = XHS_RUNTIME_HOME.strip()
    runtime_path: Path | None = None
    source_detail = ""
    setup_error = ""

    if runtime_home:
        runtime_path = Path(runtime_home)
        runtime_path.mkdir(parents=True, exist_ok=True)
        source_detail = "configured XHS runtime home"

    raw_cookie_payload = XHS_COOKIE_JSON or XHS_COOKIE_HEADER
    if raw_cookie_payload:
        cookies = parse_xhs_cookie_payload(raw_cookie_payload)
        if cookies.get("a1"):
            if runtime_path is None:
                runtime_path = Path(tempfile.mkdtemp(prefix="competitor_scan_xhs_"))
                _xhs_runtime_home = runtime_path
                atexit.register(cleanup_xhs_runtime_home)
            write_xhs_cookie_store(runtime_path, cookies)
            source_detail = (
                "provided cookie header"
                if XHS_COOKIE_HEADER
                else "provided cookie payload"
            )
        else:
            setup_error = "provided xiaohongshu cookie payload missing a1"

    if runtime_path is not None:
        env["USERPROFILE"] = str(runtime_path)
        env["HOME"] = str(runtime_path)
        _xhs_runtime_home = runtime_path

    _xhs_runtime_env = env.copy()
    _xhs_runtime_detail = source_detail
    return env, source_detail, setup_error


def mcporter_call(tool: str, params: dict[str, Any], timeout: int = 20) -> str:
    call = format_mcporter_call(tool, params)
    raw = run_cmd([MCPORTER, "call", call], timeout=timeout)
    lowered = raw.lower()
    likely_error = any(
        marker in lowered
        for marker in (
            "unknown command",
            "invalid",
            "usage:",
            "not configured",
            "no such",
            "unable to load tool metadata",
            "connection closed",
            "mcp error",
        )
    )
    if raw.strip() and "[CMD ERROR]" not in raw and not likely_error:
        return raw

    legacy_args = [MCPORTER, "call", tool]
    legacy_args.extend(f"{key}={value}" for key, value in params.items())
    fallback = run_cmd(legacy_args, timeout=timeout)
    return fallback if fallback.strip() else raw


def resolve_agent_reach_python() -> str:
    configured = os.environ.get("AGENT_REACH_PYTHON", "").strip() or AGENT_REACH_PYTHON
    xhs_python_candidates: list[str] = []
    xhs_path = Path(XHS_CLI)
    if xhs_path.suffix.lower() == ".exe":
        xhs_python_candidates.append(str(xhs_path.parents[1] / "python.exe"))
    elif xhs_path.name:
        xhs_python_candidates.append(str(xhs_path.with_name("python3")))
    candidates = [configured, *xhs_python_candidates, sys.executable, "python3", "python", "py"]
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen or not command_available(candidate):
            continue
        seen.add(candidate)
        probe = run_cmd(
            [candidate, "-c", "import agent_reach, sys; print(sys.executable)"],
            timeout=8,
        )
        lowered = probe.lower()
        if "traceback" in lowered or "modulenotfounderror" in lowered:
            continue
        path = probe.strip().splitlines()[-1] if probe.strip() else ""
        if path:
            return path
    return ""


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

    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=None)
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


def channel_disabled(channel: str) -> bool:
    return channel in DISABLED_CHANNELS


def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    return parsed.netloc.lower().lstrip("www.")


def domain_matches(domain: str, patterns: list[str]) -> bool:
    domain = domain.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if domain == pattern or domain.endswith(f".{pattern}"):
            return True
    return False


def parse_json_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("references", "organic", "result", "items", "notes"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    nested = data.get("data")
    if isinstance(nested, dict):
        return parse_json_items(nested)
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    return []


def dictify_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return {}


def classify_dimension(title: str, content: str = "", fallback: str = "增长策略") -> str:
    text = f"{title} {content}".lower()
    scores = {}
    for dimension, keywords in DIMENSION_KEYWORDS.items():
        scores[dimension] = sum(1 for keyword in keywords if keyword.lower() in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else fallback


def infer_action_type(title: str, content: str = "", dimension: str = "增长策略") -> str:
    text = f"{title} {content}".lower()
    scores = {}
    for action_type, keywords in ACTION_TYPE_RULES.items():
        scores[action_type] = sum(1 for keyword in keywords if keyword.lower() in text)
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    if dimension == "增长策略":
        return "创作者激励"
    if dimension == "产品功能":
        return "产品/能力升级"
    return "运营活动"


def is_social_noise(title: str, platform: str) -> bool:
    text = title or ""
    aliases = PLATFORM_ALIASES.get(platform, [platform])
    mentions_platform = any(alias.lower() in text.lower() for alias in aliases)
    if mentions_platform:
        return False
    return any(keyword in text for keyword in SOCIAL_NOISE_KEYWORDS)


def summarize_text(value: str, limit: int = 110) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_queries(platform: str) -> list[tuple[str, str]]:
    month_label = f"{NOW.year}年{NOW.month}月"
    plans = PLATFORM_CONFIG.get(platform, {}).get("queries", [])
    if not plans:
        hint = PLATFORM_HINTS.get(platform, "")
        return [("增长策略", f"{platform} {hint} 用户增长 创作者激励 最近14天 {month_label}")]
    queries = []
    for plan in plans[: max(1, MAX_QUERIES_PER_PLATFORM)]:
        queries.append((plan["dimension"], plan["query"].format(platform=platform, month_label=month_label)))
    return queries


def matched_aliases(platform: str, text: str) -> list[str]:
    lowered = text.lower()
    return [
        alias
        for alias in PLATFORM_ALIASES.get(platform, [])
        if alias and alias.lower() in lowered
    ]


def matched_keywords(signal: dict[str, Any]) -> list[str]:
    platform = signal["platform"]
    lowered = " ".join(
        [
            signal.get("title", ""),
            signal.get("content", ""),
            signal.get("author", ""),
            signal.get("url", ""),
        ]
    ).lower()
    candidates = GLOBAL_STRATEGIC_KEYWORDS + PLATFORM_CONFIG.get(platform, {}).get(
        "focus_keywords", []
    )
    hits = []
    for keyword in candidates:
        if keyword and keyword.lower() in lowered and keyword not in hits:
            hits.append(keyword)
    return hits


def source_tier(signal: dict[str, Any]) -> tuple[str, int]:
    domain = signal.get("domain", "")
    platform = signal["platform"]
    if domain_matches(domain, PLATFORM_CONFIG.get(platform, {}).get("official_domains", [])):
        return "官方/平台内", 95
    if domain_matches(domain, MAINSTREAM_DOMAINS):
        return "主流媒体", 80
    if domain == "mp.weixin.qq.com":
        return "公众号文章", 72
    if signal.get("source") == "weibo_hot":
        return "平台热榜", 68
    if domain_matches(domain, LOW_CREDIBILITY_DOMAINS):
        return "低可信站点", 32
    if domain:
        return "普通站点", 48
    return "未知来源", 40


def credibility_label(score: int) -> str:
    if score >= 80:
        return "高可信"
    if score >= 60:
        return "中可信"
    return "低可信"


def priority_label(score: int, credibility: int) -> str:
    if score >= 82 and credibility >= 70:
        return "P1"
    if score >= 66:
        return "P2"
    return "P3"


def strategic_implication(action_type: str) -> str:
    if action_type == "创作者激励":
        return "建议跟踪供给侧争夺强度、作者迁移风险和激励门槛变化，评估是否影响小红书内容供给成本。"
    if action_type == "分发/流量机制":
        return "建议关注分发入口和流量规则变化，评估是否会改变用户停留与内容消费心智。"
    if action_type == "商业化/变现":
        return "建议评估该动作对创作者留存和商业化预期的提升幅度，判断是否会抬高我方作者经营压力。"
    if action_type == "AI能力":
        return "建议评估其对创作提效与内容供给规模的拉动，识别我方是否需要补齐同类 AI 能力。"
    return "建议结合内容供给、流量效率和商业化承接，判断该动作对小红书的竞争压力。"


def analyst_judgement(signal: dict[str, Any]) -> str:
    platform = signal["platform"]
    action_type = signal["action_type"]
    keyword_text = "、".join(signal.get("matched_keywords", [])[:3])
    if action_type == "创作者激励":
        core = f"{platform}在通过激励/扶持动作争夺供给侧作者与内容资源。"
    elif action_type == "分发/流量机制":
        core = f"{platform}在调分发和流量机制，重点提升内容曝光与消费效率。"
    elif action_type == "商业化/变现":
        core = f"{platform}在强化作者变现链路，目标是提高供给留存和商业化预期。"
    elif action_type == "AI能力":
        core = f"{platform}在用 AI 能力强化创作效率或新场景转化。"
    else:
        core = f"{platform}在以运营动作放大内容供给和用户活跃。"
    if keyword_text:
        return f"{core}本次证据重点落在 {keyword_text}。"
    return core


def relevance_score(signal: dict[str, Any]) -> int:
    text = " ".join(
        [
            signal.get("title", ""),
            signal.get("content", ""),
            signal.get("author", ""),
            signal.get("url", ""),
        ]
    )
    aliases = matched_aliases(signal["platform"], text)
    keywords = matched_keywords(signal)
    dimension_hits = sum(
        1
        for keyword in DIMENSION_KEYWORDS.get(signal["dimension"], [])
        if keyword.lower() in text.lower()
    )
    official_bonus = 16 if signal.get("source_tier") == "官方/平台内" else 0
    roundup_bonus = 10 if len(aliases) >= 2 else 0
    score = (
        len(set(aliases)) * 20
        + len(keywords[:6]) * 6
        + dimension_hits * 5
        + official_bonus
        + roundup_bonus
    )
    if not aliases and signal.get("source_tier") not in {"官方/平台内", "公众号文章"}:
        score -= 18
    if signal.get("source_tier") == "低可信站点":
        score -= 12
    if any(noise in text for noise in SOCIAL_NOISE_KEYWORDS):
        score -= 40
    return max(0, min(100, score))


def total_signal_score(credibility: int, relevance: int, action_type: str) -> int:
    score = round(credibility * 0.42 + relevance * 0.58)
    if action_type in {"创作者激励", "分发/流量机制", "商业化/变现"}:
        score += 4
    return max(0, min(100, score))


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
) -> dict[str, Any]:
    clean_title = clean_text(title, 140)
    clean_content = clean_text(content, 320)
    signal: dict[str, Any] = {
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
        "domain": get_domain(clean_text(url, 300)),
    }
    signal["action_type"] = infer_action_type(
        signal["title"], signal["content"], signal["dimension"]
    )
    signal["matched_aliases"] = matched_aliases(
        platform,
        " ".join([signal["title"], signal["content"], signal["author"], signal["url"]]),
    )
    signal["matched_keywords"] = matched_keywords(signal)
    signal["source_tier"], signal["credibility_score"] = source_tier(signal)
    signal["relevance_score"] = relevance_score(signal)
    signal["total_score"] = total_signal_score(
        signal["credibility_score"],
        signal["relevance_score"],
        signal["action_type"],
    )
    signal["priority"] = priority_label(
        signal["total_score"], signal["credibility_score"]
    )
    signal["credibility_label"] = credibility_label(signal["credibility_score"])
    signal["judgement"] = analyst_judgement(signal)
    signal["implication"] = strategic_implication(signal["action_type"])
    signal["evidence_summary"] = summarize_text(signal["content"] or signal["title"], 120)
    return signal


def parse_exa_text(
    raw: str,
    platform: str,
    query: str,
    dimension: str | None = None,
) -> list[dict[str, Any]]:
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


def parse_minimax(
    raw: str,
    platform: str,
    query: str,
    dimension: str | None = None,
) -> list[dict[str, Any]]:
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
) -> list[dict[str, Any]]:
    data = extract_json(raw)
    results = []
    for item in parse_json_items(data):
        title = (
            item.get("title")
            or item.get("display_title")
            or item.get("name")
            or item.get("desc")
            or item.get("text")
            or item.get("word")
            or ""
        )
        if not title:
            continue
        author = ""
        user = item.get("user")
        if isinstance(user, dict):
            author = (
                user.get("screen_name")
                or user.get("nick_name")
                or user.get("nickname")
                or ""
            )
        author_obj = item.get("author")
        if not author and isinstance(author_obj, dict):
            author = author_obj.get("name") or author_obj.get("nickname") or ""
        note_id = item.get("note_id") or item.get("feed_id") or item.get("id") or ""
        url = item.get("url") or item.get("link") or item.get("note_url") or ""
        if not url and source == "xhs" and note_id:
            url = f"https://www.xiaohongshu.com/explore/{note_id}"
        results.append(
            make_signal(
                platform=platform,
                source=source,
                title=title,
                date=(
                    item.get("date")
                    or item.get("created_at")
                    or item.get("published")
                    or item.get("publishedDate")
                    or item.get("time")
                    or ""
                ),
                url=url,
                author=author or item.get("nickname") or "",
                content=(
                    item.get("content")
                    or item.get("snippet")
                    or item.get("desc")
                    or item.get("text")
                    or item.get("description")
                    or ""
                ),
                query=query,
                dimension=dimension,
            )
        )
    return results


def parse_xhs_status(raw: str) -> tuple[bool, str]:
    data = extract_json(raw)
    if isinstance(data, dict):
        if data.get("ok") is True:
            return True, "authenticated"
        message = clean_text(data.get("message") or data.get("error") or "", 120)
        if message:
            return False, message
    lowered = raw.lower()
    if "not_authenticated" in lowered or "no 'a1' cookie" in lowered:
        return False, "xiaohongshu login cookie required"
    return False, "xiaohongshu status unknown"


def ensure_xhs_login() -> tuple[bool, str]:
    global _xhs_login_attempted
    if not command_available(XHS_CLI):
        return False, "missing XHS_CLI"

    xhs_env, source_detail, setup_error = get_xhs_cmd_env()
    status_raw = run_cmd([XHS_CLI, "status", "--json"], timeout=15, env=xhs_env)
    ok, detail = parse_xhs_status(status_raw)
    if ok:
        if source_detail == "provided cookie header":
            return True, "authenticated via provided cookie header"
        if source_detail == "provided cookie payload":
            return True, "authenticated via provided cookie payload"
        if source_detail == "configured XHS runtime home":
            return True, "authenticated via configured XHS runtime home"
        return True, "authenticated"

    if _xhs_login_attempted or not XHS_AUTO_LOGIN:
        if setup_error:
            return False, setup_error
        return False, detail

    _xhs_login_attempted = True
    login_raw = run_cmd(
        [XHS_CLI, "login", "--cookie-source", XHS_COOKIE_SOURCE, "--json"],
        timeout=60,
        env=xhs_env,
    )
    status_raw = run_cmd([XHS_CLI, "status", "--json"], timeout=15, env=xhs_env)
    ok, detail = parse_xhs_status(status_raw)
    if ok:
        if source_detail == "provided cookie header":
            return True, "authenticated via provided cookie header"
        if source_detail == "provided cookie payload":
            return True, "authenticated via provided cookie payload"
        return True, "authenticated via browser cookies"
    login_detail = clean_text(login_raw, 140)
    if login_detail:
        return False, login_detail
    if setup_error:
        return False, setup_error
    return False, detail


def call_minimax_direct(query: str, count: int = 5) -> tuple[int, str]:
    if not MINIMAX_API_KEY:
        return 0, ""

    headers = {"Content-Type": "application/json"}
    if MINIMAX_AUTH_MODE == "raw":
        headers["Authorization"] = MINIMAX_API_KEY
    else:
        headers["Authorization"] = f"Bearer {MINIMAX_API_KEY}"

    body = {"query": query, "count": count}
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        MINIMAX_SEARCH_ENDPOINT,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"[CMD ERROR] {exc}"


def search_weibo_package(
    tool: str,
    query: str | None = None,
    count: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    logging.getLogger("mcp_server_weibo").setLevel(logging.CRITICAL)
    logging.getLogger("mcp_server_weibo.weibo").setLevel(logging.CRITICAL)
    try:
        import asyncio
        from mcp_server_weibo.weibo import WeiboCrawler
    except Exception as exc:
        return [], f"mcp_server_weibo unavailable: {exc}"

    async def run_search() -> list[dict[str, Any]]:
        crawler = WeiboCrawler()
        if tool == "trendings":
            rows = await crawler.get_trendings(count)
        else:
            rows = await crawler.search_content(query or "", count)
        return [dictify_item(row) for row in rows]

    try:
        return asyncio.run(run_search()), ""
    except Exception as exc:
        return [], f"mcp_server_weibo direct failed: {exc}"


def search_baidu_ai(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "baidu_ai"
    if channel_disabled(channel) or not BAIDU_AI_SEARCH_API_KEY:
        mark_channel(channel, False, "disabled or missing BAIDU_AI_SEARCH_API_KEY")
        return []

    body = {
        "instruction": (
            "你是竞品用户增长分析助手。只保留最近14天内与用户增长、创作者激励、"
            "分发机制、产品能力、商业化或运营动作直接相关的真实搜索结果。"
        ),
        "messages": [{"role": "user", "content": query}],
    }
    headers = {
        "Authorization": f"Bearer {BAIDU_AI_SEARCH_API_KEY}",
        "X-Appbuilder-From": "openclaw",
        "Content-Type": "application/json",
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://qianfan.baidubce.com/v2/ai_search/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status_code = response.status
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        mark_channel(channel, False, f"request failed: {exc}")
        return []

    if status_code == 429:
        mark_channel(channel, False, "quota exhausted: HTTP 429")
        return []
    if status_code != 200:
        mark_channel(channel, False, f"HTTP {status_code}")
        return []

    mark_channel(channel, True)
    return parse_generic_search(raw, channel, platform, query, dimension)[:count]


def search_baidu(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
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
    if "[CMD ERROR]" in raw:
        mark_channel(channel, False, raw)
        return []
    mark_channel(channel, True)
    return parse_generic_search(raw, channel, platform, query, dimension)[:count]


def search_minimax(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "minimax"
    if channel_disabled(channel):
        mark_channel(channel, False, "disabled")
        return []

    raw = ""
    if command_available(MCPORTER):
        raw = mcporter_call("minimax.web_search", {"query": query, "numResults": count}, timeout=15)
    results = parse_minimax(raw, platform, query, dimension)
    if not results:
        results = parse_generic_search(raw, channel, platform, query, dimension)
    if results:
        mark_channel(channel, True)
        return results[:count]

    if MINIMAX_API_KEY:
        status_code, direct_raw = call_minimax_direct(query, count)
        direct_results = parse_minimax(direct_raw, platform, query, dimension)
        if not direct_results:
            direct_results = parse_generic_search(direct_raw, channel, platform, query, dimension)
        if direct_results:
            mark_channel(channel, True, "used MiniMax direct API")
            return direct_results[:count]
        detail = f"MiniMax direct HTTP {status_code}"
        data = extract_json(direct_raw)
        if isinstance(data, dict):
            base_resp = data.get("base_resp")
            if isinstance(base_resp, dict):
                detail = clean_text(base_resp.get("status_msg") or detail, 120)
        mark_channel(channel, False, detail)
        return []

    detail = "missing mcporter minimax bridge and MINIMAX_API_KEY"
    if command_available(MCPORTER):
        detail = "mcporter minimax bridge unavailable"
    mark_channel(channel, False, detail)
    return []


def search_exa(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "exa"
    if channel_disabled(channel) or not command_available(MCPORTER):
        mark_channel(channel, False, "disabled or missing mcporter")
        return []
    raw = mcporter_call("exa.web_search_exa", {"query": query, "numResults": count}, timeout=20)
    results = parse_exa_text(raw, platform, query, dimension)
    if not results:
        results = parse_generic_search(raw, channel, platform, query, dimension)
    mark_channel(channel, True, "no usable results" if not results else "")
    return results[:count]


def search_weibo(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "weibo"
    if channel_disabled(channel):
        mark_channel(channel, False, "disabled")
        return []

    if command_available(MCPORTER):
        raw = mcporter_call("weibo.search_content", {"keyword": query, "limit": count}, timeout=20)
        results = parse_generic_search(raw, channel, platform, query, dimension)[:count]
        if results:
            mark_channel(channel, True)
            return results

    rows, detail = search_weibo_package("content", query, count)
    results = []
    for item in rows:
        user = item.get("user")
        author = user.get("screen_name", "") if isinstance(user, dict) else ""
        title = item.get("raw_text") or item.get("text") or ""
        if not title:
            continue
        results.append(
            make_signal(
                platform=platform,
                source=channel,
                title=title,
                date=item.get("created_at") or "",
                url=f"https://m.weibo.cn/status/{item.get('id', '')}" if item.get("id") else "",
                author=author,
                content=item.get("text") or "",
                query=query,
                dimension=dimension,
            )
        )
    if results:
        mark_channel(channel, True, "used direct mcp_server_weibo package")
        return results[:count]
    mark_channel(channel, True, detail or "no usable results")
    return []


def search_weibo_trending(
    platform: str,
    query: str,
    count: int = 10,
) -> list[dict[str, Any]]:
    channel = "weibo_hot"
    if channel_disabled(channel):
        mark_channel(channel, False, "disabled")
        return []

    items: list[dict[str, Any]] = []
    detail = ""
    if command_available(MCPORTER):
        raw = mcporter_call("weibo.get_trendings", {"limit": count}, timeout=20)
        items = parse_json_items(extract_json(raw))
    if not items:
        items, detail = search_weibo_package("trendings", count=count)

    results = []
    for item in items:
        title = item.get("description") or item.get("word") or item.get("title") or ""
        if not title or is_social_noise(title, platform):
            continue
        if not matched_aliases(platform, title):
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
    mark_channel(channel, True if items else False, detail or ("no matching trendings" if not results else ""))
    return results


def search_xhs(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "xhs"
    if channel_disabled(channel):
        mark_channel(channel, False, "disabled")
        return []

    if command_available(MCPORTER):
        raw = mcporter_call("xiaohongshu.search_feeds", {"keyword": query}, timeout=20)
        results = parse_generic_search(raw, channel, platform, query, dimension)[:count]
        if results:
            mark_channel(channel, True)
            return results

    if not command_available(XHS_CLI):
        mark_channel(channel, False, "missing mcporter xiaohongshu bridge or XHS_CLI")
        return []

    ok, detail = ensure_xhs_login()
    if not ok:
        mark_channel(channel, False, detail or "xiaohongshu login cookie required")
        return []

    xhs_env, _, _ = get_xhs_cmd_env()
    raw = run_cmd([XHS_CLI, "search", query, "--sort", "latest", "--json"], timeout=30, env=xhs_env)
    lowered = raw.lower()
    if "not_authenticated" in lowered or "no 'a1' cookie" in lowered:
        mark_channel(channel, False, "xiaohongshu login cookie required")
        return []
    results = parse_generic_search(raw, channel, platform, query, dimension)
    mark_channel(channel, True, detail or "")
    return results[:count]


def search_wechat(
    platform: str,
    query: str,
    dimension: str | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    channel = "wechat"
    results: list[dict[str, Any]] = []
    agent_python = resolve_agent_reach_python()

    if not channel_disabled(channel) and agent_python:
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
        rows.append(
            {
                "title": article.get("title", ""),
                "url": url,
                "date": date,
                "source": article.get("source", ""),
                "snippet": article.get("snippet", ""),
            }
        )
    print(json.dumps(rows, ensure_ascii=False))

asyncio.run(main())
""" % (query, count)
        raw = run_cmd([agent_python, "-c", code], timeout=25)
        if "Traceback" not in raw and "ModuleNotFoundError" not in raw:
            results = parse_generic_search(raw, channel, platform, query, dimension)
            if results:
                mark_channel(channel, True)
                return results[:count]

    if command_available(MCPORTER):
        raw = mcporter_call(
            "exa.web_search_exa",
            {"query": f"site:mp.weixin.qq.com {query}", "numResults": count},
            timeout=20,
        )
        results = parse_exa_text(raw, platform, query, dimension)
        if not results:
            results = parse_generic_search(raw, channel, platform, query, dimension)
        mark_channel(channel, True, "used Exa fallback" if results else "no usable results")
        return results[:count]

    mark_channel(channel, False, "disabled or missing Agent-Reach Python")
    return []


def dedupe_and_filter(platform: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_results = sorted(
        results,
        key=lambda row: (
            {"P1": 0, "P2": 1, "P3": 2}.get(row.get("priority"), 3),
            -row.get("total_score", 0),
            -row.get("credibility_score", 0),
        ),
    )
    seen = set()
    filtered = []
    for result in ranked_results:
        title = result.get("title", "")
        if not title or is_social_noise(title, platform):
            continue
        if not in_window(result.get("raw_date") or result.get("date")):
            continue
        if result.get("relevance_score", 0) < 34:
            continue
        if result.get("total_score", 0) < MIN_SIGNAL_SCORE:
            continue
        if (
            result.get("source_tier") == "低可信站点"
            and result.get("total_score", 0) < 62
        ):
            continue
        key = (re.sub(r"\s+", "", title.lower())[:80], result.get("platform", ""))
        if key in seen:
            continue
        seen.add(key)
        filtered.append(result)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        parsed = parse_date(row.get("raw_date") or row.get("date")) or datetime.min
        priority_rank = {"P1": 0, "P2": 1, "P3": 2}.get(row.get("priority"), 3)
        return (
            priority_rank,
            -row.get("total_score", 0),
            -row.get("credibility_score", 0),
            parsed,
        )

    return sorted(filtered, key=sort_key)


def search_all_channels(platform: str) -> list[dict[str, Any]]:
    log(f"  [{platform}] 启动扫描...")
    results: list[dict[str, Any]] = []
    for dimension, query in build_queries(platform):
        dim = None if dimension == "综合" else dimension
        results.extend(search_baidu_ai(platform, query, dim, 3))
        results.extend(search_baidu(platform, query, dim, 5))
        results.extend(search_minimax(platform, query, dim, 5))
        results.extend(search_exa(platform, query, dim, 4))
        results.extend(search_weibo(platform, query, dim, 5))
        results.extend(search_xhs(platform, query, dim, 5))
        results.extend(search_wechat(platform, query, dim, 5))
        results.extend(search_weibo_trending(platform, query, 10))

    filtered = dedupe_and_filter(platform, results)
    log(f"  [{platform}] 原始 {len(results)} 条，保留 {len(filtered)} 条")
    return filtered


def build_platform_overview(platform: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "本期未捕捉到足够可信的用户增长信号，建议继续观察。"
    dimension_counter = Counter(row["dimension"] for row in rows)
    action_counter = Counter(row["action_type"] for row in rows)
    priority_counter = Counter(row["priority"] for row in rows)
    top_dimension = dimension_counter.most_common(1)[0][0]
    top_action = action_counter.most_common(1)[0][0]

    if top_action == "创作者激励":
        sentence = f"本期动作重心在供给侧争夺，{platform}主要通过创作者激励/扶持来做增长。"
    elif top_action == "分发/流量机制":
        sentence = f"本期更偏流量和分发机制调整，{platform}在提升内容分发效率。"
    elif top_action == "商业化/变现":
        sentence = f"本期重点落在商业化承接，{platform}在增强作者变现预期。"
    elif top_action == "AI能力":
        sentence = f"本期主要通过 AI 能力扩内容供给或场景渗透，{platform}动作偏产品化。"
    else:
        sentence = f"本期以运营动作放大增长信号，{platform}在为内容供给和用户活跃造势。"

    if priority_counter.get("P1"):
        sentence += f" 其中 {priority_counter['P1']} 条属于高优先级信号。"
    else:
        sentence += f" 当前以 {top_dimension} 类中优先级中等的信号为主。"
    return sentence


def build_management_summary(all_rows: list[dict[str, Any]]) -> list[str]:
    if not all_rows:
        return ["本期未捕捉到足够可信的用户增长动作。"]

    by_platform = Counter(row["platform"] for row in all_rows if row["priority"] == "P1")
    action_counter = Counter(row["action_type"] for row in all_rows)
    dimension_counter = Counter(row["dimension"] for row in all_rows)
    top_platforms = [name for name, _ in by_platform.most_common(3)] or [
        name for name, _ in Counter(row["platform"] for row in all_rows).most_common(3)
    ]
    top_actions = [name for name, _ in action_counter.most_common(2)]
    top_dimension = dimension_counter.most_common(1)[0][0]

    bullets = []
    if "创作者激励" in top_actions or top_dimension == "增长策略":
        platforms = "、".join(top_platforms[:3]) or "重点平台"
        bullets.append(
            f"供给侧争夺仍是主线，{platforms}出现了更密集的创作者激励、流量扶持或内容扶持信号。"
        )
    if "分发/流量机制" in top_actions or "产品功能" == top_dimension:
        bullets.append(
            "增长动作不只停留在补贴层面，多个平台同步在改分发入口、推荐机制或内容消费链路。"
        )
    if "AI能力" in top_actions:
        bullets.append(
            "AI 能力正在被更明确地用于创作提效与新场景渗透，说明平台在争夺效率红利。"
        )
    if "商业化/变现" in top_actions:
        bullets.append(
            "商业化承接正在成为增长动作的一部分，作者侧的变现预期被用于稳定内容供给。"
        )
    if not bullets:
        bullets.append("本期动作分散在多平台，需继续跟踪高可信来源中的持续性动作。")
    return bullets[:4]


def build_priority_signals(all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prioritized = sorted(
        all_rows,
        key=lambda row: (
            {"P1": 0, "P2": 1, "P3": 2}.get(row["priority"], 3),
            -row["total_score"],
            -row["credibility_score"],
        ),
    )
    return prioritized[:TOP_PRIORITY_SIGNAL_LIMIT]


def evidence_bucket(row: dict[str, Any]) -> str:
    if row.get("source_tier") == "official":
        return "官方/平台侧"
    if row.get("source") == "wechat" or row.get("domain") == "mp.weixin.qq.com":
        return "公众号文章"
    if row.get("source") in {"weibo", "weibo_hot", "xhs"}:
        return "社媒/平台内观察"
    return "公开网页/媒体"


def summarize_monitoring_quality(payload: dict[str, Any]) -> list[str]:
    all_rows = [row for rows in payload["by_platform"].values() for row in rows]
    lines: list[str] = []

    bucket_counter = Counter(evidence_bucket(row) for row in all_rows)
    ordered_buckets = ["官方/平台侧", "公众号文章", "公开网页/媒体", "社媒/平台内观察"]
    if bucket_counter:
        mix = "；".join(
            f"{label}{bucket_counter[label]}条"
            for label in ordered_buckets
            if bucket_counter.get(label)
        )
        lines.append(f"- 当前有效证据主要来自：{mix}。")
    else:
        lines.append("- 本期尚未形成足够稳定的有效证据组合，当前判断仍偏早期观察。")

    status = payload.get("channels", {})
    search_channels = ("baidu_ai", "baidu", "exa", "minimax")
    social_channels = ("weibo", "weibo_hot", "xhs")
    search_ok = any(status.get(channel, {}).get("ok") for channel in search_channels)
    social_ok = any(status.get(channel, {}).get("ok") for channel in social_channels)
    wechat_ok = status.get("wechat", {}).get("ok")
    xhs_ok = status.get("xhs", {}).get("ok")

    if not search_ok:
        lines.append("- 公开网页与媒体检索覆盖不足，可能漏掉已经对外发布但尚未在社媒扩散的增长动作。")
    if not social_ok:
        lines.append("- 平台内内容与社媒扩散样本不足，可能低估动作热度、创作者反馈和执行强度。")
    elif not xhs_ok:
        lines.append("- 小红书平台内观察样本不足，跨平台动作在小红书侧的传播与反馈仍需继续补强。")
    if not wechat_ok:
        lines.append("- 公众号长文覆盖不足，可能漏掉规则解释、活动复盘和更完整的运营口径。")
    if all(row.get("source_tier") != "official" for row in all_rows):
        lines.append("- 一手官方/平台侧证据偏少，涉及规则级判断时建议继续补充确认。")
    return lines[:4]


def summarize_channel_status() -> list[str]:
    lines = []
    for channel in CHANNEL_LABELS:
        status = channel_status.get(channel)
        label = CHANNEL_LABELS[channel]
        if not status:
            lines.append(f"- {label}：未调用")
            continue
        if status["ok"]:
            detail = status["details"][0] if status["details"] else "可用"
            lines.append(
                f"- {label}：可用（成功 {status['successes']}/{status['calls']} 次；备注：{detail}）"
            )
        else:
            detail = "；".join(status["details"][:2]) if status["details"] else "不可用"
            lines.append(
                f"- {label}：存在缺口（成功 {status['successes']}/{status['calls']} 次；原因：{detail}）"
            )
    return lines


def build_payload(by_platform: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    all_rows = [row for rows in by_platform.values() for row in rows]
    priority_rows = build_priority_signals(all_rows)
    platform_analysis = {}
    for platform in PLATFORM_ORDER:
        rows = by_platform.get(platform, [])
        platform_analysis[platform] = {
            "overview": build_platform_overview(platform, rows),
            "count": len(rows),
            "dimensions": dict(Counter(row["dimension"] for row in rows)),
            "priorities": dict(Counter(row["priority"] for row in rows)),
            "signals": rows,
        }

    gaps = []
    for channel in CHANNEL_LABELS:
        status = channel_status.get(channel)
        if status and not status["ok"]:
            gaps.append(
                {
                    "channel": channel,
                    "label": CHANNEL_LABELS[channel],
                    "detail": status["details"][0] if status["details"] else "channel unavailable",
                }
            )

    return {
        "scan_time": datetime.now().isoformat(),
        "window": {"start": DATE_START, "end": DATE_TODAY, "days": WINDOW_DAYS},
        "audience": REPORT_AUDIENCE,
        "platforms": PLATFORM_ORDER,
        "dimensions": list(DIMENSION_KEYWORDS.keys()),
        "raw_channel_calls": sum(status["calls"] for status in channel_status.values()),
        "effective_signal_count": len(all_rows),
        "high_priority_signal_count": sum(1 for row in all_rows if row["priority"] == "P1"),
        "channels": channel_status,
        "summary": {
            "management_summary": build_management_summary(all_rows),
            "priority_signals": priority_rows,
            "monitor_gaps": gaps,
        },
        "platform_analysis": platform_analysis,
        "by_platform": by_platform,
    }


def format_evidence_line(row: dict[str, Any]) -> str:
    parts = [row.get("date") or row.get("raw_date") or "日期未知", row.get("source_label") or row.get("source", "未知来源")]
    if row.get("domain"):
        parts.append(row["domain"])
    return " · ".join(parts)


def build_text_summary(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    platform_analysis = payload["platform_analysis"]
    priority_rows = summary["priority_signals"]

    lines = [
        f"竞品用户增长情报简报 · {DATE_TODAY}",
        f"读者：{REPORT_AUDIENCE}",
        f"时间窗口：{DATE_START} ～ {DATE_TODAY}（{WINDOW_DAYS}天）",
        "覆盖平台：" + "、".join(PLATFORM_ORDER),
        f"有效信号：{payload['effective_signal_count']} 条 | 高优先级：{payload['high_priority_signal_count']} 条",
        "",
        "一、管理层摘要",
    ]
    for index, bullet in enumerate(summary["management_summary"], 1):
        lines.append(f"{index}. {bullet}")

    lines.extend(["", "二、建议优先跟进"])
    if not priority_rows:
        lines.append("暂无高优先级信号。")
    else:
        for index, row in enumerate(priority_rows, 1):
            lines.append(
                f"{index}. [{row['priority']}][{row['credibility_label']}/{row['total_score']}] "
                f"{row['platform']}｜{row['dimension']}｜{row['action_type']}｜{row['title']}"
            )
            lines.append(f"   判断：{row['judgement']}")
            lines.append(f"   对小红书含义：{row['implication']}")
            lines.append(f"   证据：{format_evidence_line(row)}")
            if row.get("url"):
                lines.append(f"   链接：{row['url']}")

    lines.extend(["", "三、分平台拆解"])
    section_index = 1
    for platform in PLATFORM_ORDER:
        analysis = platform_analysis[platform]
        rows = analysis["signals"]
        lines.append(f"{section_index}. {platform}")
        lines.append(f"   态势判断：{analysis['overview']}")
        if not rows:
            lines.append("   暂无达到阈值的有效信号。")
            section_index += 1
            lines.append("")
            continue

        for row_index, row in enumerate(rows, 1):
            lines.append(
                f"   {row_index}) [{row['priority']}][{row['credibility_label']}/{row['total_score']}] "
                f"{row['dimension']}｜{row['action_type']}｜{row['title']}"
            )
            lines.append(f"      判断：{row['judgement']}")
            lines.append(f"      对小红书含义：{row['implication']}")
            lines.append(f"      证据：{format_evidence_line(row)}")
            if row.get("evidence_summary"):
                lines.append(f"      摘要：{row['evidence_summary']}")
            if row.get("url"):
                lines.append(f"      链接：{row['url']}")
        lines.append("")
        section_index += 1

    lines.append("四、证据质量与覆盖缺口")
    lines.extend(summarize_monitoring_quality(payload))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    log(
        f"[竞品扫描] {DATE_TODAY} · window={WINDOW_DAYS}d · queries/platform={MAX_QUERIES_PER_PLATFORM}"
    )
    by_platform = {}
    for platform in PLATFORM_ORDER:
        by_platform[platform] = search_all_channels(platform)

    payload = build_payload(by_platform)
    text_report = build_text_summary(payload)

    json_path = OUTPUT_DIR / "latest.json"
    text_path = OUTPUT_DIR / "latest_report.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(text_report, encoding="utf-8")

    log("")
    log("扫描完成")
    log(f"  结构化数据: {json_path}")
    log(f"  原始报告: {text_path}")
    log(f"  有效信号: {payload['effective_signal_count']}")
    log("")
    print(text_report)


if __name__ == "__main__":
    main()
