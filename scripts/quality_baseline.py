"""报告质量基线：扫描 outputs 里已落盘的结果，跑规则自检并汇总。

用法：
    python scripts/quality_baseline.py                 # 只看，不写文件
    python scripts/quality_baseline.py --write         # 结果写入 outputs/checks/
    python scripts/quality_baseline.py --outputs DIR   # 指定目录
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from local_app.quality import check_report, summarize  # noqa: E402


def load_results(outputs: Path) -> list[dict]:
    results = []
    for path in sorted(outputs.glob("*.json")):
        if path.parent.name == "checks":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "topic" in data:
            data.setdefault("id", path.stem)
            results.append(data)
    return results


def render(rows: list[dict], summary: dict) -> str:
    lines = [
        f"{'id':10} {'status':10} {'pass':>5} {'sec':>7}  failed",
        "-" * 72,
    ]
    for r in rows:
        failed = ",".join(r["failed"]) or "-"
        secs = f"{r['seconds']:.2f}" if isinstance(r.get("seconds"), (int, float)) else "-"
        lines.append(
            f"{r['id'][:10]:10} {r['status'][:10]:10} "
            f"{r['passed']}/{r['total']:<3} {secs:>7}  {failed}"
        )
    lines.append("-" * 72)
    if summary.get("reports"):
        lines.append(
            f"报告 {summary['reports']} 份，完成率 {summary['completion_rate']:.0%}，"
            f"全项通过 {summary['all_checks_passed']} 份，平均分 {summary['avg_score']}"
        )
        if summary["top_failures"]:
            lines.append("最常见未通过：" + "、".join(
                f"{name}×{count}" for name, count in summary["top_failures"][:5]))
    else:
        lines.append("outputs 下没有可检查的报告")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="规则式报告质量基线")
    parser.add_argument("--outputs", default=str(ROOT / "outputs"), help="报告目录")
    parser.add_argument("--write", action="store_true", help="把结果写入 outputs/checks/")
    parser.add_argument("--exclude-errors", action="store_true",
                        help="跳过 error 非空的样本（异常路径验证不计入正常基线）")
    args = parser.parse_args()

    outputs = Path(args.outputs)
    raw = load_results(outputs)
    if args.exclude_errors:
        raw = [r for r in raw if not (r.get("error") or "").strip()]
    rows = [check_report(r) for r in raw]
    summary = summarize(rows)
    print(render(rows, summary))

    if args.write and rows:
        target = outputs / "checks"
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        payload = {
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outputs": str(outputs),
            "summary": summary,
            "reports": rows,
        }
        out = target / f"quality-baseline-{stamp}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
