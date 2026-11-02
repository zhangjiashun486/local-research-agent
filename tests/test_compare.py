"""报告对比的单元测试。不调用模型、不联网。"""
from __future__ import annotations

from local_app.compare import VERDICT_TEXT, compare_reports, render

GOOD_REPORT = (
    "## Summary\n"
    + "这是一段足够长的研究正文，用来满足最小长度检查。" * 6
    + "\n\n ### Sources:\n"
    "* a : https://a.example/x\n* b : https://b.example/y\n"
)


def _result(**kw):
    base = {
        "id": "id1",
        "topic": "Python typing",
        "status": "completed",
        "requested_loops": 1,
        "actual_loops": 1,
        "error": "",
        "seconds": 9.0,
        "report": GOOD_REPORT,
    }
    base.update(kw)
    return base


def test_identical_reports_have_no_change():
    out = compare_reports(_result(), _result(id="id2"))
    assert out["verdict"] == "unchanged"
    assert out["citations"]["added"] == [] and out["citations"]["removed"] == []
    assert out["delta"]["passed"] == 0
    assert out["delta"]["same_topic"] is True


def test_more_citations_is_detected():
    after = _result(id="id2", report=GOOD_REPORT + "* c : https://c.example/z\n")
    out = compare_reports(_result(), after)
    assert out["verdict"] == "more_citations"
    assert out["citations"]["added"] == ["https://c.example/z"]
    assert out["delta"]["citations"] == 1


def test_lost_citation_is_detected():
    before = _result(report=GOOD_REPORT + "* c : https://c.example/z\n")
    out = compare_reports(before, _result(id="id2"))
    assert out["verdict"] == "fewer_citations"
    assert out["citations"]["removed"] == ["https://c.example/z"]


def test_fixed_check_marks_improved():
    before = _result(status="failed", error="URLError", report="short")
    after = _result(id="id2")
    out = compare_reports(before, after)
    assert out["verdict"] == "improved"
    assert "status_completed" in out["checks"]["fixed"]
    assert out["checks"]["regressed"] == []
    assert out["delta"]["passed"] > 0


def test_regressed_check_marks_degraded():
    before = _result()
    after = _result(id="id2", status="failed", error="boom")
    out = compare_reports(before, after)
    assert out["verdict"] == "degraded"
    assert "status_completed" in out["checks"]["regressed"]


def test_same_topic_false_when_topics_differ():
    out = compare_reports(_result(), _result(id="id2", topic="另一个主题"))
    assert out["delta"]["same_topic"] is False


def test_render_contains_key_lines():
    text = render(compare_reports(_result(), _result(id="id2", report=GOOD_REPORT + "* c : https://c.example/z\n")))
    assert "结论：" in text and "改动前" in text and "新增引用" in text


def test_length_change_is_flagged():
    after = _result(id="id2", report=GOOD_REPORT + "补充了更多分析。" * 40)
    out = compare_reports(_result(), after)
    assert out["verdict"] == "length_changed"
    assert out["delta"]["chars"] > 0


def test_verdict_text_covers_all_keys():
    assert set(VERDICT_TEXT) == {
        "improved", "degraded", "more_citations",
        "fewer_citations", "length_changed", "unchanged",
    }
