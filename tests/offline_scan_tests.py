import importlib.util
import json
import os
import shutil
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
    assert (
        scan.parse_date("Thu Apr 09 11:52:55 +0800 2026").date().isoformat()
        == "2026-04-09"
    )


def test_build_queries_are_platform_specific():
    query = scan.build_queries("抖音")[0][1]
    assert "抖音" in query
    assert "创作者激励" in query
    month_label = f"{scan.NOW.year}年{scan.NOW.month}月"
    assert month_label in query

    doubao_query = scan.build_queries("豆包")[0][1]
    assert "豆包" in doubao_query
    assert "增长" in doubao_query


def test_format_mcporter_call_quotes_values():
    call = scan.format_mcporter_call(
        "xiaohongshu.search_feeds",
        {"keyword": "抖音 创作者", "limit": 5},
    )
    assert call == 'xiaohongshu.search_feeds(keyword: "抖音 创作者", limit: 5)'


def test_parse_exa_text():
    raw = """Title: 抖音创作者激励计划升级
URL: https://www.douyin.com/a
Published: 2026-04-18
Highlights: 抖音新增创作者现金补贴和流量扶持。
Title: 快手可灵AI发布新功能
URL: https://www.kuaishou.com/b
Published: 2026-04-17
Highlights: 可灵AI新增视频生成入口。"""
    rows = scan.parse_exa_text(raw, "抖音", "抖音 增长")
    assert len(rows) == 2
    assert rows[0]["source"] == "exa"
    assert rows[0]["url"] == "https://www.douyin.com/a"
    assert rows[0]["dimension"] == "增长策略"
    assert rows[0]["action_type"] == "创作者激励"


def test_parse_minimax_nested_json():
    payload = {
        "type": "text",
        "text": json.dumps(
            {
                "organic": [
                    {
                        "title": "微博创作活力分上线",
                        "link": "https://weibo.com/example",
                        "date": "2026-04-18 00:00:00",
                        "snippet": "微博上线创作活力分，强化作者内容标准。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }
    rows = scan.parse_minimax(json.dumps(payload, ensure_ascii=False), "微博", "微博 增长")
    assert len(rows) == 1
    assert rows[0]["source"] == "minimax"
    assert rows[0]["dimension"] in {"增长策略", "产品功能"}


def test_parse_xhs_generic_json():
    payload = {
        "data": {
            "items": [
                {
                    "display_title": "小红书创作者激励活动",
                    "note_id": "abc123",
                    "desc": "小红书开放创作者流量扶持。",
                    "user": {"nickname": "运营观察"},
                    "time": "2天前",
                }
            ]
        }
    }
    rows = scan.parse_generic_search(
        json.dumps(payload, ensure_ascii=False),
        "xhs",
        "抖音",
        "抖音 创作者激励",
    )
    assert len(rows) == 1
    assert rows[0]["author"] == "运营观察"
    assert rows[0]["url"] == "https://www.xiaohongshu.com/explore/abc123"


def test_xhs_cookie_header_creates_isolated_runtime():
    runtime_home = TEST_OUTPUT / "xhs-runtime"
    if runtime_home.exists():
        shutil.rmtree(runtime_home)

    old_header = scan.XHS_COOKIE_HEADER
    old_json = scan.XHS_COOKIE_JSON
    old_home = scan.XHS_RUNTIME_HOME
    old_env = scan._xhs_runtime_env
    old_detail = scan._xhs_runtime_detail
    old_runtime_home = scan._xhs_runtime_home

    try:
        scan.XHS_COOKIE_HEADER = "a1=test-a1; web_session=session-1; webId=web-1"
        scan.XHS_COOKIE_JSON = ""
        scan.XHS_RUNTIME_HOME = str(runtime_home)
        scan._xhs_runtime_env = None
        scan._xhs_runtime_detail = ""
        scan._xhs_runtime_home = None

        env, detail, error = scan.get_xhs_cmd_env()
        cookie_file = runtime_home / ".xiaohongshu-cli" / "cookies.json"
        payload = json.loads(cookie_file.read_text(encoding="utf-8"))

        assert error == ""
        assert detail == "provided cookie header"
        assert payload["a1"] == "test-a1"
        assert payload["web_session"] == "session-1"
        assert payload["webId"] == "web-1"
        assert env["USERPROFILE"] == str(runtime_home)
        assert env["HOME"] == str(runtime_home)
    finally:
        scan.XHS_COOKIE_HEADER = old_header
        scan.XHS_COOKIE_JSON = old_json
        scan.XHS_RUNTIME_HOME = old_home
        scan._xhs_runtime_env = old_env
        scan._xhs_runtime_detail = old_detail
        scan._xhs_runtime_home = old_runtime_home
        if runtime_home.exists():
            shutil.rmtree(runtime_home)


def test_make_signal_scores_domains():
    official = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级",
        query="抖音 创作者激励",
        url="https://www.douyin.com/notice",
        content="抖音升级创作者激励和流量扶持。",
    )
    seo = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级",
        query="抖音 创作者激励",
        url="https://www.bypdw.com/news/60d499915.html",
        content="抖音升级创作者激励和流量扶持。",
    )
    assert official["credibility_score"] > seo["credibility_score"]
    assert official["priority"] <= seo["priority"]


def test_dedupe_filter_and_noise():
    rows = [
        scan.make_signal(platform="微博", source="weibo_hot", title="航班取消引热议", query="微博"),
        scan.make_signal(
            platform="微博",
            source="weibo",
            title="微博创作活力分上线",
            query="微博",
            content="微博强化创作者内容标准与流量扶持。",
            url="https://weibo.com/example",
        ),
        scan.make_signal(
            platform="微博",
            source="exa",
            title="微博创作活力分上线",
            query="微博",
            content="微博强化创作者内容标准与流量扶持。",
            url="https://m.chinaz.com/2026/0403/1744525.shtml",
        ),
    ]
    filtered = scan.dedupe_and_filter("微博", rows)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "微博创作活力分上线"


def test_build_text_summary_contains_management_sections():
    row = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级",
        query="抖音 创作者激励",
        date="2026-04-18",
        url="https://www.douyin.com/notice",
        content="抖音新增创作者激励、现金补贴和流量扶持。",
    )
    payload = scan.build_payload({"抖音": [row], "抖音精选": [], "快手": [], "微信视频号": [], "B站": [], "微博": [], "豆包": []})
    report = scan.build_text_summary(payload)
    assert "一、管理层摘要" in report
    assert "二、建议优先跟进" in report
    assert "对小红书含义" in report
    assert "四、证据质量与覆盖缺口" in report


def test_dry_run_writes_outputs():
    output = Path(os.environ["COMPETITOR_SCAN_OUTPUT_DIR"])
    scan.main()
    data = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert data["platforms"] == scan.PLATFORM_ORDER
    assert "management_summary" in data["summary"]
    assert (output / "latest_report.txt").exists()


def main():
    tests = [
        test_parse_date,
        test_build_queries_are_platform_specific,
        test_format_mcporter_call_quotes_values,
        test_parse_exa_text,
        test_parse_minimax_nested_json,
        test_parse_xhs_generic_json,
        test_xhs_cookie_header_creates_isolated_runtime,
        test_make_signal_scores_domains,
        test_dedupe_filter_and_noise,
        test_build_text_summary_contains_management_sections,
        test_dry_run_writes_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
