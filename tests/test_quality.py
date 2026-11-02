"""规则式报告自检的单元测试。不调用模型、不联网。"""
from __future__ import annotations

import json

from local_app.quality import check_report, extract_urls, load_result, summarize

GOOD_REPORT = (
    "## Summary\n"
    + "这是一段足够长的研究正文，用来满足最小长度检查。" * 6
    + "\n\n ### Sources:\n"
    "* typing — Python 文档 : https://docs.python.org/3/library/typing.html\n"
    "* dataclasses — Python 文档 : https://docs.python.org/3/library/dataclasses.html\n"
)

GOOD = {
    "id": "abc123",
    "topic": "Python type annotations",
    "status": "completed",
    "requested_loops": 1,
    "actual_loops": 1,
    "mode": "provided_urls",
    "error": "",
    "seconds": 8.881,
    "report": GOOD_REPORT,
}


def _failed(result):
    return set(check_report(result)["failed"])


def test_extract_urls_dedup_and_strip():
    text = "见 https://a.example/x，以及 https://b.example/y。再看 https://a.example/x。"
    assert extract_urls(text) == ["https://a.example/x", "https://b.example/y"]


def test_extract_urls_handles_empty():
    assert extract_urls("") == []
    assert extract_urls(None) == []


def test_good_report_passes_everything():
    row = check_report(GOOD)
    assert row["passed"] == row["total"] == 7
    assert row["failed"] == []
    assert row["score"] == 1.0


def test_missing_sources_section_is_flagged():
    bad = dict(GOOD, report="## Summary\n" + "正文" * 120)
    assert "has_sources_section" in _failed(bad)
    assert "has_citation" in _failed(bad)


def test_short_report_is_flagged():
    bad = dict(GOOD, report="## Summary\n短\n\n ### Sources:\n* a : https://a.example/x")
    assert "min_length" in _failed(bad)


def test_loop_over_budget_is_flagged():
    bad = dict(GOOD, requested_loops=1, actual_loops=2)
    assert "loops_within_budget" in _failed(bad)


def test_failed_status_is_flagged():
    bad = dict(GOOD, status="failed", error="URLError: unreachable")
    failed = _failed(bad)
    assert "status_completed" in failed
    assert "no_error" in failed


def test_empty_report_does_not_crash():
    row = check_report({"id": "x", "topic": "", "status": "", "report": ""})
    assert row["total"] == 7
    # 空报告里只有“循环未超预算”和“error 为空”两条能通过
    assert row["passed"] == 2
    assert {"status_completed", "has_summary", "has_sources_section",
            "has_citation", "min_length"} <= set(row["failed"])


def test_summarize_aggregates():
    rows = [check_report(GOOD), check_report(dict(GOOD, id="b", status="failed"))]
    summary = summarize(rows)
    assert summary["reports"] == 2
    assert summary["completed"] == 1
    assert summary["completion_rate"] == 0.5
    assert summary["all_checks_passed"] == 1
    names = dict(summary["top_failures"])
    assert names["status_completed"] == 1


def test_summarize_empty():
    assert summarize([]) == {"reports": 0}


def test_load_result_reads_json(tmp_path):
    (tmp_path / "abc.json").write_text(json.dumps(GOOD, ensure_ascii=False), encoding="utf-8")
    data = load_result(tmp_path, "abc")
    assert data is not None and data["id"] == "abc123"


def test_load_result_missing_file(tmp_path):
    assert load_result(tmp_path, "nope") is None


def test_load_result_blocks_traversal(tmp_path):
    assert load_result(tmp_path, "../secret") is None
    assert load_result(tmp_path, "..\\secret") is None


def test_load_result_survives_broken_json(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert load_result(tmp_path, "bad") is None
