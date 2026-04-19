import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT = ROOT / ".test-output"
TEST_OUTPUT.mkdir(exist_ok=True)
os.environ.setdefault("COMPETITOR_SCAN_OUTPUT_DIR", str(TEST_OUTPUT))
os.environ.setdefault(
    "COMPETITOR_SCAN_DISABLE_CHANNELS",
    "baidu_ai,baidu,minimax,exa,official,creator_activity,ad_signal,weibo,weibo_hot,xhs,wechat",
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
    assert "implication" not in official


def test_platform_content_page_patterns_are_configured():
    row = scan.make_signal(
        platform="B站",
        source="official",
        title="B站UP主视频发布",
        query="B站 官方 创作者",
        date="2026-04-18",
        url="https://www.bilibili.com/video/BV1example",
        content="B站UP主发布视频，提到创作者激励。",
    )

    assert row["source_tier"] == "平台内容"
    assert row["credibility_score"] < 95


def test_undated_signal_is_capped_below_p1():
    undated = scan.make_signal(
        platform="微信视频号",
        source="exa",
        title="微信视频号创作者激励计划",
        query="微信视频号 创作者激励",
        url="https://support.weixin.qq.com/cgi-bin/mmsupportacctnodeweb-bin/pages/demo",
        content="微信视频号推出创作者激励、流量扶持和变现权益。",
    )
    dated = scan.make_signal(
        platform="微信视频号",
        source="exa",
        title="微信视频号创作者激励计划升级",
        query="微信视频号 创作者激励",
        date="2026-04-18",
        url="https://support.weixin.qq.com/cgi-bin/mmsupportacctnodeweb-bin/pages/demo",
        content="微信视频号推出创作者激励、流量扶持和变现权益。",
    )

    assert undated["date_confidence"] == "undated"
    assert undated["priority"] != "P1"
    assert dated["date_confidence"] == "dated"
    assert dated["priority"] == "P1"


def test_thin_official_search_result_is_not_overranked():
    row = scan.make_signal(
        platform="抖音",
        source="baidu_ai",
        title="抖音搜索",
        query="抖音 推荐 搜索 算法 新功能 AI 入口 最近14天",
        date="2026-04-12",
        url="https://so.douyin.com/s?keyword=本周新闻热点10条",
        content="火车票销售平台被约谈，医保支持基层医疗，嫦娥七号运抵发射场。",
        dimension="产品功能",
    )

    assert row["relevance_score"] < 60
    assert row["priority"] != "P1"


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


def test_filter_excludes_generic_product_news():
    row = scan.make_signal(
        platform="豆包",
        source="exa",
        title="豆包大模型升级1.6版，视频模型上新",
        query="豆包 AI 新功能",
        date="2026-04-18",
        url="https://example.com/doubao",
        content="豆包发布新模型，提升画质和语义理解。",
        dimension="产品功能",
    )

    assert scan.is_user_growth_signal(row) is False


def test_cluster_platform_events_merges_duplicate_news():
    rows = [
        scan.make_signal(
            platform="B站",
            source="exa",
            title="B站2026年4月上线播放页暂停广告功能，支持手动跳过与关闭",
            query="B站 暂停广告 播放页 创作者收益",
            date="2026-04-08",
            url="https://finance.sina.com.cn/example",
            content="B站上线播放页暂停广告，广告标注清晰且可关闭，UP主可参与。",
            dimension="产品功能",
        ),
        scan.make_signal(
            platform="B站",
            source="minimax",
            title="B站宣布将上线播放页暂停广告功能",
            query="B站 暂停广告 播放页 创作者收益",
            date="2026-04-08",
            url="https://new.qq.com/example",
            content="B站播放页暂停广告上线，创作者可选择参与相关商业化收益。",
            dimension="产品功能",
        ),
    ]
    events = scan.cluster_platform_events(rows)

    assert len(events) == 1
    assert events[0]["evidence_count"] == 2
    assert events[0]["growth_lever"] in {"商业化激励", "分发入口", "创作者供给"}


def test_dedupe_sort_prefers_newer_when_scores_match():
    older_date = (scan.NOW - timedelta(days=7)).strftime("%Y-%m-%d")
    newer_date = (scan.NOW - timedelta(days=1)).strftime("%Y-%m-%d")
    older = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级A",
        query="抖音 创作者激励",
        date=older_date,
        url="https://www.douyin.com/notice-a",
        content="抖音升级创作者激励和流量扶持。",
    )
    newer = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级B",
        query="抖音 创作者激励",
        date=newer_date,
        url="https://www.douyin.com/notice-b",
        content="抖音升级创作者激励和流量扶持。",
    )
    filtered = scan.dedupe_and_filter("抖音", [older, newer])
    assert filtered[0]["date"] == newer_date


