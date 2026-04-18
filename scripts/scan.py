#!/usr/bin/env python3
"""
竞品动态扫描脚本 v2
使用所有可用CLI渠道执行搜索，输出结构化结果。
由Agent读取后整理成最终报告。
"""

import subprocess
import json
import os
import sys
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT_DIR = "/tmp/competitor_scan"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DATE_TODAY = datetime.now().strftime("%Y-%m-%d")
DATE_14D = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

BAIDU_API_KEY = os.environ.get(
    "BAIDU_API_KEY",
    "bce-v3/ALTAK-VbCGaJu6MR0bX7yXFf1dn/26fb7fb34ff0f3513ed1c6c100ac0392bb01b381"
)
SKILL_BAIDU = "/root/.openclaw/workspace/skills/baidu-search/scripts/search.py"
AR_VENV = "/root/.agent-reach-venv/bin"
MCPORTER = "/root/.nvm/versions/node/v22.22.2/bin/mcporter"
XHS = f"{AR_VENV}/xhs"

PLATFORM_QUERIES = {
    "抖音": [
        "抖音 创作者激励 补贴 2026年4月",
        "抖音 新功能 产品更新 2026年4月",
    ],
    "抖音精选": [
        "抖音精选 增长策略 运营 2026年4月",
        "抖音精选 月榜 创作者 2026年4月",
    ],
    "快手": [
        "快手 创作者激励 运营 动作 2026年4月",
        "快手 可灵AI 产品功能 2026年4月",
    ],
    "微信视频号": [
        "视频号 直播 拉新 运营 2026年4月",
        "微信视频号 用户增长 2026年4月",
    ],
    "B站": [
        "B站 创作者激励 新功能 2026年4月",
        "哔哩哔哩 用户增长 运营 2026年4月",
    ],
    "微博": [
        "微博 创作者激励 流量扶持 2026年4月",
        "微博 用户增长 运营 动作 2026年4月",
    ],
    "豆包": [
        "豆包 用户增长 产品功能 2026年4月",
        "豆包 春晚 赞助 用户规模 2026",
    ],
}


