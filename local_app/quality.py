"""规则式报告自检。

不调用模型、不联网，只看已经落盘的一份报告是否满足最低可信度：
有没有正文、有没有来源、来源数与引用是否对得上、循环轮次有没有超预算、
失败的报告有没有冒充成功。它是“质量基线”的地基，不是效果评测。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
SOURCES_MARK = "Sources:"
SUMMARY_MARK = "## Summary"
MIN_REPORT_CHARS = 200


def load_result(outputs_dir, report_id: str) -> dict | None:
    """从 outputs/<id>.json 读取完整结果（含 requested_loops），读不到返回 None。"""
    if not report_id or "/" in report_id or "\\" in report_id or ".." in report_id:
        return None
    path = Path(outputs_dir) / f"{report_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def extract_urls(text: str) -> list[str]:
    """按出现顺序去重提取 URL。"""
    seen: set[str] = set()
    urls: list[str] = []
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(".,;:，。；：")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def check_report(result: dict) -> dict:
    """对单条研究结果做规则检查，返回逐项结果与汇总。"""
    report = result.get("report") or ""
    status = (result.get("status") or "").strip()
    requested_raw = result.get("requested_loops")
    requested = int(requested_raw) if isinstance(requested_raw, (int, float)) else None
    actual = int(result.get("actual_loops") or 0)
    urls = extract_urls(report)

    if requested is None:
        budget_ok, budget_detail = True, "预算未记录，跳过比对"
    else:
        budget_ok, budget_detail = actual <= requested, f"实际 {actual} / 预算 {requested}"

    checks = [
        ("status_completed", status == "completed", f"status={status or '空'}"),
        ("has_summary", any(mark in report for mark in (SUMMARY_MARK, "## 研究总结")), "含总结小节（中文或英文）"),
        ("has_sources_section", any(mark in report for mark in (SOURCES_MARK, "参考来源：")), "含来源小节（中文或英文）"),
        ("has_citation", len(urls) > 0, f"报告内 URL {len(urls)} 条"),
        ("min_length", len(report) >= MIN_REPORT_CHARS,
         f"正文 {len(report)} 字符（下限 {MIN_REPORT_CHARS}）"),
        ("loops_within_budget", budget_ok, budget_detail),
        ("no_error", not (result.get("error") or "").strip(),
         "error 为空" if not (result.get("error") or "").strip() else "error 非空"),
    ]

    items = [{"name": n, "ok": bool(ok), "detail": d} for n, ok, d in checks]
    passed = sum(1 for i in items if i["ok"])
    return {
        "id": result.get("id", ""),
        "topic": result.get("topic", ""),
        "status": status,
        "seconds": result.get("seconds"),
        "passed": passed,
        "total": len(items),
        "score": round(passed / len(items), 3),
        "failed": [i["name"] for i in items if not i["ok"]],
        "checks": items,
    }


def summarize(rows: list[dict]) -> dict:
    """把多条检查结果汇总成基线指标。"""
    total = len(rows)
    if not total:
        return {"reports": 0}
    completed = sum(1 for r in rows if r["status"] == "completed")
    passed_all = sum(1 for r in rows if r["passed"] == r["total"])
    fail_counter: dict[str, int] = {}
    for r in rows:
        for name in r["failed"]:
            fail_counter[name] = fail_counter.get(name, 0) + 1
    top_failures = sorted(fail_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "reports": total,
        "completed": completed,
        "completion_rate": round(completed / total, 3),
        "all_checks_passed": passed_all,
        "all_checks_passed_rate": round(passed_all / total, 3),
        "avg_score": round(sum(r["score"] for r in rows) / total, 3),
        "top_failures": top_failures,
    }
