"""对比两次研究结果：引用增删、规则通过项变化、耗时与轮数。

用途：改了一处逻辑之后，用同一个主题再跑一次，对比两次的差异，
而不是凭感觉说“好像变好了”。

注意这是**结构化对比**：它比较的是引用集合、规则通过情况和长度，
不判断两份报告在事实上谁更准确——那需要人工评测集。
"""
from __future__ import annotations

from .quality import check_report, extract_urls


def _urls(result: dict) -> list[str]:
    return extract_urls((result or {}).get("report") or "")


def _summary(result: dict, check: dict) -> dict:
    return {
        "id": (result or {}).get("id", ""),
        "topic": (result or {}).get("topic", ""),
        "status": (result or {}).get("status", ""),
        "seconds": (result or {}).get("seconds"),
        "loops": (result or {}).get("actual_loops"),
        "chars": len((result or {}).get("report") or ""),
        "citations": len(_urls(result)),
        "passed": check["passed"],
        "total": check["total"],
    }


def compare_reports(before: dict, after: dict) -> dict:
    """返回两次结果的差异；before 是改动前，after 是改动后。"""
    urls_before = _urls(before)
    urls_after = _urls(after)
    set_before, set_after = set(urls_before), set(urls_after)

    qa = check_report(before)
    qb = check_report(after)

    fixed = [name for name in qa["failed"] if name not in qb["failed"]]
    regressed = [name for name in qb["failed"] if name not in qa["failed"]]
    passed_delta = qb["passed"] - qa["passed"]

    if passed_delta > 0:
        verdict = "improved"
    elif passed_delta < 0:
        verdict = "degraded"
    elif len(urls_after) > len(urls_before):
        verdict = "more_citations"
    elif len(urls_after) < len(urls_before):
        verdict = "fewer_citations"
    else:
        verdict = "unchanged"

    seconds_before = (before or {}).get("seconds") or 0
    seconds_after = (after or {}).get("seconds") or 0
    chars_before = len((before or {}).get("report") or "")
    chars_after = len((after or {}).get("report") or "")

    if verdict == "unchanged":
        # 规则与引用都没变，但如果正文长度变化超过两成，也值得单独标出来
        if chars_before and abs(chars_after - chars_before) / chars_before >= 0.2:
            verdict = "length_changed"

    return {
        "before": _summary(before, qa),
        "after": _summary(after, qb),
        "citations": {
            "added": sorted(set_after - set_before),
            "removed": sorted(set_before - set_after),
            "common": sorted(set_before & set_after),
        },
        "checks": {"fixed": fixed, "regressed": regressed},
        "delta": {
            "passed": passed_delta,
            "citations": len(urls_after) - len(urls_before),
            "chars": len((after or {}).get("report") or "") - len((before or {}).get("report") or ""),
            "seconds": round(seconds_after - seconds_before, 3),
            "same_topic": (before or {}).get("topic") == (after or {}).get("topic"),
        },
        "verdict": verdict,
    }


VERDICT_TEXT = {
    "improved": "规则通过项增加",
    "degraded": "规则通过项减少",
    "more_citations": "引用变多（规则通过项不变）",
    "fewer_citations": "引用变少（规则通过项不变）",
    "length_changed": "规则与引用不变，正文长度变化超过两成",
    "unchanged": "无可见变化",
}


def render(result: dict) -> str:
    b, a = result["before"], result["after"]
    lines = [
        f"主题：{b['topic'] or '（空）'}",
        f"结论：{VERDICT_TEXT.get(result['verdict'], result['verdict'])}",
        "",
        f"{'':10}{'改动前':>14}{'改动后':>14}{'变化':>12}",
        f"{'状态':10}{b['status']:>14}{a['status']:>14}",
        f"{'规则通过':10}{str(b['passed']) + '/' + str(b['total']):>14}{str(a['passed']) + '/' + str(a['total']):>14}{result['delta']['passed']:>+12}",
        f"{'引用数':10}{b['citations']:>14}{a['citations']:>14}{result['delta']['citations']:>+12}",
        f"{'字符数':10}{b['chars']:>14}{a['chars']:>14}{result['delta']['chars']:>+12}",
        f"{'耗时(s)':10}{b['seconds'] or 0:>14.2f}{a['seconds'] or 0:>14.2f}{result['delta']['seconds']:>+12.2f}",
    ]
    if result["checks"]["fixed"]:
        lines.append("")
        lines.append("修好的项：" + "、".join(result["checks"]["fixed"]))
    if result["checks"]["regressed"]:
        lines.append("退化的项：" + "、".join(result["checks"]["regressed"]))
    if result["citations"]["added"]:
        lines.append("新增引用：" + "，".join(result["citations"]["added"][:3]))
    if result["citations"]["removed"]:
        lines.append("丢失引用：" + "，".join(result["citations"]["removed"][:3]))
    return "\n".join(lines)