def _abs_date(date_str):
    """Convert various date formats to datetime. Returns None if unparseable."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # MiniMax: 2026-04-15 00:00:00
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%m月%d日', '%m/%d', '%d']:
        for prefix in ['', '2026-']:
            try:
                return datetime.strptime(prefix + date_str, fmt)
            except:
                pass
    # Relative: 3天前, 2小时前, 5分钟前, 昨天 14:30, 14:30
    m = re.match(r'(\d+)天前', date_str)
    if m:
        return datetime.now() - timedelta(days=int(m.group(1)))
    m = re.match(r'(\d+)小时前', date_str)
    if m:
        return datetime.now() - timedelta(hours=int(m.group(1)))
    m = re.match(r'(\d+)分钟前', date_str)
    if m:
        return datetime.now() - timedelta(minutes=int(m.group(1)))
    if date_str.startswith('昨天'):
        try:
            t = re.search(r'(\d+:\d+)', date_str)
            if t:
                yesterday = datetime.now() - timedelta(days=1)
                return datetime.strptime(f"{yesterday.strftime('%Y-%m-%d')} {t.group(1)}", '%Y-%m-%d %H:%M')
        except:
            pass
    #微博: 2026-04-15 15:22  or  4月15日 15:22
    for pat in [r'(\d{4})-(\d{2})-(\d{2})', r'(\d{1,2})月(\d{1,2})日']:
        m = re.search(pat, date_str)
        if m:
            try:
                if len(m.group(1)) == 4:  # YYYY-MM-DD
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:  # MM月DD日
                    return datetime(2026, int(m.group(1)), int(m.group(2)))
            except:
                pass
    return None


def _in_window(date_str, cutoff):
    """Return True if date_str is within window (cutoff now)."""
    abs_d = _abs_date(date_str)
    if abs_d is None:
        return True  # no date = keep (don't filter out)
    return abs_d.timestamp() >= cutoff


def run_cmd(cmd, timeout=30, env=None):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=timeout, env=env or os.environ)
        return r.stdout + (r.stderr if r.returncode != 0 else "")
    except Exception as e:
        return f"[CMD ERROR] {e}"


def extract_json(raw):
    """Extract JSON array or object from raw output that may have prefix lines."""
    if not raw or len(raw) < 10:
        return None
    # Try direct parse first
    try:
        return json.loads(raw)
    except:
        pass
    # Find first '[' and last ']' to extract JSON array
    start = raw.find('[')
    end = raw.rfind(']')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end+1])
        except:
            pass
    # Find first '{' and last '}' for JSON object
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end+1])
        except:
            pass
    return None


def parse_search_results(raw, source):
    """Try to parse JSON search results, extract key fields."""
    if not raw or len(raw) < 20:
        return []
    try:
        data = extract_json(raw)
        if data is None:
            return []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "result" in data:
                items = data["result"]
            elif "data" in data:
                d = data["data"]
                if isinstance(d, dict) and "items" in d:
                    items = d["items"]
                elif isinstance(d, list):
                    items = d
        results = []
        for it in (items if isinstance(items, list) else [])[:8]:
            if not isinstance(it, dict):
                continue
            if source in ("baidu", "minimax"):
                title = it.get("title","")
                url = it.get("url","")
                date = it.get("date","")
                content = re.sub(r"<[^>]+>","", (it.get("content","") or ""))[:200]
                if title:
                    results.append({"t":title,"u":url,"d":date,"c":content,"s":source})
            elif source == "weibo":
                text = re.sub(r"<[^>]+>","", it.get("text",""))[:150]
                results.append({
                    "t": text, "d": it.get("created_at",""),
                    "u": it.get("user",{}).get("screen_name",""), "s":"weibo"
                })
            elif source == "xhs":
                nc = it.get("note_card",{})
                results.append({
                    "t": nc.get("display_title",""),
                    "u": nc.get("user",{}).get("nick_name",""),
                    "d": nc.get("corner_tag_info",[{}])[0].get("text",""), "s":"xhs"
                })
            elif source == "exa":
                results.append({
                    "t": (it.get("title","") or "")[:100],
                    "u": it.get("url",""),
                    "d": it.get("published",""),
                    "c": " | ".join(it.get("highlights",[""]))[:2][:200],
                    "s":"exa"
                })
        return results
    except Exception as e:
        return [{"e": str(e)[:100], "raw": raw[:200], "s": source}]


def parse_exa_text(raw):
    """Parse Exa MCP plain-text output (key-value format, not JSON)."""
    if not raw or len(raw) < 20:
        return []
    results = []
    entries = re.split(r'(?=Title:)', raw)
    for entry in entries:
        if not entry.strip():
            continue
        title_m = re.search(r'Title:\s*(.+?)(?=\n)', entry)
        url_m = re.search(r'URL:\s*(.+?)(?=\n)', entry)
        date_m = re.search(r'Published:\s*(.+?)(?=\n)', entry)
        hl_m = re.search(r'Highlights:\s*(.+?)(?=(?:Author:|URL:|Title:|\Z))', entry, re.DOTALL)
        if title_m:
            title = title_m.group(1).strip()[:100]
            date = (date_m.group(1).strip()[:10] if date_m else '')
            highlights = hl_m.group(1).strip()[:200] if hl_m else ''
            results.append({
                "t": title,
                "u": url_m.group(1).strip() if url_m else '',
                "d": date,
                "c": highlights,
                "s": "exa"
            })
    return results
    """Try to parse JSON search results, extract key fields."""
    if not raw or len(raw) < 20:
        return []
    try:
        data = extract_json(raw)
        if data is None:
            return []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "result" in data:
                items = data["result"]
            elif "data" in data:
                d = data["data"]
                if isinstance(d, dict) and "items" in d:
                    items = d["items"]
                elif isinstance(d, list):
                    items = d
        results = []
        for it in (items if isinstance(items, list) else [])[:8]:
            if not isinstance(it, dict):
                continue
            if source in ("baidu", "minimax"):
                title = it.get("title","")
                url = it.get("url","")
                date = it.get("date","")
                content = re.sub(r"<[^>]+>","", (it.get("content","") or ""))[:200]
                if title:
                    results.append({"t":title,"u":url,"d":date,"c":content,"s":source})
            elif source == "weibo":
                text = re.sub(r"<[^>]+>","", it.get("text",""))[:150]
                results.append({
                    "t": text, "d": it.get("created_at",""),
                    "u": it.get("user",{}).get("screen_name",""), "s":"weibo"
                })
            elif source == "xhs":
                nc = it.get("note_card",{})
                results.append({
                    "t": nc.get("display_title",""),
                    "u": nc.get("user",{}).get("nick_name",""),
                    "d": nc.get("corner_tag_info",[{}])[0].get("text",""), "s":"xhs"
                })
            elif source == "exa":
                results.append({
                    "t": (it.get("title","") or "")[:100],
                    "u": it.get("url",""),
                    "d": it.get("published",""),
                    "c": " | ".join(it.get("highlights",[""])[:2])[:200],
                    "s":"exa"
                })
        return results
    except Exception as e:
        return [{"e": str(e)[:100], "raw": raw[:200], "s": source}]


def search_baidu(query, count=5):
    env = os.environ.copy()
    env["BAIDU_API_KEY"] = BAIDU_API_KEY
    raw = run_cmd(
        f'BAIDU_API_KEY="{BAIDU_API_KEY}" python3 "{SKILL_BAIDU}" '
        f'\'{{"query":"{query}","count":{count}}}\'',
        timeout=20, env=env
    )
    return parse_search_results(raw, "baidu")


def search_baidu_ai(query, count=3):
    """Baidu AI Search via chat/completions endpoint. 100 calls/day free.
    Returns structured search results from references."""
    try:
        import requests
    except ImportError:
        return []
    url = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    headers = {
        "Authorization": f"Bearer {BAIDU_API_KEY}",
        "X-Appbuilder-From": "openclaw",
        "Content-Type": "application/json"
    }
    body = {
        "instruction": (
            "你是一个竞品分析助手。请根据用户输入的query，搜索并总结相关内容。"
            "输出结构化的搜索结果，包括：标题、关键信息、来源。不要编造信息，只总结真实搜索到的内容。"
        ),
        "messages": [{"role": "user", "content": query}]
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        if resp.status_code == 429:
            print(f"  [baidu_ai] 配额耗尽 (429)", flush=True)
            return []
        if resp.status_code != 200:
            print(f"  [baidu_ai] HTTP {resp.status_code}: {resp.text[:100]}", flush=True)
            return []
        data = resp.json()
        # Response: {"request_id":"...","references":[{"id":1,"url":"...","title":"...","date":"...","content":"..."}]}
        references = data.get("references", []) if isinstance(data, dict) else []
        if not references:
            return []
        results = []
        cutoff_ts = (datetime.now() - timedelta(days=14)).timestamp()
        for ref in references[:count]:
            if not isinstance(ref, dict):
                continue
            date_str = ref.get("date", "")
            if date_str:
                try:
                    ts = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                    if ts < cutoff_ts:
                        continue
                except:
                    pass
            title = (ref.get("title") or "").strip()[:100]
            content = (ref.get("content") or "").strip()[:200]
            link = ref.get("url", "")
            if title:
                results.append({"t": title, "u": link, "d": date_str[:10], "c": content, "s": "baidu_ai"})
        return results
    except Exception as e:
        print(f"  [baidu_ai] Exception: {e}", flush=True)
        pass
    return []


def search_minimax(query, count=5):
    """Call MiniMax search via mcporter MCP. Falls back to Exa if unavailable."""
    import subprocess
    # Try MiniMax MCP server via mcporter (configured in mcporter.json)
    try:
        r = subprocess.run(
            ['mcporter', 'call', 'minimax.web_search', f'query={query}', f'numResults={count}'],
            capture_output=True, text=True, timeout=15
        )
        raw = r.stdout
        if raw and len(raw) > 50:
            data = extract_json(raw)
            if data and isinstance(data, dict):
                # MiniMax MCP returns {"type": "text", "text": "{...}"}
                # Inner JSON has the actual results
                inner_str = data.get('text', '')
                if inner_str:
                    try:
                        inner = json.loads(inner_str)
                    except:
                        inner = None
                else:
                    inner = None
                if inner is None:
                    inner = data  # fallback to outer if no inner
                items = inner.get('organic', []) or []
                cutoff_ts = (datetime.now() - timedelta(days=14)).timestamp()
                results = []
                for item in items[:count]:
                    if not isinstance(item, dict):
                        continue
                    date_str = item.get('date', '')
                    if date_str:
                        try:
                            # MiniMax date format: "2026-03-31 11:07:42"
                            ts = datetime.strptime(date_str[:19], '%Y-%m-%d %H:%M:%S').timestamp()
                            if ts < cutoff_ts:
                                continue
                        except:
                            pass
                    title = re.sub(r'<[^>]+>', '', (item.get('title') or '')).strip()[:100]
                    snippet = re.sub(r'<[^>]+>', '', (item.get('snippet') or '')).strip()[:200]
                    link = item.get('link', '')
                    if title:
                        results.append({'t': title, 'u': link, 'd': date_str[:10], 'c': snippet, 's': 'minimax'})
                if results:
                    return results
    except Exception as e:
        pass
    # Fallback: use Exa via mcporter (reliable, no API key needed)
    try:
        r = subprocess.run(
            ['mcporter', 'call', 'exa.web_search_exa', f'query={query}', f'numResults={count}'],
            capture_output=True, text=True, timeout=15
        )
        return parse_search_results(r.stdout, 'exa')
    except Exception:
        return []


def search_weibo(keyword, limit=5):
    raw = run_cmd(
        f'{MCPORTER} call weibo.search_content keyword="{keyword}" limit={limit}',
        timeout=20
    )
    return parse_search_results(raw, "weibo")


def search_weibo_trending(limit=10):
    raw = run_cmd(f'{MCPORTER} call weibo.get_trendings limit={limit}', timeout=20)
    try:
        data = json.loads(raw)
        results = []
        for item in data.get("result", [])[:10]:
            results.append({
                "t": item.get("description",""),
                "d": f"热搜{item.get('trending',0)}",
                "u": "", "s": "weibo_hot"
            })
        return results
    except:
        return []


def search_xhs(keyword, limit=5):
    raw = run_cmd(f'{XHS} search "{keyword}" 2>/dev/null', timeout=20)
    # XHS outputs a custom text/YAML-like format, not JSON
    # Parse by extracting display_title and nick_name fields
    results = []
    items = re.findall(r'display_title:\s*(.+?)(?:\n|\r|$)', raw)
    users = re.findall(r'nick_name:\s*(.+?)(?:\n|\r|$)', raw)
    times = re.findall(r'text:\s*(\d+天前|\d+小时前|\d+分钟前|昨天 \d+:\d+|\d+:\d+)(?:\n|\r|$)', raw)
    for i, title in enumerate(items[:limit]):
        results.append({
            "t": title.strip(),
            "u": users[i].strip() if i < len(users) else "",
            "d": times[i].strip() if i < len(times) else "",
            "s": "xhs"
        })
    return results


def search_exa(query, num=5):
    raw = run_cmd(
        f'{MCPORTER} call exa.web_search_exa query="{query}" numResults={num}',
        timeout=20
    )
    return parse_exa_text(raw)


def search_wechat(keyword, limit=5):
    """Search WeChat public articles via miku_ai (no API key needed)."""
    import subprocess, re
    AR_PY = "/root/.agent-reach-venv/bin/python3"
    code = f"""
