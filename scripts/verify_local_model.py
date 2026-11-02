"""真实本地模型的异常场景验证（需先启动本地模型 API）。

用法（在 <仓库目录> 下执行）：
    .\\.venv\\Scripts\\python.exe scripts/verify_local_model.py

四个场景：
1. 正常路径：有效 HTTPS 来源 + 1 轮预算 → 期望 completed，报告含 Sources
2. 来源无内容：指向不存在的文档页 → 期望不产出无来源结论（empty/failed）
3. 来源不可达：不存在的域名 → 期望 failed，且记录异常类型
4. 获取真实模型非 JSON 输出，再把该原始输出送入应用查询解析方法，检查实际回退值

结果写入 outputs/checks/real-model-edge-cases-<时间戳>.json。前三项会在 outputs 中保存运行记录；
第四项是“真实输出重放到应用解析路径”，不是模型自然异常的完整研究链路。
"""
import json
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs" / "checks"

import sys

sys.path[:0] = [str(REPO), str(REPO / "src")]

from local_app.research import run_research  # noqa: E402


def case(name, fn):
    started = time.time()
    try:
        detail = fn()
        ok = detail.get("ok", False)
        record = {"case": name, "ok": bool(ok), "seconds": round(time.time() - started, 2), **detail}
    except Exception as exc:  # noqa: BLE001
        record = {"case": name, "ok": False, "seconds": round(time.time() - started, 2), "error": f"{type(exc).__name__}: {exc}"}
    print(f"{'PASS' if record['ok'] else 'FAIL'} | {name} | {record.get('note', record.get('error', ''))}")
    return record


def case_normal():
    r = run_research(
        "How Python type annotations differ from runtime validation",
        1,
        ["https://docs.python.org/3/library/typing.html"],
    )
    report = r.get("report") or ""
    has_sources = "https://docs.python.org/3/library/typing.html" in report
    return {
        "ok": r.get("status") == "completed" and has_sources and r.get("actual_loops") == 1,
        "status": r.get("status"),
        "actual_loops": r.get("actual_loops"),
        "report_chars": len(report),
        "note": f"status={r.get('status')} loops={r.get('actual_loops')} chars={len(report)}",
    }


def case_empty_source():
    r = run_research(
        "A topic whose provided page does not exist",
        1,
        ["https://docs.python.org/3/library/this-page-should-not-exist-xyz.html"],
    )
    report = (r.get("report") or "").lower()
    empty_summary = 'no verified sources were retrieved; no factual summary was generated.' in report
    empty_citations = not report.split('### sources:', 1)[-1].strip()
    return {
        "ok": r.get("status") in {"failed", "empty"} and empty_summary and empty_citations,
        "status": r.get("status"),
        "report_chars": len(r.get("report") or ""),
        "empty_summary_notice": empty_summary,
        "empty_citations": empty_citations,
        "note": f"status={r.get('status')} 未产出成功研究报告",
    }


def case_unreachable_source():
    r = run_research(
        "A topic whose provided domain cannot be resolved",
        1,
        ["https://nonexistent-domain-for-edge-test-abc123.example/"],
    )
    return {
        "ok": r.get("status") in {"failed", "empty"},
        "status": r.get("status"),
        "error": (r.get("error") or "")[:160],
        "note": f"status={r.get('status')} error={(r.get('error') or '')[:60]}",
    }


def case_plain_text_output():
    from langchain_core.messages import HumanMessage
    from types import SimpleNamespace
    from unittest.mock import patch

    from local_app.settings import load_model_settings
    from ollama_deep_researcher.configuration import Configuration
    from ollama_deep_researcher import graph as flow
    from ollama_deep_researcher.lmstudio import ChatLMStudio
    from ollama_deep_researcher.utils import strip_thinking_tokens

    settings = load_model_settings()
    llm = ChatLMStudio(base_url=settings['base_url'], model=settings['model'], temperature=0, timeout=120, max_tokens=256, max_retries=0, reasoning_effort='none')
    content = llm.invoke([HumanMessage("Reply with exactly: hello")]).content
    cleaned = strip_thinking_tokens(content)
    parsed_failed = False
    try:
        json.loads(cleaned)
    except json.JSONDecodeError:
        parsed_failed = True
    class CapturedOutput:
        def invoke(self, messages):
            return SimpleNamespace(content=content)
    fallback = 'Python type annotations'
    with patch.object(flow, 'get_llm', return_value=CapturedOutput()):
        application_result = flow.generate_search_query_with_structured_output(
            Configuration(llm_provider='lmstudio'), [], None, fallback, 'query', 'query'
        )
    return {
        "ok": isinstance(cleaned, str) and parsed_failed and application_result == {'search_query': fallback},
        "raw_prefix": content[:60],
        "cleaned_prefix": cleaned[:60],
        "application_result": application_result,
        "verification_type": "real model output replayed through actual application parser",
        "note": "真实模型输出重放至应用解析方法，核对非法JSON回退值；不等同自然异常端到端",
    }


def main() -> int:
    from local_app.settings import load_model_settings
    settings = load_model_settings()
    OUT.mkdir(parents=True, exist_ok=True)
    results = [
        case("normal", case_normal),
        case("empty_source", case_empty_source),
        case("unreachable_source", case_unreachable_source),
        case("plain_text_output", case_plain_text_output),
    ]
    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model_endpoint": settings['base_url'],
        "model": settings['model'],
        "results": results,
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
    }
    path = OUT / f"real-model-edge-cases-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {path}")
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
