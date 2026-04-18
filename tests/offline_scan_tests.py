import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT = ROOT / ".test-output"
TEST_OUTPUT.mkdir(exist_ok=True)
os.environ.setdefault("COMPETITOR_SCAN_OUTPUT_DIR", str(TEST_OUTPUT))
os.environ.setdefault(
    "COMPETITOR_SCAN_DISABLE_CHANNELS",
    "baidu_ai,baidu,minimax,exa,weibo,weibo_hot,xhs,wechat",
)

spec = importlib.util.spec_from_file_location("scan", ROOT / "scripts" / "scan.py")
scan = importlib.util.module_from_spec(spec)
sys.modules["scan"] = scan
spec.loader.exec_module(scan)


def test_parse_date():
    assert scan.parse_date("2026-04-18 09:30:12").date().isoformat() == "2026-04-18"
    assert scan.parse_date("4月18日", now=datetime(2026, 4, 18)).date().isoformat() == "2026-04-18"
    assert scan.parse_date("3天前", now=datetime(2026, 4, 18)).date().isoformat() == "2026-04-15"
    assert scan.parse_date("昨天 14:30", now=datetime(2026, 4, 18)).date().isoformat() == "2026-04-17"


def test_build_queries_are_dynamic():
    query = scan.build_queries("抖音")[0][1]
    assert "2026年4月" in query
    assert "2026年4月" == f"{scan.NOW.year}年{scan.NOW.month}月"


def test_parse_exa_text():
    raw = """Title: 抖音创作者激励计划升级
URL: https://example.com/a
Published: 2026-04-18
Highlights: 抖音新增创作者现金补贴和流量扶持。

Title: 快手可灵AI发布新功能
URL: https://example.com/b
Published: 2026-04-17
Highlights: 可灵AI新增视频生成入口。
"""
    rows = scan.parse_exa_text(raw, "抖音", "抖音 增长")
    assert len(rows) == 2
    assert rows[0]["source"] == "exa"
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["dimension"] == "增长策略"


def test_parse_minimax_nested_json():
    payload = {
        "type": "text",
        "text": json.dumps(
            {
                "organic": [
                    {
                        "title": "微博创作者流量扶持活动",
                        "link": "https://example.com/weibo",
                        "date": "2026-04-18 00:00:00",
                        "snippet": "微博上线创作者流量扶持。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }
    rows = scan.parse_minimax(json.dumps(payload, ensure_ascii=False), "微博", "微博 增长")
    assert len(rows) == 1
    assert rows[0]["source"] == "minimax"
    assert rows[0]["dimension"] == "增长策略"


def test_dedupe_filter_and_noise():
    rows = [
        scan.make_signal(platform="微博", source="weibo_hot", title="航班取消引热议", query="微博"),
        scan.make_signal(platform="微博", source="weibo", title="微博创作者流量扶持活动", query="微博"),
        scan.make_signal(platform="微博", source="exa", title="微博创作者流量扶持活动", query="微博"),
    ]
    filtered = scan.dedupe_and_filter("微博", rows)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "微博创作者流量扶持活动"


def test_dry_run_writes_outputs():
    output = Path(os.environ["COMPETITOR_SCAN_OUTPUT_DIR"])
    scan.main()
    data = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert data["platforms"] == scan.PLATFORM_ORDER
    assert data["effective_signal_count"] == 0
    assert (output / "latest_report.txt").exists()


def main():
    tests = [
        test_parse_date,
        test_build_queries_are_dynamic,
        test_parse_exa_text,
        test_parse_minimax_nested_json,
        test_dedupe_filter_and_noise,
        test_dry_run_writes_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
