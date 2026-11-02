"""接口集成测试：对运行中的服务打一组真实 HTTP 请求，产出 JSON 报告。

与单元测试的区别：这个脚本走的是真实端口、真实路由、真实状态码，
对应 TapTap 里 data_server/jobs/tools/system_test.py 那一层。

用法：
    python scripts/system_test.py                    # 打 127.0.0.1:8765
    python scripts/system_test.py --base-url http://127.0.0.1:8799 --write
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://127.0.0.1:8765"


def http(method: str, url: str, body: dict | None = None, timeout: int = 15):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")


def run_checks(base: str) -> list[dict]:
    results: list[dict] = []

    def add(name, ok, detail):
        results.append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + " :: " + str(detail)[:90])

    status, text = http("GET", base + "/health")
    add("健康检查 /health", status == 200 and '"status":"ok"' in text.replace(" ", ""), f"http={status}")

    status, text = http("GET", base + "/")
    add("首页返回 HTML", status == 200 and "<html" in text.lower(), f"http={status} len={len(text)}")

    status, text = http("GET", base + "/favicon.ico")
    add("图标 /favicon.ico", status == 200, f"http={status}")

    status, text = http("GET", base + "/reports")
    ok_list = status == 200 and text.strip().startswith("[")
    add("报告列表 /reports", ok_list, f"http={status}")
    report_id = ""
    if ok_list:
        try:
            items = json.loads(text)
            if items:
                report_id = items[0].get("id", "")
        except json.JSONDecodeError:
            ok_list = False

    if report_id:
        status, text = http("GET", base + f"/reports/{report_id}")
        add("报告详情 /reports/{id}", status == 200 and report_id in text, f"http={status}")

        status, text = http("GET", base + f"/reports/{report_id}/download")
        add("报告下载 /download", status == 200 and len(text) > 0, f"http={status} len={len(text)}")

        status, text = http("GET", base + f"/reports/{report_id}/check")
        ok_check = status == 200 and '"total"' in text and '"checks"' in text
        add("质量自检 /check", ok_check, f"http={status}")
    else:
        add("报告详情 /reports/{id}", False, "没有可用的报告 id，先跑一次研究")

    status, _ = http("GET", base + "/reports/not-a-real-id")
    add("未知报告返回 404", status == 404, f"http={status}")

    status, _ = http("POST", base + "/research", {"topic": "xy", "loops": 1})
    add("主题过短被拒（422）", status == 422, f"http={status}")

    status, _ = http("POST", base + "/research", {"topic": "Python 类型注解", "loops": 0})
    add("轮次越界被拒（422）", status == 422, f"http={status}")

    status, _ = http("POST", base + "/research", {"topic": "Python 类型注解", "loops": 1, "source_urls": ["a"] * 6})
    add("来源超过 5 条被拒（422）", status == 422, f"http={status}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="接口集成测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--write", action="store_true", help="写入 outputs/checks/")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    try:
        http("GET", base + "/health", timeout=3)
    except OSError as exc:
        print(f"无法连接 {base}：{exc}")
        return 2

    results = run_checks(base)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print("-" * 60)
    print(f"{passed}/{total} 通过")

    if args.write:
        target = ROOT / "outputs" / "checks"
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        payload = {
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base_url": base,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "results": results,
        }
        out = target / f"system-test-{stamp}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