def test_monitoring_quality_counts_official_sources():
    row = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级",
        query="抖音 创作者激励",
        date="2026-04-18",
        url="https://www.douyin.com/notice",
        content="抖音新增创作者激励、现金补贴和流量扶持。",
    )
    payload = {
        "by_platform": {"抖音": [row]},
        "channels": {},
    }
    lines = scan.summarize_monitoring_quality(payload)
    joined = "\n".join(lines)
    assert "官方/平台侧1条" in joined
    assert "一手官方/平台侧证据偏少" not in joined


def test_monitoring_quality_uses_neutral_social_gap():
    payload = {
        "by_platform": {"微博": []},
        "channels": {
            "weibo": {"ok": True, "calls": 1, "skipped": 0, "successes": 1, "details": []},
            "xhs": {"ok": False, "calls": 1, "skipped": 1, "successes": 0, "details": ["auth gap"]},
            "exa": {"ok": True, "calls": 1, "skipped": 0, "successes": 1, "details": []},
            "wechat": {"ok": True, "calls": 1, "skipped": 0, "successes": 1, "details": []},
        },
    }

    joined = "\n".join(scan.summarize_monitoring_quality(payload))
    assert "小红书侧" not in joined
    assert "部分社媒/平台内渠道未覆盖" in joined


def test_weibo_package_unavailable_marks_channel_gap():
    old_status = scan.channel_status
    old_command_available = scan.command_available
    old_search_weibo_package = scan.search_weibo_package
    try:
        scan.channel_status = {}
        scan.command_available = lambda _command: False
        scan.search_weibo_package = lambda *_args, **_kwargs: (
            [],
            "mcp_server_weibo unavailable: No module named 'mcp_server_weibo'",
        )

        rows = scan.search_weibo("微博", "微博 创作者激励")

        assert rows == []
        assert scan.channel_status["weibo"]["ok"] is False
        assert scan.channel_status["weibo"]["skipped"] == 1
    finally:
        scan.channel_status = old_status
        scan.command_available = old_command_available
        scan.search_weibo_package = old_search_weibo_package


def test_empty_report_with_no_successful_channels_is_not_business_conclusion():
    channels = {
        "exa": {"ok": False, "calls": 1, "skipped": 1, "successes": 0, "details": ["missing mcporter"]},
        "weibo": {"ok": False, "calls": 1, "skipped": 1, "successes": 0, "details": ["missing package"]},
    }
    summary = scan.build_management_summary([], channels)
    assert "不能代表竞品没有增长动作" in summary[0]


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
    assert "一、摘要" in report
    assert "二、分平台信息" in report
    assert "增长杠杆" in report
    assert "对小红书含义" not in report
    assert "三、" not in report


def test_management_summary_includes_signal_counts():
    dated = scan.make_signal(
        platform="抖音",
        source="exa",
        title="抖音创作者激励计划升级",
        query="抖音 创作者激励",
        date="2026-04-18",
        url="https://www.douyin.com/notice",
        content="抖音新增创作者激励、现金补贴和流量扶持。",
    )
    commercial = scan.make_signal(
        platform="微信视频号",
        source="exa",
        title="微信视频号创作分成计划升级",
        query="微信视频号 分成",
        date="2026-04-18",
        url="https://support.weixin.qq.com/cgi-bin/mmsupportacctnodeweb-bin/pages/demo",
        content="微信视频号升级创作者分成和广告变现权益。",
    )
    events = scan.cluster_platform_events([dated, commercial])
    summary = scan.build_management_summary(events, {}, 2)
    joined = "\n".join(summary)

    assert "本期形成" in summary[0]
    assert "用户增长事件" in summary[0]
    assert "P1" in summary[0]
    assert "创作者供给与商业化激励合计" in joined


def test_dry_run_writes_outputs():
    output = Path(os.environ["COMPETITOR_SCAN_OUTPUT_DIR"])
    scan.main()
    data = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert data["platforms"] == scan.PLATFORM_ORDER
    assert "management_summary" in data["summary"]
    assert "by_platform_events" in data
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
        test_platform_content_page_patterns_are_configured,
        test_undated_signal_is_capped_below_p1,
        test_thin_official_search_result_is_not_overranked,
        test_dedupe_filter_and_noise,
        test_filter_excludes_generic_product_news,
        test_cluster_platform_events_merges_duplicate_news,
        test_dedupe_sort_prefers_newer_when_scores_match,
        test_monitoring_quality_counts_official_sources,
        test_monitoring_quality_uses_neutral_social_gap,
        test_weibo_package_unavailable_marks_channel_gap,
        test_empty_report_with_no_successful_channels_is_not_business_conclusion,
        test_build_text_summary_contains_management_sections,
        test_management_summary_includes_signal_counts,
        test_dry_run_writes_outputs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