import asyncio
from miku_ai import get_wexin_article
async def s():
    for a in await get_wexin_article('{keyword}', {limit}):
        url = a.get('url', '')
        # Extract timestamp from URL for date parsing
        ts_match = url and __import__('re').search(r'timestamp=(\\d+)', url)
        date_str = ''
        if ts_match:
            try:
                import time
                date_str = time.strftime('%Y-%m-%d', time.localtime(int(ts_match.group(1))))
            except:
                pass
        title = a.get('title', ' ')
        print(title, '|', url, '|', date_str)
asyncio.run(s())
"""
    try:
        r = subprocess.run([AR_PY, '-c', code], capture_output=True, text=True, timeout=15)
        results = []
        for line in (r.stdout or '').strip().split('\n'):
            if '|' not in line:
                continue
            parts = line.split('|')
            if len(parts) >= 2:
                title = parts[0].strip()
                url = parts[1].strip()
                date = parts[2].strip() if len(parts) >= 3 else ''
                if title and title != ' ':
                    results.append({'t': title, 'u': url, 'd': date, 'c': '', 's': 'wechat'})
        return results
    except Exception:
        return []


def search_all_channels(platform, queries):
    """Run all available channels for a platform."""
    print(f"  [{platform}] 启动多渠道搜索...", flush=True)
    all_results = []
    seen = set()

    def dedup(res):
        key = res.get("t","")[:60]
        if key and key not in seen:
            seen.add(key)
            return True
        return False

    # Baidu AI Search (web_summary, 100 calls/day free)
    for q in queries[:1]:
        for r in search_baidu_ai(q, 3):
            if dedup(r): all_results.append(r)

    # Baidu searches (fallback when web_summary fails)
    for q in queries[:1]:
        for r in search_baidu(q):
            if dedup(r): all_results.append(r)

    # MiniMax searches (web search - important source)
    for q in queries[:1]:
        for r in search_minimax(q, 5):
            if dedup(r): all_results.append(r)

    # Exa searches
    for q in queries[:1]:
        for r in search_exa(q, 3):
            if dedup(r): all_results.append(r)

    # Weibo — all platforms (important source for growth signals)
    for r in search_weibo(queries[0], 5):
        if dedup(r): all_results.append(r)
    for r in search_weibo_trending(10):
        if dedup(r): all_results.append(r)

    # XHS — all platforms (competitor content discovery)
    for r in search_xhs(queries[0], 5):
        if dedup(r): all_results.append(r)

    # WeChat public articles — all platforms (high-value deep content)
    for r in search_wechat(queries[0], 5):
        if dedup(r): all_results.append(r)

    # Apply 14-day filter to all results
    cutoff_ts = (datetime.now() - timedelta(days=14)).timestamp()
    before = len(all_results)
    all_results = [r for r in all_results if _in_window(r.get('d', ''), cutoff_ts)]
    if before != len(all_results):
        print(f"  [{platform}] → {len(all_results)} 条（过滤掉{before - len(all_results)}条过期）", flush=True)
    else:
        print(f"  [{platform}] → {len(all_results)} 条去重结果", flush=True)
    return all_results


def build_summary(all_results, date_str):
    """Build the full text report."""
    buf = []
    buf.append(f"📡 竞品动态扫描 · {date_str}")
    buf.append(f"时间窗口：{DATE_14D} ～ {date_str}（双周内）")
    buf.append(f"覆盖：抖音、抖音精选、快手、微信视频号、B站、微博、豆包")
    buf.append(f"渠道：百度AI搜索(web_summary) + 百度搜索 + Exa + 微博 + 小红书 + 微信公众号(miku_ai) + MiniMax(MCP fallback→Exa)\n")

    for platform, results in all_results.items():
        buf.append(f"\n{'━'*40}")
        buf.append(f"【{platform}】")
        if not results:
            buf.append("  （暂无搜索结果）")
            continue
        for i, r in enumerate(results[:15], 1):
            source = r.get("s","?")
            title = r.get("t","")
            date = str(r.get("d",""))[:10]
            user = r.get("u","")
            content = r.get("c","")[:100]
            buf.append(f"  {i}. [{source}] {date} | {user} | {title}")
            if content:
                buf.append(f"     └ {content[:100]}")

    buf.append(f"\n{'━'*40}")
    buf.append("⚠️ 以上为原始搜索结果，Agent整理后输出正式报告")
    return "\n".join(buf)


def main():
    print(f"[竞品扫描] {'='*40}")
    print(f"[竞品扫描] {datetime.now().strftime('%H:%M:%S')} · {DATE_TODAY}")
    print(f"[竞品扫描] 14天窗口: {DATE_14D} → {DATE_TODAY}\n")

    all_results = {}
    for platform, queries in PLATFORM_QUERIES.items():
        print(f">>> {platform}", end=" ", flush=True)
        results = search_all_channels(platform, queries)
        all_results[platform] = results

    print(f"\n[竞品扫描] 生成报告中...")

    report_text = build_summary(all_results, DATE_TODAY)

    txt_path = f"{OUTPUT_DIR}/latest_report.txt"
    json_path = f"{OUTPUT_DIR}/latest.json"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Also save structured data
    struct = {
        "scan_time": datetime.now().isoformat(),
        "window": f"{DATE_14D} to {DATE_TODAY}",
        "platforms": list(PLATFORM_QUERIES.keys()),
        "by_platform": {p: [{"title":r.get("t",""),"date":r.get("d",""),"user":r.get("u",""),"source":r.get("s",""),"content":r.get("c","")[:200]} for r in rs] for p, rs in all_results.items()}
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(struct, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 扫描完成")
    print(f"  原始报告: {txt_path}")
    print(f"  结构数据: {json_path}")
    total = sum(len(v) for v in all_results.values())
    print(f"  共 {total} 条信号（{len(all_results)} 个平台）")

    # Also print to stdout so agent sees it
    print(f"\n{'='*40}\n{report_text}")


if __name__ == "__main__":
    main()
